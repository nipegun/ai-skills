#!/usr/bin/env python3

"""Use an authenticated browser context to read the TryHackMe catalogue."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import random
import re
import shutil
import time
import tempfile
from typing import Callable
from urllib.parse import quote, urlencode, urlparse


cBaseUrl = "https://tryhackme.com"
cCatalogueEndpoint = f"{cBaseUrl}/api/v2/hacktivities/extended-search"
cSessionEndpoint = f"{cBaseUrl}/api/v2/users/self"
cTasksEndpoint = f"{cBaseUrl}/api/v2/rooms/tasks"
cModuleDataEndpoint = f"{cBaseUrl}/api/v2/modules/data"
cPrimeUrl = f"{cBaseUrl}/hacktivities/search?page=1"
cSkillRoot = Path(__file__).resolve().parent.parent
cTempRoot = cSkillRoot.parent / "_" / "temp" / "thm"
cUserAgent = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
  "AppleWebKit/537.36 (KHTML, like Gecko) "
  "Chrome/151.0.0.0 Safari/537.36"
)
cFetchScript = """
async ({pUrl, pTimeoutMs}) => {
  const vController = new AbortController();
  const vTimer = setTimeout(() => vController.abort(), pTimeoutMs);
  try {
    const vResponse = await fetch(pUrl, {
      cache: "no-store",
      credentials: "include",
      method: "GET",
      redirect: "follow",
      signal: vController.signal
    });
    const vBody = await vResponse.text();
    return {
      body: vBody,
      contentType: vResponse.headers.get("content-type") || "",
      finalUrl: vResponse.url,
      retryAfter: vResponse.headers.get("retry-after") || "",
      status: vResponse.status
    };
  } finally {
    clearTimeout(vTimer);
  }
}
"""
cQuickGetScript = """
async ({pUrl, pTimeoutMs}) => {
  const vController = new AbortController();
  const vTimer = setTimeout(() => vController.abort(), pTimeoutMs);
  try {
    const vResponse = await fetch(pUrl, {
      cache: "no-store",
      credentials: "include",
      method: "GET",
      redirect: "follow",
      signal: vController.signal
    });
    if (vResponse.body) {
      await vResponse.body.cancel();
    }
    return {
      finalUrl: vResponse.url,
      retryAfter: vResponse.headers.get("retry-after") || "",
      status: vResponse.status
    };
  } finally {
    clearTimeout(vTimer);
  }
}
"""


class TryHackMeClientError(RuntimeError):
  """Base error for browser-backed TryHackMe operations."""


class SecurityCheckpointError(TryHackMeClientError):
  """Raised when Vercel's browser checkpoint does not complete."""


class AuthenticationError(TryHackMeClientError):
  """Raised when a candidate browser session is not authenticated."""


class CatalogueFormatError(TryHackMeClientError):
  """Raised when the current catalogue payload cannot be interpreted safely."""


class RateLimitError(TryHackMeClientError):
  """Raised after TryHackMe returns a rate-limit response."""

  def __init__(self, pMessage: str, pRetryAfter: float | None = None) -> None:
    super().__init__(pMessage)
    self.vRetryAfter = pRetryAfter


class AdaptiveRateLimiter:
  """Keep requests sequential and adapt conservatively to server responses."""

  def __init__(
    self,
    pInitialDelay: float,
    pMinimumDelay: float = 0.75,
    pMaximumDelay: float = 60.0,
  ) -> None:
    self.vDelay = max(pMinimumDelay, pInitialDelay)
    self.vMinimumDelay = pMinimumDelay
    self.vMaximumDelay = pMaximumDelay
    self.vSuccesses = 0
    self.vLastRequestAt = 0.0

  def mWait(self) -> None:
    vElapsed = time.monotonic() - self.vLastRequestAt
    vJitter = random.uniform(0.85, 1.15)
    vWaitFor = max(0.0, self.vDelay * vJitter - vElapsed)
    if vWaitFor > 0:
      time.sleep(vWaitFor)
    self.vLastRequestAt = time.monotonic()

  def mSuccess(self) -> None:
    self.vSuccesses += 1
    if self.vSuccesses >= 20:
      self.vDelay = max(self.vMinimumDelay, self.vDelay * 0.95)
      self.vSuccesses = 0

  def mLimited(self, pRetryAfter: float | None = None) -> float:
    self.vSuccesses = 0
    vRequestedDelay = pRetryAfter if pRetryAfter is not None else self.vDelay * 2
    self.vDelay = min(self.vMaximumDelay, max(self.vDelay * 2, vRequestedDelay))
    return self.vDelay


def fIsoNow() -> str:
  """Return a stable UTC timestamp for cache metadata."""

  return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fRequireUsableSocketPath() -> None:
  """Keep the cross-platform launch contract; Windows has no Unix socket limit."""

  return None


