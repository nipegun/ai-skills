#!/usr/bin/env python3

"""Build, refresh and verify the TryHackMe module catalogue on macOS."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from manage_rooms import (
  CacheError,
  Localiser,
  cBrowsers,
  cLocales,
  cSkillRoot,
  cTempRoot,
  fOpenAuthenticatedClient,
  fParseTimestamp,
  fPreparseLocale,
)
from tryhackme_client import (
  AdaptiveRateLimiter,
  AuthenticationError,
  RateLimitError,
  SecurityCheckpointError,
  TryHackMeBrowserClient,
  TryHackMeClientError,
  cCatalogueEndpoint,
  cModuleDataEndpoint,
  fIsoNow,
)


cModuleCachePath = cSkillRoot / "thm-modules" / "all-modules.json"
cModuleSchemaVersion = 1


def fBuildParser(pLocaliser: Localiser) -> argparse.ArgumentParser:
  """Create the localised module command-line interface."""

  vParser = argparse.ArgumentParser(
    description=pLocaliser.mText("modules_description")
  )
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
    "--detail-delay",
    type=float,
    default=1.25,
    help=pLocaliser.mText("arg_detail_delay"),
  )
  vParser.add_argument(
    "--skip-module-details",
    action="store_true",
    help=pLocaliser.mText("arg_skip_module_details"),
  )
  return vParser


def fLoadModuleCache() -> dict[str, object] | None:
  """Load and structurally validate all-modules.json when present."""

  if not cModuleCachePath.is_file():
    return None

  try:
    with cModuleCachePath.open("r", encoding="utf-8") as vFile:
      vPayload = json.load(vFile)
  except (OSError, json.JSONDecodeError) as vError:
    raise CacheError(f"Could not read {cModuleCachePath}: {vError}") from vError

  if not isinstance(vPayload, dict):
    raise CacheError("The module cache root must be a JSON object.")
  if not isinstance(vPayload.get("modules"), list):
    raise CacheError("The module cache must contain a modules list.")
  if int(vPayload.get("schemaVersion", 0)) != cModuleSchemaVersion:
    raise CacheError("The module cache schema version is not supported.")

  vDefaultSeenAt = str(
    vPayload.get("lastDiscoveryAt")
    or vPayload.get("lastCataloguedAt")
    or fIsoNow()
  )

  for vIndex, dModule in enumerate(vPayload["modules"]):
    if not isinstance(dModule, dict):
      raise CacheError(f"Module entry {vIndex} is not a JSON object.")
    for vRequiredKey in ("code", "title", "description", "url"):
      if vRequiredKey not in dModule:
        raise CacheError(f"Module entry {vIndex} is missing {vRequiredKey}.")
    if not isinstance(dModule.get("listed", True), bool):
      raise CacheError(f"Module entry {vIndex} has an invalid listed value.")
    dModule.setdefault("listed", True)
    dModule.setdefault("firstSeenAt", vDefaultSeenAt)
    dModule.setdefault("lastSeenAt", vDefaultSeenAt)

  vPayload["moduleCount"] = len(vPayload["modules"])
  vPayload["listedModuleCount"] = sum(
    1 for dModule in vPayload["modules"] if dModule.get("listed") is True
  )

  return vPayload


def fSaveModuleCache(pCache: dict[str, object]) -> None:
  """Atomically save public module metadata without session or account data."""

  cModuleCachePath.parent.mkdir(parents=True, exist_ok=True)
  cTempRoot.mkdir(mode=0o700, parents=True, exist_ok=True)
  vTemporaryPath: Path | None = None

  try:
    vDescriptor, vTemporaryName = tempfile.mkstemp(
      prefix="all-modules-",
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
    os.replace(vTemporaryPath, cModuleCachePath)
    os.chmod(cModuleCachePath, 0o644)
    vTemporaryPath = None
  except OSError as vError:
    raise CacheError(f"Could not save {cModuleCachePath}: {vError}") from vError
  finally:
    if vTemporaryPath is not None and vTemporaryPath.exists():
      vTemporaryPath.unlink(missing_ok=True)


def fMergeModuleCatalogue(
  pExistingCache: dict[str, object] | None,
  pFreshModules: list[dict[str, object]],
  pDiscoveryComplete: bool = True,
) -> tuple[dict[str, object], list[str], list[str], list[str]]:
  """Union a fresh discovery into the cache without losing historical modules.

  When the search endpoint returned fewer modules than its own reported total,
  the pass is incomplete and cached modules keep their listed state: a module
  missing from a partial answer has not been withdrawn from the platform.
  """

  dExistingModules: dict[str, dict[str, object]] = {}
  if pExistingCache is not None:
    for dModule in pExistingCache.get("modules", []):
      if isinstance(dModule, dict) and isinstance(dModule.get("code"), str):
        dExistingModules[str(dModule["code"])] = dModule

  vDiscoveredAt = fIsoNow()
  sFreshCodes = {str(dModule["code"]) for dModule in pFreshModules}
  dMergedModules: dict[str, dict[str, object]] = {}
  lNewCodes: list[str] = []
  lRelistedCodes: list[str] = []
  lUnlistedCodes: list[str] = []

  for vCode, dExistingModule in dExistingModules.items():
    dMergedModule = dict(dExistingModule)
    if vCode not in sFreshCodes and pDiscoveryComplete:
      if dMergedModule.get("listed") is not False:
        lUnlistedCodes.append(vCode)
      dMergedModule["listed"] = False
    dMergedModules[vCode] = dMergedModule

  for dFreshModule in pFreshModules:
    vCode = str(dFreshModule["code"])
    dExistingModule = dMergedModules.get(vCode)
    if dExistingModule is None:
      dMergedModule = dict(dFreshModule)
      dMergedModule["firstSeenAt"] = vDiscoveredAt
      lNewCodes.append(vCode)
    else:
      vWasListed = dExistingModule.get("listed") is not False
      dMergedModule = dict(dExistingModule)
      for vKey, vValue in dFreshModule.items():
        if vKey in ("isPremium", "accessTier") and dMergedModule.get("roomCount"):
          continue
        if vKey == "summary" and not str(vValue).strip():
          continue
        if vKey == "tags" and not vValue:
          continue
        dMergedModule[vKey] = vValue
      dMergedModule.setdefault("firstSeenAt", vDiscoveredAt)
      if not vWasListed:
        lRelistedCodes.append(vCode)
    dMergedModule["listed"] = True
    dMergedModule["lastSeenAt"] = vDiscoveredAt
    dMergedModules[vCode] = dMergedModule

  lMergedModules = sorted(
    dMergedModules.values(),
    key=lambda pModule: str(pModule["title"]).casefold(),
  )
  dMergedCache = dict(pExistingCache) if pExistingCache is not None else {}
  dMergedCache.update({
    "schemaVersion": cModuleSchemaVersion,
    "source": cCatalogueEndpoint,
    "detailSource": cModuleDataEndpoint,
    "lastCataloguedAt": vDiscoveredAt,
    "lastDiscoveryAt": vDiscoveredAt,
    "discoveryState": {
      "discoveredAt": vDiscoveredAt,
      "newModuleCount": len(lNewCodes),
      "newModuleCodes": sorted(lNewCodes),
      "relistedModuleCount": len(lRelistedCodes),
      "relistedModuleCodes": sorted(lRelistedCodes),
      "unlistedModuleCount": len(lUnlistedCodes),
      "unlistedModuleCodes": sorted(lUnlistedCodes),
    },
    "moduleCount": len(lMergedModules),
    "listedModuleCount": sum(
      1 for dModule in lMergedModules if dModule.get("listed") is True
    ),
    "modules": lMergedModules,
  })
  return dMergedCache, lNewCodes, lRelistedCodes, lUnlistedCodes


def fDiscoverModules(
  pClient: TryHackMeBrowserClient,
  pCache: dict[str, object] | None,
  pDelaySeconds: float,
  pLocaliser: Localiser,
) -> tuple[dict[str, object], list[str], list[str]]:
  """Discover the complete live module catalogue and append newly seen modules."""

  def fProgress(pPage: int, pCount: int, pTotal: int | None) -> None:
    print(
      pLocaliser.mText("modules_page", page=pPage, count=pCount, total=""),
      flush=True,
    )

  print(pLocaliser.mText("modules_discovery_start"), flush=True)
  lFreshModules, vExpectedTotal = pClient.mFetchModuleCatalogue(
    pDelaySeconds=max(0.75, pDelaySeconds),
    pProgress=fProgress,
  )
  vDiscoveryComplete = vExpectedTotal is None or len(lFreshModules) >= vExpectedTotal
  dMergedCache, lNewCodes, lRelistedCodes, lUnlistedCodes = fMergeModuleCatalogue(
    pCache,
    lFreshModules,
    vDiscoveryComplete,
  )
  dMergedCache["discoveryState"]["expectedTotal"] = vExpectedTotal
  dMergedCache["discoveryState"]["complete"] = vDiscoveryComplete
  fSaveModuleCache(dMergedCache)
  print(
    pLocaliser.mText("modules_discovery_complete", count=len(lFreshModules)),
    flush=True,
  )
  if not vDiscoveryComplete:
    print(
      pLocaliser.mText(
        "modules_discovery_partial",
        count=len(lFreshModules),
        total=vExpectedTotal,
      ),
      flush=True,
    )
  if lNewCodes:
    print(pLocaliser.mText("modules_discovery_new", count=len(lNewCodes)), flush=True)
  else:
    print(pLocaliser.mText("modules_discovery_no_new"), flush=True)
  if lRelistedCodes:
    print(
      pLocaliser.mText("modules_discovery_relisted", count=len(lRelistedCodes)),
      flush=True,
    )
  if lUnlistedCodes:
    print(
      pLocaliser.mText("modules_discovery_unlisted", count=len(lUnlistedCodes)),
      flush=True,
    )
  print(
    pLocaliser.mText(
      "modules_saved",
      count=len(dMergedCache["modules"]),
      path=cModuleCachePath,
    ),
    flush=True,
  )
  return dMergedCache, lNewCodes, lRelistedCodes


def fApplyModuleDetail(
  pModule: dict[str, object],
  pResult: dict[str, object],
) -> None:
  """Store one detail result as public metadata plus its verification record.

  A transient failure never demotes a module that a previous pass verified,
  because search only accepts verified modules and a single network error
  would otherwise silently remove a module that still exists. Only an explicit
  "not found" answer from the platform invalidates a module.
  """

  dDetail = pResult.get("detail")
  dPreviousValidation = pModule.get("validation")
  vTransientFailure = (
    not pResult["valid"] and int(pResult["httpStatus"]) not in (404, 410)
  )
  if (
    vTransientFailure
    and isinstance(dPreviousValidation, dict)
    and dPreviousValidation.get("valid") is True
  ):
    dPreviousValidation["lastFailureAt"] = pResult["checkedAt"]
    dPreviousValidation["lastFailure"] = str(pResult.get("error", "request_failed"))
    return

  pModule["validation"] = {
    "checkedAt": pResult["checkedAt"],
    "httpStatus": pResult["httpStatus"],
    "finalUrl": pResult["finalUrl"],
    "valid": bool(pResult["valid"]),
  }
  if "error" in pResult:
    pModule["validation"]["error"] = pResult["error"]
  if not isinstance(dDetail, dict):
    return

  pModule["summary"] = dDetail["summary"]
  if dDetail["detailDescription"]:
    pModule["description"] = dDetail["detailDescription"]
  if dDetail["tags"]:
    pModule["tags"] = dDetail["tags"]
  pModule["rooms"] = dDetail["rooms"]
  pModule["roomCount"] = dDetail["roomCount"]
  pModule["freeRoomCount"] = dDetail["freeRoomCount"]
  pModule["paidRoomCount"] = dDetail["paidRoomCount"]
  pModule["totalTimeMinutes"] = dDetail["totalTimeMinutes"]
  pModule["prerequisites"] = dDetail["prerequisites"]
  pModule["nextSteps"] = dDetail["nextSteps"]
  pModule["keyLearnings"] = dDetail["keyLearnings"]
  pModule["isPublic"] = dDetail["isPublic"]
  if dDetail["accessTier"] != "unknown":
    pModule["isPremium"] = dDetail["isPremium"]
    pModule["accessTier"] = dDetail["accessTier"]


def fFetchModuleDetails(
  pClient: TryHackMeBrowserClient,
  pCache: dict[str, object],
  pDelaySeconds: float,
  pLocaliser: Localiser,
  pModuleCodes: set[str] | None = None,
  pScope: str = "all",
) -> dict[str, object]:
  """Read official module details sequentially with adaptive rate limiting."""

  lAllModules = [
    dModule for dModule in pCache.get("modules", []) if isinstance(dModule, dict)
  ]
  lModules = [
    dModule
    for dModule in lAllModules
    if pModuleCodes is None or str(dModule.get("code", "")) in pModuleCodes
  ]
  vCount = len(lModules)
  if vCount == 0:
    return pCache

  lSelectedCodes = sorted(str(dModule["code"]) for dModule in lModules)
  vValidCount = 0
  vInvalidCount = 0
  vConsecutiveLimitedModules = 0
  vLimiter = AdaptiveRateLimiter(max(0.75, pDelaySeconds), pMinimumDelay=0.75)
  dPreviousState = pCache.get("detailState")
  vResumeRun = (
    isinstance(dPreviousState, dict)
    and dPreviousState.get("status") == "in_progress"
    and dPreviousState.get("scope") == pScope
    and dPreviousState.get("total") == vCount
    and (
      pScope == "all"
      or dPreviousState.get("moduleCodes") == lSelectedCodes
    )
    and fParseTimestamp(dPreviousState.get("startedAt")) is not None
  )
  vRunStartedAt = str(dPreviousState["startedAt"]) if vResumeRun else fIsoNow()
  pCache["detailState"] = {
    "status": "in_progress",
    "scope": pScope,
    "startedAt": vRunStartedAt,
    "completed": 0,
    "total": vCount,
    "moduleCodes": lSelectedCodes if pScope != "all" else [],
  }
  fSaveModuleCache(pCache)
  print(pLocaliser.mText("modules_detail_start", count=vCount), flush=True)

  try:
    for vIndex, dModule in enumerate(lModules, start=1):
      dExistingValidation = dModule.get("validation")
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
          pCache["detailState"]["completed"] = vIndex
          continue

      vAttempts = 0
      vRateLimited = False
      dResult: dict[str, object] | None = None
      vLastError = ""

      while vAttempts < 3:
        vLimiter.mWait()
        try:
          dResult = pClient.mFetchModuleData(str(dModule["code"]))
          vLimiter.mSuccess()
          vConsecutiveLimitedModules = 0
          break
        except RateLimitError as vError:
          vAttempts += 1
          vRateLimited = True
          vWaitFor = vLimiter.mLimited(vError.vRetryAfter)
          print(pLocaliser.mText("rate_limited", seconds=vWaitFor), flush=True)
          time.sleep(vWaitFor)
        except SecurityCheckpointError:
          raise
        except TryHackMeClientError as vError:
          vAttempts += 1
          vLastError = str(vError)
          time.sleep(min(8.0, 2.0 * vAttempts))

      if dResult is None:
        if vRateLimited:
          vConsecutiveLimitedModules += 1
        dResult = {
          "checkedAt": fIsoNow(),
          "httpStatus": 429 if vRateLimited else 0,
          "finalUrl": str(dModule["url"]),
          "valid": False,
          "error": (
            "rate_limited_after_three_retries"
            if vRateLimited
            else vLastError or "request_failed_after_three_retries"
          ),
          "detail": None,
        }

      fApplyModuleDetail(dModule, dResult)
      pCache["detailState"]["completed"] = vIndex
      if dResult["valid"]:
        vValidCount += 1
      else:
        vInvalidCount += 1

      if vIndex % 10 == 0 or vIndex == vCount:
        pCache["lastDetailAt"] = fIsoNow()
        pCache["modules"] = lAllModules
        fSaveModuleCache(pCache)
        print(
          pLocaliser.mText(
            "modules_detail_progress",
            done=vIndex,
            count=vCount,
            valid=vValidCount,
            invalid=vInvalidCount,
            delay=vLimiter.vDelay,
          ),
          flush=True,
        )

      if vConsecutiveLimitedModules >= 3:
        pCache["lastDetailAt"] = fIsoNow()
        pCache["modules"] = lAllModules
        fSaveModuleCache(pCache)
        raise RateLimitError(
          "Three consecutive module details remained rate-limited after all retries.",
          vLimiter.vDelay,
        )
  except KeyboardInterrupt:
    pCache["lastDetailAt"] = fIsoNow()
    pCache["modules"] = lAllModules
    fSaveModuleCache(pCache)
    print(pLocaliser.mText("interrupted"), flush=True)
    raise

  pCache["lastDetailAt"] = fIsoNow()
  pCache["detailState"] = {
    "status": "complete",
    "scope": pScope,
    "startedAt": vRunStartedAt,
    "completedAt": pCache["lastDetailAt"],
    "completed": vCount,
    "total": vCount,
    "moduleCodes": lSelectedCodes if pScope != "all" else [],
  }
  if pScope == "all":
    pCache["lastFullDetailAt"] = pCache["lastDetailAt"]
  pCache["modules"] = lAllModules
  fSaveModuleCache(pCache)
  print(
    pLocaliser.mText(
      "modules_detail_complete",
      valid=vValidCount,
      invalid=vInvalidCount,
      count=vCount,
    ),
    flush=True,
  )
  return pCache


def fMain(pArguments: list[str] | None = None) -> int:
  """Run the complete macOS module preparation workflow."""

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
      dCache = fLoadModuleCache()
    except CacheError as vError:
      print(vLocaliser.mText("modules_cache_invalid", error=str(vError)), flush=True)
      dCache = None

    if dCache is None:
      print(vLocaliser.mText("modules_cache_missing"), flush=True)
    else:
      print(
        vLocaliser.mText(
          "modules_cache_loaded",
          count=len(dCache["modules"]),
          path=cModuleCachePath,
        ),
        flush=True,
      )
      if not bool(dArguments["skip_module_details"]):
        dCache = fFetchModuleDetails(
          pClient=vClient,
          pCache=dCache,
          pDelaySeconds=float(dArguments["detail_delay"]),
          pLocaliser=vLocaliser,
        )

    dCache, lNewCodes, lRelistedCodes = fDiscoverModules(
      pClient=vClient,
      pCache=dCache,
      pDelaySeconds=float(dArguments["catalogue_delay"]),
      pLocaliser=vLocaliser,
    )
    sDiscoveredCodes = set(lNewCodes + lRelistedCodes)
    if not bool(dArguments["skip_module_details"]) and sDiscoveredCodes:
      print(
        vLocaliser.mText("modules_detail_discovery_start", count=len(sDiscoveredCodes)),
        flush=True,
      )
      dCache = fFetchModuleDetails(
        pClient=vClient,
        pCache=dCache,
        pDelaySeconds=float(dArguments["detail_delay"]),
        pLocaliser=vLocaliser,
        pModuleCodes=sDiscoveredCodes,
        pScope="discovered",
      )

    print(vLocaliser.mText("modules_ready"), flush=True)
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
