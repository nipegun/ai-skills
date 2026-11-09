#!/usr/bin/env python3

"""Read TryHackMe cookies from supported macOS browser profiles."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import time
from typing import Iterator


cTryHackMeDomain = "tryhackme.com"
cSkillRoot = Path(__file__).resolve().parent.parent.parent
cTempRoot = cSkillRoot.parent / "_" / "temp" / "thm"
cChromiumEpochOffset = 11_644_473_600
cBrowserOrder = {
  "firefox": 0,
  "chrome": 1,
  "chromium": 2,
}
cKeychainNames = {
  "chrome": ("Chrome Safe Storage", "Chrome"),
  "chromium": ("Chromium Safe Storage", "Chromium"),
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
      "Could not create a private snapshot of the browser cookie database."
    ) from vError
  finally:
    if vTempDirectory is not None and vTempDirectory.is_dir():
      shutil.rmtree(vTempDirectory, ignore_errors=True)


def fProfileName(pDatabasePath: Path) -> str:
  """Return the browser profile directory that owns a cookie store."""

  if pDatabasePath.parent.name.casefold() == "network":
    return pDatabasePath.parent.parent.name
  return pDatabasePath.parent.name


def fDiscoverCookieStores(pHome: Path | None = None) -> list[dict[str, str]]:
  """Return supported macOS cookie databases without modifying them."""

  vHome = pHome if pHome is not None else Path.home()
  vApplicationSupport = vHome / "Library" / "Application Support"
  dPatterns: dict[str, list[tuple[Path, str]]] = {
    "firefox": [
      (vApplicationSupport, "Firefox/Profiles/*/cookies.sqlite"),
    ],
    "chrome": [
      (vApplicationSupport, "Google/Chrome/*/Network/Cookies"),
      (vApplicationSupport, "Google/Chrome/*/Cookies"),
    ],
    "chromium": [
      (vApplicationSupport, "Chromium/*/Network/Cookies"),
      (vApplicationSupport, "Chromium/*/Cookies"),
    ],
  }
  lStores: list[dict[str, str]] = []
  sSeenPaths: set[Path] = set()

  for vBrowser, lPatterns in dPatterns.items():
    for vRoot, vPattern in lPatterns:
      for vPath in sorted(vRoot.glob(vPattern)):
        try:
          vResolvedPath = vPath.resolve(strict=True)
        except OSError:
          continue
        if vResolvedPath in sSeenPaths or not vResolvedPath.is_file():
          continue

        sSeenPaths.add(vResolvedPath)
        dStore = {
          "browser": vBrowser,
          "profile": fProfileName(vResolvedPath),
          "database": str(vResolvedPath),
          "format": "gecko" if vBrowser == "firefox" else "chromium-mac",
        }
        if vBrowser in cKeychainNames:
          dStore["keychainService"], dStore["keychainAccount"] = (
            cKeychainNames[vBrowser]
          )
        lStores.append(dStore)

  return sorted(
    lStores,
    key=lambda pStore: (
      cBrowserOrder.get(pStore["browser"], 99),
      0 if pStore["profile"].casefold() == "default" else 1,
      pStore["profile"].casefold(),
      pStore["database"].casefold(),
    ),
  )


def fGeckoExpiryToUnix(pTimestamp: int) -> int:
  """Normalise Firefox expiry values stored as seconds or milliseconds."""

  vTimestamp = pTimestamp
  while vTimestamp > 10_000_000_000:
    vTimestamp //= 1000
  return vTimestamp


def fReadGeckoCookies(pDatabasePath: Path) -> list[dict[str, object]]:
  """Read unexpired TryHackMe cookies from a Firefox database."""

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
          WHERE lower(host) = ? OR lower(host) LIKE ?
          """,
          (cTryHackMeDomain, f"%.{cTryHackMeDomain}"),
        ).fetchall()

        for dRow in lRows:
          vExpiry = fGeckoExpiryToUnix(int(dRow["expiry"] or 0))
          if vExpiry > 0 and vExpiry <= vNow:
            continue

          vValue = str(dRow["value"] or "")
          if not vValue:
            continue
          dCookie: dict[str, object] = {
            "name": str(dRow["name"]),
            "value": vValue,
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
  except BrowserSessionError:
    raise
  except (sqlite3.Error, OSError) as vError:
    raise BrowserSessionError(
      "Could not read the Firefox cookie database."
    ) from vError

  return lCookies


def fExistingUserKeychains() -> list[Path]:
  """Return existing user keychains while ignoring stale search-list entries."""

  lPaths: list[Path] = []
  try:
    dResult = subprocess.run(
      ["/usr/bin/security", "list-keychains", "-d", "user"],
      check=False,
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,
      timeout=5,
    )
    if dResult.returncode == 0:
      for vRawPath in shlex.split(dResult.stdout.decode("utf-8", "replace")):
        vPath = Path(vRawPath).expanduser()
        if vPath.is_file() and vPath not in lPaths:
          lPaths.append(vPath)
  except (OSError, subprocess.SubprocessError):
    pass

  for vName in ("login.keychain-db", "login.keychain"):
    vPath = Path.home() / "Library" / "Keychains" / vName
    if vPath.is_file() and vPath not in lPaths:
      lPaths.append(vPath)
  return lPaths


def fReadMacKeychainPassword(pService: str, pAccount: str) -> bytes:
  """Read a Chromium Safe Storage password without logging its contents."""

  lKeychains: list[Path | None] = [None, *fExistingUserKeychains()]
  for vKeychainPath in lKeychains:
    lCommand = [
      "/usr/bin/security",
      "find-generic-password",
      "-w",
      "-a",
      pAccount,
      "-s",
      pService,
    ]
    if vKeychainPath is not None:
      lCommand.append(str(vKeychainPath))
    try:
      dResult = subprocess.run(
        lCommand,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=15,
      )
    except (OSError, subprocess.SubprocessError):
      continue

    vPassword = dResult.stdout.rstrip(b"\r\n")
    if dResult.returncode == 0 and vPassword:
      return vPassword

  raise BrowserSessionError(
    f"macOS could not read {pService} for the current desktop user. "
    "Unlock the login keychain and allow access when macOS asks, or use an "
    "authenticated Firefox profile."
  )


def fDecryptChromiumCookie(
  pEncryptedValue: bytes,
  pHost: str,
  pSafeStoragePassword: bytes | None,
) -> str:
  """Decrypt a Chromium macOS v10 AES-CBC cookie value."""

  if not pEncryptedValue:
    return ""
  if not pEncryptedValue.startswith(b"v10"):
    if pEncryptedValue.startswith((b"v11", b"v20")):
      raise BrowserSessionError(
        "This Chromium profile uses an unsupported cookie-encryption format."
      )
    try:
      return pEncryptedValue.decode("utf-8")
    except UnicodeDecodeError as vError:
      raise BrowserSessionError(
        "Chromium returned an unknown cookie-encryption format."
      ) from vError
  if not pSafeStoragePassword:
    raise BrowserSessionError(
      "Chromium v10 cookies require the browser's macOS Safe Storage password."
    )

  try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
  except ImportError as vError:
    raise BrowserSessionError(
      "Chrome and Chromium cookies need the Python package 'cryptography'."
    ) from vError

  try:
    vKey = hashlib.pbkdf2_hmac(
      "sha1",
      pSafeStoragePassword,
      b"saltysalt",
      1003,
      dklen=16,
    )
    vDecryptor = Cipher(algorithms.AES(vKey), modes.CBC(b" " * 16)).decryptor()
    vPaddedValue = (
      vDecryptor.update(pEncryptedValue[3:]) + vDecryptor.finalize()
    )
    vUnpadder = padding.PKCS7(128).unpadder()
    vPlainValue = vUnpadder.update(vPaddedValue) + vUnpadder.finalize()

    vHostDigest = hashlib.sha256(pHost.encode("utf-8")).digest()
    if vPlainValue.startswith(vHostDigest):
      vPlainValue = vPlainValue[len(vHostDigest):]
    return vPlainValue.decode("utf-8")
  except (ValueError, UnicodeDecodeError) as vError:
    raise BrowserSessionError(
      "Chromium cookie decryption failed; Safe Storage may not match this profile."
    ) from vError


def fChromiumExpiryToUnix(pChromiumTimestamp: int) -> int:
  """Convert Chromium microseconds since 1601 to Unix seconds."""

  if pChromiumTimestamp <= 0:
    return 0
  return int(pChromiumTimestamp / 1_000_000 - cChromiumEpochOffset)


def fReadChromiumCookies(
  pDatabasePath: Path,
  pKeychainService: str,
  pKeychainAccount: str,
  pSafeStoragePassword: bytes | None = None,
) -> list[dict[str, object]]:
  """Read and decrypt unexpired TryHackMe cookies from Chrome or Chromium."""

  lCookies: list[dict[str, object]] = []
  vNow = int(time.time())

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
          WHERE lower(host_key) = ? OR lower(host_key) LIKE ?
          """,
          (cTryHackMeDomain, f"%.{cTryHackMeDomain}"),
        ).fetchall()

        lActiveRows = [
          dRow
          for dRow in lRows
          if (
            fChromiumExpiryToUnix(int(dRow["expires_utc"] or 0)) <= 0
            or fChromiumExpiryToUnix(int(dRow["expires_utc"] or 0)) > vNow
          )
        ]
        vNeedsPassword = any(
          not str(dRow["value"] or "")
          and bytes(dRow["encrypted_value"] or b"").startswith(b"v10")
          for dRow in lActiveRows
        )
        vPassword = pSafeStoragePassword
        if vNeedsPassword and not vPassword:
          vPassword = fReadMacKeychainPassword(
            pKeychainService,
            pKeychainAccount,
          )

        for dRow in lActiveRows:
          vExpiry = fChromiumExpiryToUnix(int(dRow["expires_utc"] or 0))
          vValue = str(dRow["value"] or "")
          if not vValue:
            vValue = fDecryptChromiumCookie(
              bytes(dRow["encrypted_value"] or b""),
              str(dRow["host_key"]),
              vPassword,
            )
          if not vValue:
            continue

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
  except BrowserSessionError:
    raise
  except (sqlite3.Error, OSError) as vError:
    raise BrowserSessionError(
      "Could not read the Chromium cookie database."
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
      if dStore["format"] == "chromium-mac":
        lCookies = fReadChromiumCookies(
          Path(dStore["database"]),
          dStore["keychainService"],
          dStore["keychainAccount"],
        )
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