def fFindChromiumExecutable() -> str:
  """Find an installed Chrome, Edge or Chromium binary for Playwright."""

  lCandidates: list[Path] = []
  for vEnvironmentName in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
    vRoot = os.environ.get(vEnvironmentName)
    if not vRoot:
      continue
    vRootPath = Path(vRoot)
    lCandidates.extend((
      vRootPath / "Google" / "Chrome" / "Application" / "chrome.exe",
      vRootPath / "Microsoft" / "Edge" / "Application" / "msedge.exe",
      vRootPath / "Chromium" / "Application" / "chrome.exe",
    ))

  for vPath in lCandidates:
    if vPath.is_file():
      return str(vPath)

  for vName in ("chrome", "msedge", "chromium"):
    vPath = shutil.which(vName)
    if vPath:
      return vPath
  raise TryHackMeClientError(
    "Google Chrome, Microsoft Edge or Chromium is required to pass "
    "TryHackMe's browser checkpoint."
  )


def fParseRetryAfter(pValue: str) -> float | None:
  """Parse a Retry-After value expressed as seconds."""

  try:
    return max(0.0, float(pValue.strip())) if pValue.strip() else None
  except ValueError:
    return None


def fNormaliseText(pValue: object) -> str:
  """Convert catalogue text or basic HTML to clean single-line text."""

  if pValue is None:
    return ""
  vText = html.unescape(str(pValue))
  vText = re.sub(r"<[^>]+>", " ", vText)
  return re.sub(r"\s+", " ", vText).strip()


def fCaseInsensitiveValue(pRecord: dict[str, object], pKeys: tuple[str, ...]) -> object:
  """Find the first matching value regardless of JSON key casing."""

  dLowerKeys = {str(vKey).lower(): vValue for vKey, vValue in pRecord.items()}
  for vKey in pKeys:
    if vKey.lower() in dLowerKeys:
      vValue = dLowerKeys[vKey.lower()]
      if vValue is None:
        continue
      if isinstance(vValue, str) and not vValue.strip():
        continue
      return vValue
  return None


def fExtractRoomCode(pRecord: dict[str, object]) -> str:
  """Extract a canonical room code from a catalogue record."""

  vUrlValue = fCaseInsensitiveValue(
    pRecord,
    ("url", "href", "link", "path", "roomUrl", "roomPath"),
  )
  if isinstance(vUrlValue, str):
    vMatch = re.search(r"/room/([A-Za-z0-9_-]+)", vUrlValue)
    if vMatch:
      return vMatch.group(1)

  vCodeValue = fCaseInsensitiveValue(
    pRecord,
    ("code", "roomCode", "room_code", "slug", "roomSlug"),
  )
  if isinstance(vCodeValue, str):
    vCode = vCodeValue.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+", vCode):
      return vCode

  return ""


def fExtractPremium(pRecord: dict[str, object]) -> tuple[bool | None, str]:
  """Normalise Free, Premium and MAX catalogue access labels."""

  vTierValue = fCaseInsensitiveValue(
    pRecord,
    ("access", "accessTier", "subscription", "subscriptionTier", "subscriptionType", "tier", "plan"),
  )
  if vTierValue is not None:
    vTier = fNormaliseText(vTierValue).lower()
    if "free" in vTier:
      return False, "free"
    if "max" in vTier:
      return True, "max"
    if "premium" in vTier or "paid" in vTier or "subscriber" in vTier:
      return True, "premium"

  vPremiumValue = fCaseInsensitiveValue(
    pRecord,
    ("isPremium", "premium", "requiresSubscription", "requireSubscription", "paid"),
  )
  if isinstance(vPremiumValue, bool):
    return vPremiumValue, "premium" if vPremiumValue else "free"

  vFreeValue = fCaseInsensitiveValue(
    pRecord,
    ("isFree", "free", "freeToUse", "isFreeToUse"),
  )
  if isinstance(vFreeValue, bool):
    return not vFreeValue, "free" if vFreeValue else "premium"

  return None, "unknown"


def fNormaliseRoom(pRecord: dict[str, object]) -> dict[str, object] | None:
  """Convert one current API record to the stable room-cache schema."""

  vCode = fExtractRoomCode(pRecord)
  vTitleValue = fCaseInsensitiveValue(pRecord, ("title", "name", "roomTitle"))
  vDescriptionValue = fCaseInsensitiveValue(
    pRecord,
    ("description", "summary", "shortDescription", "roomDescription"),
  )
  vTitle = fNormaliseText(vTitleValue)
  vDescription = fNormaliseText(vDescriptionValue)

  if not vCode or not vTitle:
    return None

  vIsPremium, vAccessTier = fExtractPremium(pRecord)
  vDifficulty = fNormaliseText(
    fCaseInsensitiveValue(pRecord, ("difficulty", "difficultyLevel"))
  ).lower()
  vRoomType = fNormaliseText(
    fCaseInsensitiveValue(pRecord, ("roomType", "type", "contentType"))
  ).lower()

  return {
    "code": vCode,
    "title": vTitle,
    "description": vDescription,
    "url": f"{cBaseUrl}/room/{quote(vCode, safe='')}",
    "isPremium": vIsPremium,
    "accessTier": vAccessTier,
    "difficulty": vDifficulty,
    "roomType": vRoomType,
  }


