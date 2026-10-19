#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Read TryHackMe cookies from supported Debian browser profiles."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Iterator


cTryHackMeDomain = "tryhackme.com"
cSkillRoot = Path(__file__).resolve().parent.parent
cTempRoot = cSkillRoot.parent / "_" / "temp" / "thm"
cChromiumEpochOffset = 11_644_473_600
cBrowserOrder = {
  "firefox": 0,
  "chromium": 1,
  "librewolf": 2,
  "epiphany": 3,
}


class BrowserSessionError(RuntimeError):
  """Report a browser-cookie problem without exposing cookie values."""


@contextmanager
def fSnapshotDatabase(pDatabasePath: Path) -> Iterator[Path]:
  """Yield a private snapshot so a running browser cannot lock the read."""

  vTempDirectory: Path | None = None
  try:
    cTempRoot.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(cTempRoot, 0o700)
    vTempDirectory = Path(tempfile.mkdtemp(prefix="cookie-db-", dir=cTempRoot))
    os.chmod(vTempDirectory, 0o700)
    vSnapshotPath = vTempDirectory / pDatabasePath.name
    shutil.copy2(pDatabasePath, vSnapshotPath)
    os.chmod(vSnapshotPath, 0o600)

    for vSuffix in ("-wal", "-shm"):
      vSourcePath = Path(f"{pDatabasePath}{vSuffix}")
      if vSourcePath.is_file():
        vDestinationPath = Path(f"{vSnapshotPath}{vSuffix}")
        shutil.copy2(vSourcePath, vDestinationPath)
        os.chmod(vDestinationPath, 0o600)

    yield vSnapshotPath
  except (OSError, sqlite3.Error) as vError:
    raise BrowserSessionError(
      f"Could not create a private snapshot of {pDatabasePath}: {vError}"
    ) from vError
  finally:
    if vTempDirectory is not None and vTempDirectory.is_dir():
      shutil.rmtree(vTempDirectory, ignore_errors=True)


def fDiscoverCookieStores(pHome: Path | None = None) -> list[dict[str, str]]:
  """Return supported cookie databases without opening or modifying them."""

  vHome = pHome if pHome is not None else Path.home()
  dPatterns = {
    "firefox": [
      ".mozilla/firefox/*/cookies.sqlite",
      ".var/app/org.mozilla.firefox/.mozilla/firefox/*/cookies.sqlite",
      "snap/firefox/common/.mozilla/firefox/*/cookies.sqlite",
    ],
    "chromium": [
      ".config/chromium/*/Cookies",
      ".config/chromium/*/Network/Cookies",
      ".var/app/org.chromium.Chromium/config/chromium/*/Cookies",
      ".var/app/org.chromium.Chromium/config/chromium/*/Network/Cookies",
      "snap/chromium/common/chromium/*/Cookies",
      "snap/chromium/common/chromium/*/Network/Cookies",
    ],
    "librewolf": [
      ".librewolf/*/cookies.sqlite",
      ".var/app/io.gitlab.librewolf-community/.librewolf/*/cookies.sqlite",
    ],
    "epiphany": [
      ".local/share/epiphany/cookies.sqlite",
      ".local/share/epiphany-*/cookies.sqlite",
      ".var/app/org.gnome.Epiphany/data/epiphany/cookies.sqlite",
    ],
  }
  lStores: list[dict[str, str]] = []
  sSeenPaths: set[Path] = set()

  for vBrowser, lPatterns in dPatterns.items():
    for vPattern in lPatterns:
      for vPath in sorted(vHome.glob(vPattern)):
        try:
          vResolvedPath = vPath.resolve(strict=True)
        except OSError:
          continue

        if vResolvedPath in sSeenPaths or not vResolvedPath.is_file():
          continue

        sSeenPaths.add(vResolvedPath)
        lStores.append({
          "browser": vBrowser,
          "profile": vPath.parent.name,
          "database": str(vResolvedPath),
          "format": "chromium" if vBrowser == "chromium" else "gecko",
        })

  return sorted(
    lStores,
    key=lambda pStore: (
      cBrowserOrder.get(pStore["browser"], 99),
      pStore["profile"],
      pStore["database"],
    ),
  )


