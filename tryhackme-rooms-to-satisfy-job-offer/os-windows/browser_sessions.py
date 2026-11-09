#!/usr/bin/env python3

"""Read TryHackMe cookies from supported Windows browser profiles."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
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
cCryptProtectUiForbidden = 0x1
cBrowserOrder = {
  "firefox": 0,
  "chrome": 1,
  "edge": 2,
  "chromium": 3,
}


class BrowserSessionError(RuntimeError):
  """Report a browser-cookie problem without exposing cookie values."""


class DataBlob(ctypes.Structure):
  """Match the Windows DATA_BLOB used by DPAPI."""

  _fields_ = [
    ("cbData", wintypes.DWORD),
    ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
  ]


@contextmanager
def fSnapshotDatabase(pDatabasePath: Path) -> Iterator[Path]:
  """Yield a coherent private SQLite snapshot and remove it afterwards."""

  vTempDirectory: Path | None = None
  vSourceConnection: sqlite3.Connection | None = None
  vDestinationConnection: sqlite3.Connection | None = None

  try:
    cTempRoot.mkdir(parents=True, exist_ok=True)
    vTempDirectory = Path(tempfile.mkdtemp(prefix="cookie-db-", dir=cTempRoot))
    vSnapshotPath = vTempDirectory / "Cookies.sqlite"
    vSourceUri = pDatabasePath.resolve(strict=True).as_uri() + "?mode=ro"
    vSourceConnection = sqlite3.connect(vSourceUri, uri=True, timeout=1.0)
    vDestinationConnection = sqlite3.connect(vSnapshotPath)
    vSourceConnection.backup(vDestinationConnection)
    vDestinationConnection.close()
    vDestinationConnection = None
    vSourceConnection.close()
    vSourceConnection = None
    yield vSnapshotPath
  except (OSError, sqlite3.Error) as vError:
    raise BrowserSessionError(
      "Windows could not create a private snapshot of the browser cookie "
      "database. Close that browser completely and retry; if it remains "
      "inaccessible, check the profile permissions."
    ) from vError
  finally:
    if vDestinationConnection is not None:
      vDestinationConnection.close()
    if vSourceConnection is not None:
      vSourceConnection.close()
    if vTempDirectory is not None and vTempDirectory.is_dir():
      shutil.rmtree(vTempDirectory, ignore_errors=True)


def fProfileName(pDatabasePath: Path) -> str:
  """Return the browser profile directory that owns a cookie store."""

  if pDatabasePath.parent.name.casefold() == "network":
    return pDatabasePath.parent.parent.name
  return pDatabasePath.parent.name


def fChromiumUserDataRoot(pDatabasePath: Path) -> Path:
  """Return the user-data root containing a Chromium Local State file."""

  if pDatabasePath.parent.name.casefold() == "network":
    return pDatabasePath.parent.parent.parent
  return pDatabasePath.parent.parent


def fDiscoverCookieStores(pHome: Path | None = None) -> list[dict[str, str]]:
  """Return supported Windows cookie databases without modifying them."""

  if pHome is None:
    vHome = Path.home()
    vRoamingRoot = Path(os.environ.get("APPDATA", vHome / "AppData" / "Roaming"))
    vLocalRoot = Path(
      os.environ.get("LOCALAPPDATA", vHome / "AppData" / "Local")
    )
  else:
    vHome = pHome
    vRoamingRoot = vHome / "AppData" / "Roaming"
    vLocalRoot = vHome / "AppData" / "Local"

  dPatterns: dict[str, list[tuple[Path, str]]] = {
    "firefox": [
      (vRoamingRoot, "Mozilla/Firefox/Profiles/*/cookies.sqlite"),
      (
        vLocalRoot,
        "Packages/Mozilla.Firefox_*/LocalCache/Roaming/Mozilla/Firefox/"
        "Profiles/*/cookies.sqlite",
      ),
    ],
    "chrome": [
      (vLocalRoot, "Google/Chrome/User Data/*/Network/Cookies"),
      (vLocalRoot, "Google/Chrome/User Data/*/Cookies"),
    ],
    "edge": [
      (vLocalRoot, "Microsoft/Edge/User Data/*/Network/Cookies"),
      (vLocalRoot, "Microsoft/Edge/User Data/*/Cookies"),
    ],
    "chromium": [
      (vLocalRoot, "Chromium/User Data/*/Network/Cookies"),
      (vLocalRoot, "Chromium/User Data/*/Cookies"),
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
          "format": "gecko" if vBrowser == "firefox" else "chromium-windows",
        }
        if vBrowser != "firefox":
          dStore["localState"] = str(
            fChromiumUserDataRoot(vResolvedPath) / "Local State"
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
  except BrowserSessionError:
    raise
  except (sqlite3.Error, OSError) as vError:
    raise BrowserSessionError(
      "Could not read the Firefox cookie database."
    ) from vError

  return lCookies


def fGeckoExpiryToUnix(pTimestamp: int) -> int:
  """Normalise Firefox expiry values stored as seconds or milliseconds."""

  vTimestamp = pTimestamp
  while vTimestamp > 10_000_000_000:
    vTimestamp //= 1000
  return vTimestamp


def fWindowsDpapiUnprotect(pEncryptedValue: bytes) -> bytes:
  """Decrypt one current-user DPAPI blob without logging its contents."""

  if not pEncryptedValue:
    return b""

  vInputBuffer = (ctypes.c_ubyte * len(pEncryptedValue)).from_buffer_copy(
    pEncryptedValue
  )
  dInput = DataBlob(
    len(pEncryptedValue),
    ctypes.cast(vInputBuffer, ctypes.POINTER(ctypes.c_ubyte)),
  )
  dOutput = DataBlob()
  vCrypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
  vKernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
  vCrypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DataBlob),
    ctypes.POINTER(ctypes.c_wchar_p),
    ctypes.POINTER(DataBlob),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DataBlob),
  ]
  vCrypt32.CryptUnprotectData.restype = wintypes.BOOL
  vKernel32.LocalFree.argtypes = [ctypes.c_void_p]
  vKernel32.LocalFree.restype = ctypes.c_void_p

  vSucceeded = vCrypt32.CryptUnprotectData(
    ctypes.byref(dInput),
    None,
    None,
    None,
    None,
    cCryptProtectUiForbidden,
    ctypes.byref(dOutput),
  )
  if not vSucceeded:
    vErrorCode = ctypes.get_last_error()
    raise BrowserSessionError(
      "Windows DPAPI could not decrypt this browser profile for the current "
      f"desktop user (error {vErrorCode})."
    )

  try:
    return ctypes.string_at(dOutput.pbData, dOutput.cbData)
  finally:
    if dOutput.pbData:
      vKernel32.LocalFree(dOutput.pbData)


def fReadChromiumMasterKey(pLocalStatePath: Path) -> bytes:
  """Read and decrypt a Chromium v10/v11 AES key from Local State."""

  try:
    with pLocalStatePath.open("r", encoding="utf-8") as vFile:
      dLocalState = json.load(vFile)
    vEncodedKey = dLocalState["os_crypt"]["encrypted_key"]
    if not isinstance(vEncodedKey, str):
      raise TypeError("encrypted_key is not text")
    vProtectedKey = base64.b64decode(vEncodedKey, validate=True)
  except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as vError:
    raise BrowserSessionError(
      "Could not read Chromium's encrypted key from Local State."
    ) from vError

  if not vProtectedKey.startswith(b"DPAPI"):
    raise BrowserSessionError(
      "Chromium Local State contains an unsupported Windows key format."
    )
  return fWindowsDpapiUnprotect(vProtectedKey[5:])


def fDecryptChromiumCookie(
  pEncryptedValue: bytes,
  pHost: str,
  pMasterKey: bytes | None,
) -> str:
  """Decrypt a legacy DPAPI or v10/v11 AES-GCM Chromium cookie."""

  if not pEncryptedValue:
    return ""
  if pEncryptedValue.startswith(b"v20"):
    raise BrowserSessionError(
      "This Chromium profile uses v20 app-bound cookie encryption. Windows "
      "intentionally permits only the browser application to decrypt these "
      "cookies; use an authenticated Firefox profile for this skill."
    )

  try:
    if pEncryptedValue[:3] in (b"v10", b"v11"):
      if not pMasterKey:
        raise BrowserSessionError(
          "Chromium's AES cookie key is not available for this profile."
        )
      if len(pEncryptedValue) < 3 + 12 + 16:
        raise BrowserSessionError("Chromium returned a truncated cookie value.")
      try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
      except ImportError as vError:
        raise BrowserSessionError(
          "Chromium cookies need the Python package 'cryptography'."
        ) from vError

      vNonce = pEncryptedValue[3:15]
      vCiphertextAndTag = pEncryptedValue[15:]
      vPlainValue = AESGCM(pMasterKey).decrypt(
        vNonce,
        vCiphertextAndTag,
        None,
      )
    else:
      vPlainValue = fWindowsDpapiUnprotect(pEncryptedValue)

    vHostDigest = hashlib.sha256(pHost.encode("utf-8")).digest()
    if vPlainValue.startswith(vHostDigest):
      vPlainValue = vPlainValue[len(vHostDigest):]
    return vPlainValue.decode("utf-8")
  except BrowserSessionError:
    raise
  except (ValueError, UnicodeDecodeError) as vError:
    raise BrowserSessionError(
      "Chromium cookie decryption failed for this Windows profile."
    ) from vError


def fChromiumExpiryToUnix(pChromiumTimestamp: int) -> int:
  """Convert Chromium microseconds since 1601 to Unix seconds."""

  if pChromiumTimestamp <= 0:
    return 0
  return int(pChromiumTimestamp / 1_000_000 - cChromiumEpochOffset)


def fReadChromiumCookies(
  pDatabasePath: Path,
  pLocalStatePath: Path,
) -> list[dict[str, object]]:
  """Read and decrypt unexpired TryHackMe cookies from Chrome or Edge."""

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

        if any(
          not str(dRow["value"] or "")
          and bytes(dRow["encrypted_value"] or b"").startswith(b"v20")
          for dRow in lRows
        ):
          raise BrowserSessionError(
            "This Chromium profile uses v20 app-bound cookie encryption. "
            "Windows intentionally permits only the browser application to "
            "decrypt these cookies; use an authenticated Firefox profile for "
            "this skill."
          )

        vNeedsMasterKey = any(
          not str(dRow["value"] or "")
          and bytes(dRow["encrypted_value"] or b"")[:3] in (b"v10", b"v11")
          for dRow in lRows
        )
        vMasterKey = (
          fReadChromiumMasterKey(pLocalStatePath)
          if vNeedsMasterKey
          else None
        )

        for dRow in lRows:
          vExpiry = fChromiumExpiryToUnix(int(dRow["expires_utc"] or 0))
          if vExpiry > 0 and vExpiry <= vNow:
            continue

          vValue = str(dRow["value"] or "")
          if not vValue:
            vValue = fDecryptChromiumCookie(
              bytes(dRow["encrypted_value"] or b""),
              str(dRow["host_key"]),
              vMasterKey,
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
      if dStore["format"] == "chromium-windows":
        lCookies = fReadChromiumCookies(
          Path(dStore["database"]),
          Path(dStore["localState"]),
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
