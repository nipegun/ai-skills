#!/usr/bin/env python3

"""Build, refresh and validate the TryHackMe room catalogue on macOS."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time

from browser_sessions import fFindSessionCandidates
from tryhackme_client import (
  AdaptiveRateLimiter,
  AuthenticationError,
  RateLimitError,
  SecurityCheckpointError,
  TryHackMeBrowserClient,
  TryHackMeClientError,
  cCatalogueEndpoint,
  fIsoNow,
  fRoomCodeFromUrl,
)


cSkillRoot = Path(__file__).resolve().parent.parent.parent
cI18nRoot = cSkillRoot / "i18n"
cCachePath = cSkillRoot / "thm-rooms" / "all-rooms.json"
cTempRoot = cSkillRoot.parent / "_" / "temp" / "thm"
cLocales = ("en-GB", "en-US", "es-AR", "es-ES")
cBrowsers = ("auto", "firefox", "safari", "chrome", "chromium")
cSchemaVersion = 2
cLegacySchemaVersion = 1


class CacheError(RuntimeError):
  """Raised when all-rooms.json does not match the supported schema."""


class Localiser:
  """Load user-facing strings with en-GB as the canonical fallback."""

  def __init__(self, pLocale: str) -> None:
    self.vLocale = pLocale if pLocale in cLocales else "en-GB"
    self.dFallback = self.mLoad("en-GB")
    self.dStrings = self.mLoad(self.vLocale)

  def mLoad(self, pLocale: str) -> dict[str, str]:
    vPath = cI18nRoot / f"{pLocale}.json"
    try:
      with vPath.open("r", encoding="utf-8") as vFile:
        vPayload = json.load(vFile)
    except (OSError, json.JSONDecodeError) as vError:
      raise CacheError(f"Could not load translation file {vPath}: {vError}") from vError
    if not isinstance(vPayload, dict):
      raise CacheError(f"Translation file {vPath} must contain a JSON object.")
    return {str(vKey): str(vValue) for vKey, vValue in vPayload.items()}

  def mText(self, pKey: str, **pValues: object) -> str:
    vTemplate = self.dStrings.get(pKey, self.dFallback.get(pKey, pKey))
    try:
      return vTemplate.format(**pValues)
    except (KeyError, ValueError):
      return vTemplate


def fPreparseLocale(pArguments: list[str]) -> str:
  """Read --locale early enough to localise argparse help."""

  for vIndex, vArgument in enumerate(pArguments):
    if vArgument.startswith("--locale="):
      return vArgument.split("=", 1)[1]
    if vArgument == "--locale" and vIndex + 1 < len(pArguments):
      return pArguments[vIndex + 1]
  return "en-GB"


def fBuildParser(pLocaliser: Localiser) -> argparse.ArgumentParser:
  """Create the localised command-line interface."""

  vParser = argparse.ArgumentParser(description=pLocaliser.mText("description"))
  vParser.add_argument(
    "--locale",
    choices=cLocales,
    default=pLocaliser.vLocale,
    help=pLocaliser.mText("arg_locale"),
  )
  vParser.add_argument(
    "--browser",
    choices=cBrowsers,
    default="auto",
    help=pLocaliser.mText("arg_browser"),
  )
  vParser.add_argument(
    "--headed",
    action="store_true",
    help=pLocaliser.mText("arg_headed"),
  )
  vParser.add_argument(
    "--catalogue-delay",
    type=float,
    default=1.25,
    help=pLocaliser.mText("arg_catalogue_delay"),
  )
  vParser.add_argument(
    "--validation-delay",
    type=float,
    default=1.25,
    help=pLocaliser.mText("arg_validation_delay"),
  )
  vParser.add_argument(
    "--skip-url-validation",
    action="store_true",
    help=pLocaliser.mText("arg_skip_validation"),
  )
  return vParser


def fMigrateCache(pCache: dict[str, object]) -> dict[str, object]:
  """Migrate schema version 1 without discarding public room metadata."""

  vSchemaVersion = int(pCache.get("schemaVersion", 0))
  if vSchemaVersion == cSchemaVersion:
    return pCache
  if vSchemaVersion != cLegacySchemaVersion:
    raise CacheError("The room cache schema version is not supported.")

  vSeenAt = str(pCache.get("lastCataloguedAt") or fIsoNow())
  for dRoom in pCache.get("rooms", []):
    if not isinstance(dRoom, dict):
      continue
    dRoom["listed"] = True
    dRoom["firstSeenAt"] = vSeenAt
    dRoom["lastSeenAt"] = vSeenAt

  pCache["schemaVersion"] = cSchemaVersion
  pCache["lastDiscoveryAt"] = pCache.get("lastCataloguedAt")
  pCache["listedRoomCount"] = len(pCache.get("rooms", []))
  return pCache


def fLoadCache() -> dict[str, object] | None:
  """Load and structurally validate all-rooms.json when present."""

  if not cCachePath.is_file():
    return None

  try:
    with cCachePath.open("r", encoding="utf-8") as vFile:
      vPayload = json.load(vFile)
  except (OSError, json.JSONDecodeError) as vError:
    raise CacheError(f"Could not read {cCachePath}: {vError}") from vError

  if not isinstance(vPayload, dict):
    raise CacheError("The room cache root must be a JSON object.")
  if not isinstance(vPayload.get("rooms"), list):
    raise CacheError("The room cache must contain a rooms list.")
  vPayload = fMigrateCache(vPayload)

  vDefaultSeenAt = str(
    vPayload.get("lastDiscoveryAt")
    or vPayload.get("lastCataloguedAt")
    or fIsoNow()
  )

  for vIndex, dRoom in enumerate(vPayload["rooms"]):
    if not isinstance(dRoom, dict):
      raise CacheError(f"Room entry {vIndex} is not a JSON object.")
    for vRequiredKey in ("code", "title", "description", "url", "isPremium"):
      if vRequiredKey not in dRoom:
        raise CacheError(f"Room entry {vIndex} is missing {vRequiredKey}.")
    if not isinstance(dRoom.get("listed", True), bool):
      raise CacheError(f"Room entry {vIndex} has an invalid listed value.")
    dRoom.setdefault("listed", True)
    dRoom.setdefault("firstSeenAt", vDefaultSeenAt)
    dRoom.setdefault("lastSeenAt", vDefaultSeenAt)

  vPayload["roomCount"] = len(vPayload["rooms"])
  vPayload["listedRoomCount"] = sum(
    1 for dRoom in vPayload["rooms"] if dRoom.get("listed") is True
  )

  return vPayload


def fSaveCache(pCache: dict[str, object]) -> None:
  """Atomically save public room metadata without session cookies."""

  cCachePath.parent.mkdir(parents=True, exist_ok=True)
  cTempRoot.mkdir(mode=0o700, parents=True, exist_ok=True)
  vTemporaryPath: Path | None = None

  try:
    vDescriptor, vTemporaryName = tempfile.mkstemp(
      prefix="all-rooms-",
      suffix=".json",
      dir=cTempRoot,
      text=True,
    )
    vTemporaryPath = Path(vTemporaryName)
    with os.fdopen(vDescriptor, "w", encoding="utf-8") as vFile:
      json.dump(pCache, vFile, ensure_ascii=False, indent=2, sort_keys=False)
      vFile.write("\n")
      vFile.flush()
      os.fsync(vFile.fileno())
    os.chmod(vTemporaryPath, 0o600)
    os.replace(vTemporaryPath, cCachePath)
    os.chmod(cCachePath, 0o644)
    vTemporaryPath = None
  except OSError as vError:
    raise CacheError(f"Could not save {cCachePath}: {vError}") from vError
  finally:
    if vTemporaryPath is not None and vTemporaryPath.exists():
      vTemporaryPath.unlink(missing_ok=True)


def fParseTimestamp(pValue: object) -> datetime | None:
  """Parse an ISO-8601 cache timestamp as UTC."""

  if not isinstance(pValue, str) or not pValue:
    return None
  try:
    vTimestamp = datetime.fromisoformat(pValue.replace("Z", "+00:00"))
    if vTimestamp.tzinfo is None:
      vTimestamp = vTimestamp.replace(tzinfo=timezone.utc)
    return vTimestamp.astimezone(timezone.utc)
  except ValueError:
    return None


def fMergeCatalogue(
  pExistingCache: dict[str, object] | None,
  pFreshRooms: list[dict[str, object]],
) -> tuple[dict[str, object], list[str], list[str], list[str]]:
  """Union a fresh discovery into the cache without losing historical rooms."""

  dExistingRooms: dict[str, dict[str, object]] = {}
  if pExistingCache is not None:
    for dRoom in pExistingCache.get("rooms", []):
      if isinstance(dRoom, dict) and isinstance(dRoom.get("code"), str):
        dExistingRooms[str(dRoom["code"])] = dRoom

  vDiscoveredAt = fIsoNow()
  sFreshCodes = {str(dRoom["code"]) for dRoom in pFreshRooms}
  dMergedRooms: dict[str, dict[str, object]] = {}
  lNewCodes: list[str] = []
  lRelistedCodes: list[str] = []
  lUnlistedCodes: list[str] = []

  for vCode, dExistingRoom in dExistingRooms.items():
    dMergedRoom = dict(dExistingRoom)
    if vCode not in sFreshCodes:
      if dMergedRoom.get("listed") is not False:
        lUnlistedCodes.append(vCode)
      dMergedRoom["listed"] = False
    dMergedRooms[vCode] = dMergedRoom

  for dFreshRoom in pFreshRooms:
    vCode = str(dFreshRoom["code"])
    dExistingRoom = dMergedRooms.get(vCode)
    if dExistingRoom is None:
      dMergedRoom = dict(dFreshRoom)
      dMergedRoom["firstSeenAt"] = vDiscoveredAt
      lNewCodes.append(vCode)
    else:
      vWasListed = dExistingRoom.get("listed") is not False
      dValidation = dExistingRoom.get("validation")
      dMergedRoom = dict(dExistingRoom)
      dMergedRoom.update(dFreshRoom)
      if isinstance(dValidation, dict):
        dMergedRoom["validation"] = dValidation
      dMergedRoom.setdefault("firstSeenAt", vDiscoveredAt)
      if not vWasListed:
        lRelistedCodes.append(vCode)
    dMergedRoom["listed"] = True
    dMergedRoom["lastSeenAt"] = vDiscoveredAt
    dMergedRooms[vCode] = dMergedRoom

  vValidationState = (
    pExistingCache.get("validationState") if pExistingCache is not None else None
  )
  if vValidationState is None and pExistingCache is not None:
    lExistingRooms = [
      vRoom for vRoom in pExistingCache.get("rooms", []) if isinstance(vRoom, dict)
    ]
    vLastValidatedAt = pExistingCache.get("lastValidatedAt")
    if (
      lExistingRooms
      and all(isinstance(vRoom.get("validation"), dict) for vRoom in lExistingRooms)
      and fParseTimestamp(vLastValidatedAt) is not None
    ):
      vValidationState = {
        "status": "complete",
        "startedAt": vLastValidatedAt,
        "completedAt": vLastValidatedAt,
        "completed": len(lExistingRooms),
        "total": len(lExistingRooms),
      }

  lMergedRooms = sorted(
    dMergedRooms.values(),
    key=lambda pRoom: str(pRoom["title"]).casefold(),
  )
  dMergedCache = dict(pExistingCache) if pExistingCache is not None else {}
  dMergedCache.update({
    "schemaVersion": cSchemaVersion,
    "source": cCatalogueEndpoint,
    "lastCataloguedAt": vDiscoveredAt,
    "lastDiscoveryAt": vDiscoveredAt,
    "validationState": vValidationState,
    "discoveryState": {
      "discoveredAt": vDiscoveredAt,
      "newRoomCount": len(lNewCodes),
      "newRoomCodes": sorted(lNewCodes),
      "relistedRoomCount": len(lRelistedCodes),
      "relistedRoomCodes": sorted(lRelistedCodes),
      "unlistedRoomCount": len(lUnlistedCodes),
      "unlistedRoomCodes": sorted(lUnlistedCodes),
    },
    "roomCount": len(lMergedRooms),
    "listedRoomCount": sum(
      1 for dRoom in lMergedRooms if dRoom.get("listed") is True
    ),
    "rooms": lMergedRooms,
  })
  return dMergedCache, lNewCodes, lRelistedCodes, lUnlistedCodes


def fOpenAuthenticatedClient(
  pBrowser: str,
  pHeaded: bool,
  pLocaliser: Localiser,
) -> tuple[TryHackMeBrowserClient, dict[str, object]]:
  """Try each candidate profile until TryHackMe confirms authentication."""

  print(pLocaliser.mText("session_search"), flush=True)
  lCandidates, lErrors = fFindSessionCandidates(pBrowser)

  for dError in lErrors:
    print(
      pLocaliser.mText(
        "profile_error",
        browser=dError["browser"],
        profile=dError["profile"],
        error=dError["error"],
      ),
      flush=True,
    )

  for dCandidate in lCandidates:
    print(
      pLocaliser.mText(
        "session_candidate",
        browser=dCandidate["browser"],
        profile=dCandidate["profile"],
        count=len(dCandidate["cookies"]),
      ),
      flush=True,
    )
    vClient = TryHackMeBrowserClient(
      pCookies=dCandidate["cookies"],
      pHeaded=pHeaded,
    )
    vKeepClient = False
    try:
      vClient.mStart()
      if vClient.mVerifySession():
        print(
          pLocaliser.mText(
            "session_valid",
            browser=dCandidate["browser"],
            profile=dCandidate["profile"],
          ),
          flush=True,
        )
        lCandidates.clear()
        vKeepClient = True
        return vClient, dCandidate
      print(
        pLocaliser.mText(
          "session_invalid",
          browser=dCandidate["browser"],
          profile=dCandidate["profile"],
        ),
        flush=True,
      )
    except (SecurityCheckpointError, TryHackMeClientError) as vError:
      print(
        pLocaliser.mText(
          "profile_error",
          browser=dCandidate["browser"],
          profile=dCandidate["profile"],
          error=str(vError),
        ),
        flush=True,
      )
    finally:
      if not vKeepClient:
        vClient.mClose()

  lCandidates.clear()
  raise AuthenticationError(pLocaliser.mText("no_session_modern"))


def fDiscoverCatalogue(
  pClient: TryHackMeBrowserClient,
  pCache: dict[str, object] | None,
  pDelaySeconds: float,
  pLocaliser: Localiser,
) -> tuple[dict[str, object], list[str], list[str]]:
  """Discover the complete live catalogue and append newly seen rooms."""

  def fProgress(pPage: int, pCount: int, pTotal: int | None) -> None:
    vTotalText = ""
    print(
      pLocaliser.mText(
        "catalogue_page",
        page=pPage,
        count=pCount,
        total=vTotalText,
      ),
      flush=True,
    )

  print(pLocaliser.mText("discovery_start"), flush=True)
  lFreshRooms = pClient.mFetchCatalogue(
    pDelaySeconds=max(0.75, pDelaySeconds),
    pProgress=fProgress,
  )
  for dRoom in lFreshRooms:
    if not str(dRoom.get("description", "")).strip():
      vDescription = pClient.mFetchRoomDescription(str(dRoom["url"]))
      if vDescription:
        dRoom["description"] = vDescription
  dMergedCache, lNewCodes, lRelistedCodes, lUnlistedCodes = fMergeCatalogue(
    pCache,
    lFreshRooms,
  )
  fSaveCache(dMergedCache)
  print(
    pLocaliser.mText("discovery_complete", count=len(lFreshRooms)),
    flush=True,
  )
  if lNewCodes:
    print(pLocaliser.mText("discovery_new", count=len(lNewCodes)), flush=True)
  else:
    print(pLocaliser.mText("discovery_no_new"), flush=True)
  if lRelistedCodes:
    print(
      pLocaliser.mText("discovery_relisted", count=len(lRelistedCodes)),
      flush=True,
    )
  if lUnlistedCodes:
    print(
      pLocaliser.mText("discovery_unlisted", count=len(lUnlistedCodes)),
      flush=True,
    )
  print(
    pLocaliser.mText(
      "catalogue_saved",
      count=len(dMergedCache["rooms"]),
      path=cCachePath,
    ),
    flush=True,
  )
  return dMergedCache, lNewCodes, lRelistedCodes


def fValidateCatalogueUrls(
  pClient: TryHackMeBrowserClient,
  pCache: dict[str, object],
  pDelaySeconds: float,
  pLocaliser: Localiser,
  pRoomCodes: set[str] | None = None,
  pScope: str = "all",
) -> dict[str, object]:
  """Validate all cached URLs or a selected set with adaptive GET requests."""

  lAllRooms = [
    dRoom for dRoom in pCache.get("rooms", []) if isinstance(dRoom, dict)
  ]
  lRooms = [
    dRoom
    for dRoom in lAllRooms
    if pRoomCodes is None or str(dRoom.get("code", "")) in pRoomCodes
  ]
  vCount = len(lRooms)
  if vCount == 0:
    return pCache

  lSelectedCodes = sorted(str(dRoom["code"]) for dRoom in lRooms)
  vValidCount = 0
  vInvalidCount = 0
  vConsecutiveLimitedRooms = 0
  vLimiter = AdaptiveRateLimiter(max(0.75, pDelaySeconds), pMinimumDelay=0.75)
  dPreviousState = pCache.get("validationState")
  vResumeRun = (
    isinstance(dPreviousState, dict)
    and dPreviousState.get("status") == "in_progress"
    and dPreviousState.get("scope") == pScope
    and dPreviousState.get("total") == vCount
    and (
      pScope == "all"
      or dPreviousState.get("roomCodes") == lSelectedCodes
    )
    and fParseTimestamp(dPreviousState.get("startedAt")) is not None
  )
  vRunStartedAt = (
    str(dPreviousState["startedAt"]) if vResumeRun else fIsoNow()
  )
  pCache["validationState"] = {
    "status": "in_progress",
    "scope": pScope,
    "startedAt": vRunStartedAt,
    "completed": 0,
    "total": vCount,
    "roomCodes": lSelectedCodes if pScope != "all" else [],
  }
  fSaveCache(pCache)
  print(pLocaliser.mText("validation_start", count=vCount), flush=True)

  try:
    for vIndex, dRoom in enumerate(lRooms, start=1):
      dExistingValidation = dRoom.get("validation")
      if vResumeRun and isinstance(dExistingValidation, dict):
        vExistingTimestamp = fParseTimestamp(dExistingValidation.get("checkedAt"))
        vRunTimestamp = fParseTimestamp(vRunStartedAt)
        if (
          vExistingTimestamp is not None
          and vRunTimestamp is not None
          and vExistingTimestamp >= vRunTimestamp
          and int(dExistingValidation.get("httpStatus", 0)) != 429
        ):
          if dExistingValidation.get("valid") is True:
            vValidCount += 1
          else:
            vInvalidCount += 1
          pCache["validationState"]["completed"] = vIndex
          continue

      vAttempts = 0
      dValidation: dict[str, object] | None = None

      while vAttempts < 3:
        vLimiter.mWait()
        try:
          dResult = pClient.mQuickGet(str(dRoom["url"]))
          vLimiter.mSuccess()
          vConsecutiveLimitedRooms = 0
          vFinalRoomCode = fRoomCodeFromUrl(str(dResult["finalUrl"]))
          dValidation = {
            "checkedAt": dResult["checkedAt"],
            "httpStatus": dResult["status"],
            "finalUrl": dResult["finalUrl"],
            "valid": bool(dResult["valid"]) and bool(vFinalRoomCode),
          }
          break
        except RateLimitError as vError:
          vAttempts += 1
          vWaitFor = vLimiter.mLimited(vError.vRetryAfter)
          print(
            pLocaliser.mText("rate_limited", seconds=vWaitFor),
            flush=True,
          )
          time.sleep(vWaitFor)
        except TryHackMeClientError as vError:
          vConsecutiveLimitedRooms = 0
          dValidation = {
            "checkedAt": fIsoNow(),
            "httpStatus": 0,
            "finalUrl": str(dRoom["url"]),
            "valid": False,
            "error": str(vError),
          }
          break

      if dValidation is None:
        vConsecutiveLimitedRooms += 1
        dValidation = {
          "checkedAt": fIsoNow(),
          "httpStatus": 429,
          "finalUrl": str(dRoom["url"]),
          "valid": False,
          "error": "rate_limited_after_three_retries",
        }

      dRoom["validation"] = dValidation
      pCache["validationState"]["completed"] = vIndex
      if dValidation["valid"]:
        vValidCount += 1
      else:
        vInvalidCount += 1

      if vIndex % 10 == 0 or vIndex == vCount:
        pCache["lastValidatedAt"] = fIsoNow()
        pCache["rooms"] = lAllRooms
        fSaveCache(pCache)
        print(
          pLocaliser.mText(
            "validation_progress",
            done=vIndex,
            count=vCount,
            valid=vValidCount,
            invalid=vInvalidCount,
            delay=vLimiter.vDelay,
          ),
          flush=True,
        )

      if vConsecutiveLimitedRooms >= 3:
        pCache["lastValidatedAt"] = fIsoNow()
        pCache["rooms"] = lAllRooms
        fSaveCache(pCache)
        raise RateLimitError(
          "Three consecutive room URLs remained rate-limited after all retries.",
          vLimiter.vDelay,
        )
  except KeyboardInterrupt:
    pCache["lastValidatedAt"] = fIsoNow()
    pCache["rooms"] = lAllRooms
    fSaveCache(pCache)
    print(pLocaliser.mText("interrupted"), flush=True)
    raise

  pCache["lastValidatedAt"] = fIsoNow()
  pCache["validationState"] = {
    "status": "complete",
    "scope": pScope,
    "startedAt": vRunStartedAt,
    "completedAt": pCache["lastValidatedAt"],
    "completed": vCount,
    "total": vCount,
    "roomCodes": lSelectedCodes if pScope != "all" else [],
  }
  if pScope == "all":
    pCache["lastFullValidationAt"] = pCache["lastValidatedAt"]
  pCache["rooms"] = lAllRooms
  fSaveCache(pCache)
  print(
    pLocaliser.mText(
      "validation_complete",
      valid=vValidCount,
      invalid=vInvalidCount,
      count=vCount,
    ),
    flush=True,
  )
  return pCache


def fMain(pArguments: list[str] | None = None) -> int:
  """Run the complete macOS preparation workflow."""

  vArguments = pArguments if pArguments is not None else __import__("sys").argv[1:]
  vLocaliser = Localiser(fPreparseLocale(vArguments))
  vParser = fBuildParser(vLocaliser)
  dArguments = vars(vParser.parse_args(vArguments))
  vLocaliser = Localiser(str(dArguments["locale"]))
  vClient: TryHackMeBrowserClient | None = None

  try:
    vClient, dCandidate = fOpenAuthenticatedClient(
      pBrowser=str(dArguments["browser"]),
      pHeaded=bool(dArguments["headed"]),
      pLocaliser=vLocaliser,
    )
    dCandidate.clear()

    try:
      dCache = fLoadCache()
    except CacheError as vError:
      print(vLocaliser.mText("cache_invalid", error=str(vError)), flush=True)
      dCache = None

    if dCache is None:
      print(vLocaliser.mText("cache_missing"), flush=True)
      dCache, lNewCodes, lRelistedCodes = fDiscoverCatalogue(
        pClient=vClient,
        pCache=None,
        pDelaySeconds=float(dArguments["catalogue_delay"]),
        pLocaliser=vLocaliser,
      )
      if not bool(dArguments["skip_url_validation"]):
        dCache = fValidateCatalogueUrls(
          pClient=vClient,
          pCache=dCache,
          pDelaySeconds=float(dArguments["validation_delay"]),
          pLocaliser=vLocaliser,
        )
    else:
      print(
        vLocaliser.mText(
          "cache_loaded",
          count=len(dCache["rooms"]),
          path=cCachePath,
        ),
        flush=True,
      )
      if not bool(dArguments["skip_url_validation"]):
        dCache = fValidateCatalogueUrls(
          pClient=vClient,
          pCache=dCache,
          pDelaySeconds=float(dArguments["validation_delay"]),
          pLocaliser=vLocaliser,
        )

      dCache, lNewCodes, lRelistedCodes = fDiscoverCatalogue(
        pClient=vClient,
        pCache=dCache,
        pDelaySeconds=float(dArguments["catalogue_delay"]),
        pLocaliser=vLocaliser,
      )
      sDiscoveredCodes = set(lNewCodes + lRelistedCodes)
      if not bool(dArguments["skip_url_validation"]) and sDiscoveredCodes:
        print(
          vLocaliser.mText("discovery_validation_start", count=len(sDiscoveredCodes)),
          flush=True,
        )
        dCache = fValidateCatalogueUrls(
          pClient=vClient,
          pCache=dCache,
          pDelaySeconds=float(dArguments["validation_delay"]),
          pLocaliser=vLocaliser,
          pRoomCodes=sDiscoveredCodes,
          pScope="discovered",
        )

    print(vLocaliser.mText("ready_for_offer"), flush=True)
    return 0
  except KeyboardInterrupt:
    return 130
  except (AuthenticationError, CacheError, TryHackMeClientError) as vError:
    print(vLocaliser.mText("fatal", error=str(vError)), flush=True)
    return 1
  finally:
    if vClient is not None:
      vClient.mClose()


if __name__ == "__main__":
  raise SystemExit(fMain())