def fReadGeckoCookies(pDatabasePath: Path) -> list[dict[str, object]]:
  """Read unexpired TryHackMe cookies from Firefox-compatible databases."""

  lCookies: list[dict[str, object]] = []
  vNow = int(time.time())

  try:
    with fSnapshotDatabase(pDatabasePath) as vSnapshotPath:
      vConnection = sqlite3.connect(vSnapshotPath)
      try:
        vConnection.row_factory = sqlite3.Row
        lRows = vConnection.execute(
          """
          SELECT name, value, host, path, expiry, isSecure, isHttpOnly
          FROM moz_cookies
          WHERE lower(host) LIKE ?
          """,
          (f"%{cTryHackMeDomain}",),
        ).fetchall()

        for dRow in lRows:
          vExpiry = int(dRow["expiry"] or 0)
          if vExpiry > 0 and vExpiry <= vNow:
            continue

          dCookie: dict[str, object] = {
            "name": str(dRow["name"]),
            "value": str(dRow["value"]),
            "domain": str(dRow["host"]),
            "path": str(dRow["path"] or "/"),
            "secure": bool(dRow["isSecure"]),
            "httpOnly": bool(dRow["isHttpOnly"]),
          }
          if vExpiry > 0:
            dCookie["expires"] = float(vExpiry)
          lCookies.append(dCookie)
      finally:
        vConnection.close()
  except (BrowserSessionError, sqlite3.Error, OSError) as vError:
    raise BrowserSessionError(
      f"Could not read the browser cookie database {pDatabasePath}: {vError}"
    ) from vError

  return lCookies


def fGetChromiumSafeStoragePassword() -> bytes:
  """Read Chromium's encryption password from the current user's keyring."""

  try:
    import secretstorage
  except ImportError as vError:
    raise BrowserSessionError(
      "Chromium cookies need the Python package 'secretstorage'."
    ) from vError

  try:
    vBus = secretstorage.dbus_init()
    vCollection = secretstorage.get_default_collection(vBus)
    if vCollection.is_locked():
      raise BrowserSessionError(
        "The desktop keyring is locked; unlock it before reading Chromium cookies."
      )

    lItems = [
      vItem
      for vItem in vCollection.get_all_items()
      if vItem.get_attributes().get("application") == "chromium"
    ]
    lItems.sort(
      key=lambda pItem: pItem.get_modified() if hasattr(pItem, "get_modified") else 0,
      reverse=True,
    )

    for vItem in lItems:
      vSecret = vItem.get_secret()
      if vSecret:
        return bytes(vSecret)
  except BrowserSessionError:
    raise
  except Exception as vError:
    raise BrowserSessionError(
      "Could not read Chromium Safe Storage from the desktop keyring."
    ) from vError

  raise BrowserSessionError(
    "No Chromium Safe Storage entry exists in the desktop keyring."
  )


def fDecryptChromiumCookie(
  pEncryptedValue: bytes,
  pHost: str,
  pSafeStoragePassword: bytes | None,
) -> str:
  """Decrypt a Chromium Linux v10 or v11 cookie value."""

  if not pEncryptedValue:
    return ""

  vPrefix = pEncryptedValue[:3]
  if vPrefix not in (b"v10", b"v11"):
    if vPrefix == b"v20":
      raise BrowserSessionError(
        "This Chromium profile uses unsupported v20 app-bound cookie encryption."
      )
    try:
      return pEncryptedValue.decode("utf-8")
    except UnicodeDecodeError as vError:
      raise BrowserSessionError(
        "Chromium returned an unknown cookie-encryption format."
      ) from vError

  if vPrefix == b"v10":
    vPassword = b"peanuts"
  else:
    if not pSafeStoragePassword:
      raise BrowserSessionError(
        "Chromium v11 cookies require the desktop keyring password."
      )
    vPassword = pSafeStoragePassword

  try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
  except ImportError as vError:
    raise BrowserSessionError(
      "Chromium cookies need the Python package 'cryptography'."
    ) from vError

  try:
    vKey = hashlib.pbkdf2_hmac("sha1", vPassword, b"saltysalt", 1, dklen=16)
    vCipher = Cipher(algorithms.AES(vKey), modes.CBC(b" " * 16))
    vDecryptor = vCipher.decryptor()
    vPaddedValue = vDecryptor.update(pEncryptedValue[3:]) + vDecryptor.finalize()
    vUnpadder = padding.PKCS7(128).unpadder()
    vPlainValue = vUnpadder.update(vPaddedValue) + vUnpadder.finalize()

    vHostDigest = hashlib.sha256(pHost.encode("utf-8")).digest()
    if vPlainValue.startswith(vHostDigest):
      vPlainValue = vPlainValue[len(vHostDigest):]

    return vPlainValue.decode("utf-8")
  except (ValueError, UnicodeDecodeError) as vError:
    raise BrowserSessionError(
      "Chromium cookie decryption failed; the keyring entry may not match the profile."
    ) from vError