def fRecordScore(pRecord: dict[str, object]) -> int:
  """Score whether a JSON object resembles a room catalogue entry."""

  sKeys = {str(vKey).lower() for vKey in pRecord}
  vScore = 0
  if sKeys.intersection({"code", "roomcode", "room_code", "slug", "roomslug"}):
    vScore += 5
  if sKeys.intersection({"title", "name", "roomtitle"}):
    vScore += 3
  if sKeys.intersection({"description", "summary", "shortdescription"}):
    vScore += 3
  if sKeys.intersection({"ispremium", "subscriptiontype", "accesstier", "access"}):
    vScore += 2
  return vScore


def fFindRoomRecordList(pPayload: object) -> list[dict[str, object]]:
  """Find the most room-like list in a version-tolerant API payload."""

  lCandidates: list[tuple[int, list[dict[str, object]]]] = []

  def fVisit(pValue: object) -> None:
    if isinstance(pValue, list):
      lRecords = [vItem for vItem in pValue if isinstance(vItem, dict)]
      if lRecords:
        vScore = sum(fRecordScore(vRecord) for vRecord in lRecords[:10])
        lCandidates.append((vScore, lRecords))
      for vItem in pValue:
        fVisit(vItem)
    elif isinstance(pValue, dict):
      for vChild in pValue.values():
        fVisit(vChild)

  fVisit(pPayload)
  if not lCandidates:
    return []

  lCandidates.sort(key=lambda pCandidate: (pCandidate[0], len(pCandidate[1])), reverse=True)
  vBestScore, lBestRecords = lCandidates[0]
  return lBestRecords if vBestScore >= 6 else []


def fFindTotal(pPayload: object) -> int | None:
  """Find a plausible pagination total in a nested API payload."""

  sTotalKeys = {
    "total",
    "totalcount",
    "totaldocs",
    "totalitems",
    "totalresults",
    "resultcount",
  }
  lValues: list[int] = []

  def fVisit(pValue: object) -> None:
    if isinstance(pValue, dict):
      for vKey, vChild in pValue.items():
        if str(vKey).lower() in sTotalKeys and isinstance(vChild, int) and vChild >= 0:
          lValues.append(vChild)
        else:
          fVisit(vChild)
    elif isinstance(pValue, list):
      for vChild in pValue:
        if isinstance(vChild, (dict, list)):
          fVisit(vChild)

  fVisit(pPayload)
  return max(lValues) if lValues else None


def fFindOfficialDescriptions(pPayload: object) -> list[str]:
  """Collect non-empty official description fields without retaining task data."""

  lDescriptions: list[str] = []

  def fVisit(pValue: object) -> None:
    if isinstance(pValue, dict):
      for vKey, vChild in pValue.items():
        if "description" in str(vKey).lower() and isinstance(vChild, str):
          vDescription = fNormaliseText(vChild)
          if vDescription and vDescription not in lDescriptions:
            lDescriptions.append(vDescription)
        elif isinstance(vChild, (dict, list)):
          fVisit(vChild)
    elif isinstance(pValue, list):
      for vChild in pValue:
        if isinstance(vChild, (dict, list)):
          fVisit(vChild)

  fVisit(pPayload)
  return lDescriptions


def fExtractModuleCode(pRecord: dict[str, object]) -> str:
  """Extract a canonical module code from a catalogue or detail record."""

  vUrlValue = fCaseInsensitiveValue(
    pRecord,
    ("moduleURL", "module_url", "url", "href", "link", "path", "modulePath"),
  )
  if isinstance(vUrlValue, str):
    vMatch = re.search(r"/module/([A-Za-z0-9_-]+)", vUrlValue)
    if vMatch:
      return vMatch.group(1)
    vCandidate = vUrlValue.strip().strip("/")
    if re.fullmatch(r"[A-Za-z0-9_-]+", vCandidate):
      return vCandidate

  vCodeValue = fCaseInsensitiveValue(
    pRecord,
    ("code", "moduleCode", "module_code", "slug", "moduleSlug"),
  )
  if isinstance(vCodeValue, str):
    vCode = vCodeValue.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+", vCode):
      return vCode

  return ""


def fExtractTagList(pRecord: dict[str, object], pKeys: tuple[str, ...]) -> list[str]:
  """Collect clean unique tag strings from tolerant catalogue tag fields."""

  lTags: list[str] = []
  for vKey in pKeys:
    vValue = fCaseInsensitiveValue(pRecord, (vKey,))
    if not isinstance(vValue, list):
      continue
    for vItem in vValue:
      if isinstance(vItem, dict):
        vItem = fCaseInsensitiveValue(vItem, ("name", "title", "label", "value"))
      vTag = fNormaliseText(vItem)
      if vTag and vTag not in lTags:
        lTags.append(vTag)
  return lTags


def fNormaliseModule(pRecord: dict[str, object]) -> dict[str, object] | None:
  """Convert one current module search record to the stable module schema."""

  vCode = fExtractModuleCode(pRecord)
  vTitle = fNormaliseText(fCaseInsensitiveValue(pRecord, ("title", "name", "moduleTitle")))
  if not vCode or not vTitle:
    return None

  vDescription = fNormaliseText(
    fCaseInsensitiveValue(
      pRecord,
      ("description", "summary", "shortDescription", "moduleDescription"),
    )
  )
  vDifficultyLevel = fCaseInsensitiveValue(pRecord, ("difficultyLevel", "difficulty_level"))
  vIsPremium, vAccessTier = fExtractPremium(pRecord)

  return {
    "code": vCode,
    "title": vTitle,
    "description": vDescription,
    "summary": "",
    "url": f"{cBaseUrl}/module/{quote(vCode, safe='')}",
    "tags": fExtractTagList(
      pRecord,
      ("tags", "skillTags", "technologyTags", "toolTags", "povTags"),
    ),
    "difficulty": fNormaliseText(
      fCaseInsensitiveValue(pRecord, ("difficulty", "difficultyName"))
    ).lower(),
    "difficultyLevel": (
      int(vDifficultyLevel) if isinstance(vDifficultyLevel, int) else None
    ),
    "moduleType": fNormaliseText(
      fCaseInsensitiveValue(pRecord, ("type", "moduleType", "contentType"))
    ).lower(),
    "isPremium": vIsPremium,
    "accessTier": vAccessTier,
  }


def fModuleRecordScore(pRecord: dict[str, object]) -> int:
  """Score whether a JSON object resembles a module catalogue entry."""

  sKeys = {str(vKey).lower() for vKey in pRecord}
  vScore = 0
  if sKeys.intersection({"code", "moduleurl", "modulecode", "slug"}):
    vScore += 5
  if sKeys.intersection({"title", "name", "moduletitle"}):
    vScore += 3
  if sKeys.intersection({"description", "summary", "shortdescription"}):
    vScore += 3
  if str(pRecord.get("kind", "")).lower() == "modules":
    vScore += 4
  return vScore


def fFindModuleRecordList(pPayload: object) -> list[dict[str, object]]:
  """Find the most module-like list in a version-tolerant API payload."""

  lCandidates: list[tuple[int, list[dict[str, object]]]] = []

  def fVisit(pValue: object) -> None:
    if isinstance(pValue, list):
      lRecords = [vItem for vItem in pValue if isinstance(vItem, dict)]
      if lRecords:
        vScore = sum(fModuleRecordScore(vRecord) for vRecord in lRecords[:10])
        lCandidates.append((vScore, lRecords))
      for vItem in pValue:
        fVisit(vItem)
    elif isinstance(pValue, dict):
      for vChild in pValue.values():
        fVisit(vChild)

  fVisit(pPayload)
  if not lCandidates:
    return []

  lCandidates.sort(
    key=lambda pCandidate: (pCandidate[0], len(pCandidate[1])),
    reverse=True,
  )
  vBestScore, lBestRecords = lCandidates[0]
  return lBestRecords if vBestScore >= 6 else []


def fNormaliseModuleRoom(pRecord: dict[str, object]) -> dict[str, object] | None:
  """Keep only the public room fields a module needs, never account progress."""

  vCode = fExtractRoomCode(pRecord)
  vTitle = fNormaliseText(fCaseInsensitiveValue(pRecord, ("title", "name", "roomTitle")))
  if not vCode or not vTitle:
    return None

  vFreeValue = fCaseInsensitiveValue(pRecord, ("free", "isFree", "freeToUse"))
  vOrder = fCaseInsensitiveValue(pRecord, ("id", "order", "position"))

  return {
    "code": vCode,
    "title": vTitle,
    "url": f"{cBaseUrl}/room/{quote(vCode, safe='')}",
    "isFree": vFreeValue if isinstance(vFreeValue, bool) else None,
    "roomType": fNormaliseText(
      fCaseInsensitiveValue(pRecord, ("type", "roomType", "contentType"))
    ).lower(),
    "order": int(vOrder) if isinstance(vOrder, int) else None,
  }