def fChromiumExpiryToUnix(pChromiumTimestamp: int) -> int:
  """Convert Chromium microseconds since 1601 to Unix seconds."""

  if pChromiumTimestamp <= 0:
    return 0
  return int(pChromiumTimestamp / 1_000_000 - cChromiumEpochOffset)


def fReadChromiumCookies(pDatabasePath: Path) -> list[dict[str, object]]:
  """Read and decrypt unexpired TryHackMe cookies from Chromium."""

  lCookies: list[dict[str, object]] = []
  vNow = int(time.time())
  vSafeStoragePassword: bytes | None = None

  try:
    with fSnapshotDatabase(pDatabasePath) as vSnapshotPath:
      vConnection = sqlite3.connect(vSnapshotPath)
      try:
        vConnection.row_factory = sqlite3.Row
        lRows = vConnection.execute(
          """
          SELECT name, value, encrypted_value, host_key, path, expires_utc,
                 is_secure, is_httponly
          FROM cookies
          WHERE lower(host_key) LIKE ?
          """,
          (f"%{cTryHackMeDomain}",),
        ).fetchall()

        if any(bytes(dRow["encrypted_value"] or b"").startswith(b"v11") for dRow in lRows):
          vSafeStoragePassword = fGetChromiumSafeStoragePassword()

        for dRow in lRows:
          vExpiry = fChromiumExpiryToUnix(int(dRow["expires_utc"] or 0))
          if vExpiry > 0 and vExpiry <= vNow:
            continue

          vValue = str(dRow["value"] or "")
          if not vValue:
            vValue = fDecryptChromiumCookie(
              bytes(dRow["encrypted_value"] or b""),
              str(dRow["host_key"]),
              vSafeStoragePassword,
            )

          dCookie: dict[str, object] = {
            "name": str(dRow["name"]),
            "value": vValue,
            "domain": str(dRow["host_key"]),
            "path": str(dRow["path"] or "/"),
            "secure": bool(dRow["is_secure"]),
            "httpOnly": bool(dRow["is_httponly"]),
          }
          if vExpiry > 0:
            dCookie["expires"] = float(vExpiry)
          lCookies.append(dCookie)
      finally:
        vConnection.close()
  except (BrowserSessionError, sqlite3.Error, OSError) as vError:
    raise BrowserSessionError(
      f"Could not read the Chromium cookie database {pDatabasePath}: {vError}"
    ) from vError

  return lCookies


def fFindSessionCandidates(
  pBrowser: str = "auto",
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
  """Return profiles with unexpired TryHackMe cookies and sanitised errors."""

  lCandidates: list[dict[str, object]] = []
  lErrors: list[dict[str, str]] = []

  for dStore in fDiscoverCookieStores():
    if pBrowser != "auto" and dStore["browser"] != pBrowser:
      continue

    try:
      if dStore["format"] == "chromium":
        lCookies = fReadChromiumCookies(Path(dStore["database"]))
      else:
        lCookies = fReadGeckoCookies(Path(dStore["database"]))

      if not lCookies:
        continue

      lCandidates.append({
        "browser": dStore["browser"],
        "profile": dStore["profile"],
        "database": dStore["database"],
        "cookies": lCookies,
      })
    except BrowserSessionError as vError:
      lErrors.append({
        "browser": dStore["browser"],
        "profile": dStore["profile"],
        "error": str(vError),
      })

  return lCandidates, lErrors