def fNormaliseModuleDetail(pPayload: object) -> dict[str, object]:
  """Convert one module detail payload into stable public metadata."""

  dData = pPayload.get("data") if isinstance(pPayload, dict) else None
  if not isinstance(dData, dict):
    dData = pPayload if isinstance(pPayload, dict) else {}

  lRooms: list[dict[str, object]] = []
  vRoomsValue = fCaseInsensitiveValue(dData, ("rooms", "roomList"))
  if isinstance(vRoomsValue, list):
    for dRoomRecord in vRoomsValue:
      if not isinstance(dRoomRecord, dict):
        continue
      dModuleRoom = fNormaliseModuleRoom(dRoomRecord)
      if dModuleRoom is not None:
        lRooms.append(dModuleRoom)
  lRooms.sort(
    key=lambda pRoom: (
      pRoom["order"] if isinstance(pRoom.get("order"), int) else 1_000_000,
      str(pRoom["title"]).casefold(),
    )
  )

  lKeyLearnings: list[str] = []
  dCompletion = fCaseInsensitiveValue(dData, ("completionMetadata",))
  if isinstance(dCompletion, dict):
    vLearnings = fCaseInsensitiveValue(dCompletion, ("keyLearnings", "learnings"))
    if isinstance(vLearnings, list):
      for vLearning in vLearnings:
        vText = fNormaliseText(vLearning)
        if vText and vText not in lKeyLearnings:
          lKeyLearnings.append(vText)

  def fRelatedCodes(pKey: str) -> list[str]:
    lCodes: list[str] = []
    vValue = fCaseInsensitiveValue(dData, (pKey,))
    if isinstance(vValue, list):
      for vItem in vValue:
        if isinstance(vItem, str):
          vCode = vItem.strip()
        elif isinstance(vItem, dict):
          vCode = fExtractModuleCode(vItem)
        else:
          continue
        if vCode and vCode not in lCodes:
          lCodes.append(vCode)
    return lCodes

  vTotalMinutes = fCaseInsensitiveValue(
    dData,
    ("totalTimeToCompleteMinutes", "timeToCompleteMinutes", "totalMinutes"),
  )
  vFreeRoomCount = sum(1 for dRoom in lRooms if dRoom["isFree"] is True)
  vPaidRoomCount = sum(1 for dRoom in lRooms if dRoom["isFree"] is False)
  if lRooms and vPaidRoomCount == 0:
    vIsPremium, vAccessTier = False, "free"
  elif vPaidRoomCount:
    vIsPremium, vAccessTier = True, "premium"
  else:
    vIsPremium, vAccessTier = None, "unknown"

  return {
    "summary": fNormaliseText(fCaseInsensitiveValue(dData, ("summary", "subtitle"))),
    "detailDescription": fNormaliseText(
      fCaseInsensitiveValue(dData, ("description", "moduleDescription"))
    ),
    "tags": fExtractTagList(
      dData,
      ("tags", "skillTags", "technologyTags", "toolTags", "povTags"),
    ),
    "rooms": lRooms,
    "roomCount": len(lRooms),
    "freeRoomCount": vFreeRoomCount,
    "paidRoomCount": vPaidRoomCount,
    "isPremium": vIsPremium,
    "accessTier": vAccessTier,
    "totalTimeMinutes": int(vTotalMinutes) if isinstance(vTotalMinutes, int) else None,
    "prerequisites": fRelatedCodes("prerequisites"),
    "nextSteps": fRelatedCodes("nextSteps"),
    "keyLearnings": lKeyLearnings,
    "isPublic": bool(fCaseInsensitiveValue(dData, ("public", "isPublic")) or False),
  }


class TryHackMeBrowserClient:
  """Own one isolated Chromium context populated with a source profile's cookies."""

  def __init__(
    self,
    pCookies: list[dict[str, object]],
    pHeaded: bool = False,
    pRequestTimeoutSeconds: float = 45.0,
  ) -> None:
    self.lCookies = pCookies
    self.vHeaded = pHeaded
    self.vRequestTimeoutMs = int(pRequestTimeoutSeconds * 1000)
    self.vPlaywright = None
    self.vBrowser = None
    self.vContext = None
    self.vPage = None

  def mStart(self) -> None:
    """Launch the isolated browser and prime TryHackMe's first-party context."""

    try:
      from playwright.sync_api import sync_playwright
    except ImportError as vError:
      raise TryHackMeClientError(
        "The Python package 'playwright' is required."
      ) from vError

    fRequireUsableSocketPath()
    cTempRoot.mkdir(mode=0o700, parents=True, exist_ok=True)
    tempfile.tempdir = str(cTempRoot)
    self.vPlaywright = sync_playwright().start()
    try:
      self.vBrowser = self.vPlaywright.chromium.launch(
        executable_path=fFindChromiumExecutable(),
        headless=not self.vHeaded,
        args=[
          "--disable-blink-features=AutomationControlled",
          "--disable-crash-reporter",
          "--disable-crashpad",
          "--disable-dev-shm-usage",
          "--no-first-run",
        ],
        env={
          **dict(os.environ),
          "TEMP": str(cTempRoot),
          "TMP": str(cTempRoot),
        },
      )
      self.vContext = self.vBrowser.new_context(
        locale="en-GB",
        user_agent=cUserAgent,
        viewport={"width": 1280, "height": 900},
      )
      self.vContext.add_cookies(self.lCookies)
      self.vPage = self.vContext.new_page()
      self.vPage.set_default_timeout(self.vRequestTimeoutMs)
      self.mPrimeContext()
    except Exception as vError:
      self.mClose()
      if isinstance(vError, TryHackMeClientError):
        raise
      raise TryHackMeClientError(
        "Could not launch the isolated Chromium browser."
      ) from vError

  def mPrimeContext(self) -> None:
    """Allow the browser to complete the platform's JavaScript checkpoint."""

    if self.vPage is None:
      raise TryHackMeClientError("The browser context has not been started.")

    try:
      self.vPage.goto(
        cPrimeUrl,
        wait_until="domcontentloaded",
        timeout=self.vRequestTimeoutMs,
      )
      vDeadline = time.monotonic() + 45
      while time.monotonic() < vDeadline:
        vContent = self.vPage.content().lower()
        if (
          "vercel.link/security-checkpoint" not in vContent
          and "security checkpoint" not in vContent
        ):
          return
        self.vPage.wait_for_timeout(1000)
      raise SecurityCheckpointError(
        "TryHackMe's security checkpoint did not complete. Retry with a visible browser."
      )
    except SecurityCheckpointError:
      raise
    except Exception as vError:
      raise TryHackMeClientError(
        "Could not initialise the TryHackMe browser context."
      ) from vError

  def mFetchJson(self, pUrl: str) -> tuple[int, object, str]:
    """Fetch same-origin JSON with the authenticated browser context."""

    if self.vPage is None:
      raise TryHackMeClientError("The browser context has not been started.")

    try:
      dResponse = self.vPage.evaluate(
        cFetchScript,
        {"pUrl": pUrl, "pTimeoutMs": self.vRequestTimeoutMs},
      )
    except Exception as vError:
      raise TryHackMeClientError(f"GET failed for {pUrl}.") from vError

    vStatus = int(dResponse.get("status", 0))
    if vStatus == 429:
      raise RateLimitError(
        "TryHackMe rate-limited the request.",
        fParseRetryAfter(str(dResponse.get("retryAfter", ""))),
      )

    vBody = str(dResponse.get("body", ""))
    try:
      vPayload = json.loads(vBody)
    except json.JSONDecodeError as vError:
      if "security checkpoint" in vBody.lower() or "vercel.link/security-checkpoint" in vBody:
        raise SecurityCheckpointError(
          "TryHackMe returned its browser security checkpoint instead of JSON."
        ) from vError
      raise TryHackMeClientError(
        f"TryHackMe returned non-JSON content with HTTP {vStatus}."
      ) from vError

    return vStatus, vPayload, str(dResponse.get("finalUrl", pUrl))

  def mVerifySession(self) -> bool:
    """Confirm that the imported cookies identify an authenticated user."""

    try:
      vStatus, vPayload, vFinalUrl = self.mFetchJson(cSessionEndpoint)
      if vStatus in (401, 403) or "/login" in vFinalUrl:
        return False
      if vStatus != 200 or not isinstance(vPayload, dict):
        return False

      vPayloadText = json.dumps(vPayload, ensure_ascii=True).lower()
      if any(
        vMarker in vPayloadText
        for vMarker in ("unauthorised", "unauthorized", "not authenticated", "login required")
      ):
        return False
      return True
    except AuthenticationError:
      return False

  def mFetchCatalogue(
    self,
    pDelaySeconds: float,
    pProgress: Callable[[int, int, int | None], None] | None = None,
    pPageSize: int = 24,
  ) -> list[dict[str, object]]:
    """Fetch every current room page and return a deduplicated catalogue."""

    dRooms: dict[str, dict[str, object]] = {}
    vPageNumber = 1
    vTotal: int | None = None
    vEmptyPages = 0
    vLimiter = AdaptiveRateLimiter(pDelaySeconds, pMinimumDelay=0.75)

    while vPageNumber <= 500:
      if vPageNumber > 1:
        vLimiter.mWait()

      dQuery = {
        "kind": "rooms",
        "difficulty": "all",
        "order": "newest",
        "roomType": "all",
        "page": vPageNumber,
        "limit": pPageSize,
      }
      vUrl = f"{cCatalogueEndpoint}?{urlencode(dQuery)}"

      try:
        vStatus, vPayload, vFinalUrl = self.mFetchJson(vUrl)
      except RateLimitError as vError:
        vWaitFor = vLimiter.mLimited(vError.vRetryAfter)
        time.sleep(vWaitFor)
        continue

      if vStatus in (401, 403) or "/login" in vFinalUrl:
        raise AuthenticationError("The TryHackMe session expired while reading the catalogue.")
      if vStatus != 200:
        raise TryHackMeClientError(
          f"The catalogue endpoint returned HTTP {vStatus} on page {vPageNumber}."
        )

      lRawRecords = fFindRoomRecordList(vPayload)
      if not lRawRecords:
        vEmptyPages += 1
        if vEmptyPages >= 1:
          break
      else:
        vEmptyPages = 0

      vNewRooms = 0
      for dRawRecord in lRawRecords:
        dRoom = fNormaliseRoom(dRawRecord)
        if dRoom is None:
          continue
        vCode = str(dRoom["code"])
        if vCode not in dRooms:
          vNewRooms += 1
        dRooms[vCode] = dRoom

      vTotal = fFindTotal(vPayload) or vTotal
      vLimiter.mSuccess()
      if pProgress is not None:
        pProgress(vPageNumber, len(dRooms), vTotal)

      if vTotal is not None and len(dRooms) >= vTotal:
        break
      if vTotal is None and len(lRawRecords) < pPageSize:
        break
      if vNewRooms == 0 and vPageNumber > 1:
        break

      vPageNumber += 1

    if not dRooms:
      raise CatalogueFormatError(
        "No room records could be extracted from TryHackMe's current catalogue response."
      )
    if vPageNumber > 500:
      raise TryHackMeClientError(
        "Catalogue pagination exceeded 500 pages; stopping to avoid unbounded requests."
      )

    return sorted(dRooms.values(), key=lambda pRoom: str(pRoom["title"]).casefold())

  def mFetchModuleCatalogue(
    self,
    pDelaySeconds: float,
    pProgress: Callable[[int, int, int | None], None] | None = None,
    pPageSize: int = 100,
    pMaximumPasses: int = 4,
  ) -> tuple[list[dict[str, object]], int | None]:
    """Fetch the module catalogue, repeating passes until its own total is met.

    The search endpoint paginates over a non-deterministic index: consecutive
    pages overlap and a single pass can silently return only part of the
    catalogue. Repeating the pass and unioning the results converges on the
    total the endpoint itself reports, so the caller also receives that total
    and can tell whether the discovery was complete.
    """

    dModules: dict[str, dict[str, object]] = {}
    vTotal: int | None = None
    vLimiter = AdaptiveRateLimiter(pDelaySeconds, pMinimumDelay=0.75)
    vPassNumber = 0
    vRequestNumber = 0

    while vPassNumber < pMaximumPasses:
      vPassNumber += 1
      vPageNumber = 1

      while vPageNumber <= 100:
        if vRequestNumber > 0:
          vLimiter.mWait()
        vRequestNumber += 1

        dQuery = {
          "kind": "modules",
          "page": vPageNumber,
          "limit": pPageSize,
        }
        vUrl = f"{cCatalogueEndpoint}?{urlencode(dQuery)}"

        try:
          vStatus, vPayload, vFinalUrl = self.mFetchJson(vUrl)
        except RateLimitError as vError:
          vWaitFor = vLimiter.mLimited(vError.vRetryAfter)
          time.sleep(vWaitFor)
          continue

        if vStatus in (401, 403) or "/login" in vFinalUrl:
          raise AuthenticationError(
            "The TryHackMe session expired while reading the module catalogue."
          )
        if vStatus != 200:
          raise TryHackMeClientError(
            f"The module catalogue endpoint returned HTTP {vStatus} on page {vPageNumber}."
          )

        lRawRecords = fFindModuleRecordList(vPayload)
        if not lRawRecords:
          break

        for dRawRecord in lRawRecords:
          dModule = fNormaliseModule(dRawRecord)
          if dModule is None:
            continue
          dModules[str(dModule["code"])] = dModule

        vTotal = fFindTotal(vPayload) or vTotal
        vLimiter.mSuccess()
        if pProgress is not None:
          pProgress(vPassNumber, len(dModules), vTotal)

        if len(lRawRecords) < pPageSize:
          break

        vPageNumber += 1

      if vPageNumber > 100:
        raise TryHackMeClientError(
          "Module pagination exceeded 100 pages; stopping to avoid unbounded requests."
        )
      if vTotal is not None and len(dModules) >= vTotal:
        break

    if not dModules:
      raise CatalogueFormatError(
        "No module records could be extracted from TryHackMe's current search response."
      )

    lModules = sorted(
      dModules.values(),
      key=lambda pModule: str(pModule["title"]).casefold(),
    )
    return lModules, vTotal

  def mFetchModuleData(self, pCode: str) -> dict[str, object]:
    """Read one module's official detail and report whether it still exists."""

    vUrl = f"{cModuleDataEndpoint}?{urlencode({'moduleURL': pCode})}"
    vStatus, vPayload, vFinalUrl = self.mFetchJson(vUrl)

    if vStatus in (401, 403) or "/login" in vFinalUrl:
      raise AuthenticationError(
        "The TryHackMe session expired while reading module details."
      )

    dDetail = fNormaliseModuleDetail(vPayload) if vStatus == 200 else None
    if dDetail is not None and not dDetail["rooms"] and not dDetail["summary"]:
      dDetail = None

    return {
      "checkedAt": fIsoNow(),
      "httpStatus": vStatus,
      "finalUrl": f"{cBaseUrl}/module/{quote(pCode, safe='')}",
      "valid": vStatus == 200 and dDetail is not None,
      "detail": dDetail,
    }

  def mFetchRoomDescription(self, pUrl: str) -> str:
    """Read an official page description when the catalogue field is empty."""

    if self.vContext is None:
      raise TryHackMeClientError("The browser context has not been started.")

    vRoomCode = fRoomCodeFromUrl(pUrl)
    if vRoomCode:
      try:
        vStatus, vTasksPayload, vFinalUrl = self.mFetchJson(
          f"{cTasksEndpoint}?{urlencode({'roomCode': vRoomCode})}"
        )
        if vStatus == 200 and "/login" not in vFinalUrl:
          for vDescription in fFindOfficialDescriptions(vTasksPayload):
            vLowerDescription = vDescription.lower()
            if "set up your virtual environment" in vLowerDescription:
              continue
            if 20 <= len(vDescription) <= 1000:
              return vDescription
      except TryHackMeClientError:
        pass

    vRoomPage = self.vContext.new_page()
    try:
      vResponse = vRoomPage.goto(
        pUrl,
        wait_until="domcontentloaded",
        timeout=self.vRequestTimeoutMs,
      )
      if vResponse is None or vResponse.status != 200:
        return ""

      for vSelector in (
        'meta[name="description"]',
        'meta[property="og:description"]',
        'meta[name="twitter:description"]',
      ):
        vElement = vRoomPage.locator(vSelector).first
        if vElement.count() == 0:
          continue
        vDescription = fNormaliseText(vElement.get_attribute("content"))
        vLowerDescription = vDescription.lower()
        if (
          vDescription
          and "gamified, hands-on cyber security training platform" not in vLowerDescription
          and "free online cyber security training" not in vLowerDescription
        ):
          return vDescription

      vRoomPage.wait_for_timeout(1500)
      lExcludedFragments = [
        "answer the questions",
        "free online cyber security training",
        "gamified, hands-on cyber security training platform",
        "log in",
        "login",
        "ready to learn cyber security",
        "set up your virtual environment",
        "signup",
        "start lab machine",
        "task includes a deployable machine",
        "to access material",
        "user flag",
        "root flag",
      ]
      lDescriptions: list[str] = []
      for vParagraph in vRoomPage.locator("main p").all_inner_texts():
        vDescription = fNormaliseText(vParagraph)
        vLowerDescription = vDescription.lower()
        if not 20 <= len(vDescription) <= 500:
          continue
        if any(vFragment in vLowerDescription for vFragment in lExcludedFragments):
          continue
        lDescriptions.append(vDescription)
        if len(lDescriptions) >= 2:
          break
      if lDescriptions:
        return " ".join(lDescriptions)

      lBodyLines = [
        fNormaliseText(vLine)
        for vLine in vRoomPage.locator("body").inner_text().splitlines()
        if fNormaliseText(vLine)
      ]
      for vAnswerIndex, vLine in enumerate(lBodyLines):
        if "answer the questions below" not in vLine.lower():
          continue
        vStartIndex = max(0, vAnswerIndex - 12)
        for vIndex in range(vAnswerIndex - 1, vStartIndex - 1, -1):
          if "start lab machine" in lBodyLines[vIndex].lower():
            vStartIndex = vIndex + 1
            break
        lDescriptions = []
        for vCandidate in lBodyLines[vStartIndex:vAnswerIndex]:
          vLowerCandidate = vCandidate.lower()
          if not 20 <= len(vCandidate) <= 500:
            continue
          if any(vFragment in vLowerCandidate for vFragment in lExcludedFragments):
            continue
          lDescriptions.append(vCandidate)
        if lDescriptions:
          return " ".join(lDescriptions[-3:])
      return ""
    except Exception:
      return ""
    finally:
      vRoomPage.close()

  def mQuickGet(self, pUrl: str) -> dict[str, object]:
    """Issue one lightweight GET and cancel its body after receiving headers."""

    if self.vPage is None:
      raise TryHackMeClientError("The browser context has not been started.")

    try:
      dResponse = self.vPage.evaluate(
        cQuickGetScript,
        {"pUrl": pUrl, "pTimeoutMs": self.vRequestTimeoutMs},
      )
    except Exception as vError:
      raise TryHackMeClientError(f"GET failed for {pUrl}.") from vError

    vStatus = int(dResponse.get("status", 0))
    if vStatus == 429:
      raise RateLimitError(
        "TryHackMe rate-limited room URL validation.",
        fParseRetryAfter(str(dResponse.get("retryAfter", ""))),
      )

    vFinalUrl = str(dResponse.get("finalUrl", pUrl))
    return {
      "status": vStatus,
      "finalUrl": vFinalUrl,
      "valid": vStatus == 200 and "/login" not in vFinalUrl,
      "checkedAt": fIsoNow(),
    }

  def mClose(self) -> None:
    """Close every Playwright object without retaining imported cookies."""

    try:
      if self.vContext is not None:
        self.vContext.close()
    except Exception:
      pass
    finally:
      self.vContext = None
      self.vPage = None

    try:
      if self.vBrowser is not None:
        self.vBrowser.close()
    except Exception:
      pass
    finally:
      self.vBrowser = None

    try:
      if self.vPlaywright is not None:
        self.vPlaywright.stop()
    except Exception:
      pass
    finally:
      self.vPlaywright = None
      self.lCookies.clear()


def fRoomCodeFromUrl(pUrl: str) -> str:
  """Return a room code from a canonical TryHackMe URL."""

  vParsedUrl = urlparse(pUrl)
  vMatch = re.fullmatch(r"/room/([A-Za-z0-9_-]+)", vParsedUrl.path.rstrip("/"))
  return vMatch.group(1) if vMatch else ""
