#!/usr/bin/env python3

"""Rank cached TryHackMe modules for one or more job-skill queries."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys

from manage_modules import cModuleCachePath, fLoadModuleCache
from manage_rooms import CacheError, Localiser, cLocales
from search_rooms import fDocumentFrequencies, fNormalise, fScoreDocument, fTokenise


def fBuildParser(pLocaliser: Localiser) -> argparse.ArgumentParser:
  """Create the module-search command-line interface."""

  vParser = argparse.ArgumentParser(
    description=pLocaliser.mText("module_search_description")
  )
  vParser.add_argument(
    "--query",
    action="append",
    default=[],
    help=pLocaliser.mText("arg_query"),
  )
  vParser.add_argument(
    "--limit",
    type=int,
    default=30,
    help=pLocaliser.mText("arg_module_limit"),
  )
  vParser.add_argument(
    "--locale",
    choices=cLocales,
    default=pLocaliser.vLocale,
    help=pLocaliser.mText("arg_locale"),
  )
  return vParser


def fPrepareModuleDocuments(
  pModules: list[dict[str, object]],
) -> list[dict[str, object]]:
  """Build weighted token statistics once for the complete module cache."""

  lDocuments: list[dict[str, object]] = []
  for dModule in pModules:
    if dModule.get("listed") is False:
      continue
    dValidation = dModule.get("validation")
    if not isinstance(dValidation, dict) or dValidation.get("valid") is not True:
      continue

    vTitle = str(dModule.get("title", ""))
    vSummary = str(dModule.get("summary", ""))
    vDescription = str(dModule.get("description", ""))
    lTags = [str(vTag) for vTag in dModule.get("tags", []) if isinstance(vTag, str)]
    lKeyLearnings = [
      str(vLearning)
      for vLearning in dModule.get("keyLearnings", [])
      if isinstance(vLearning, str)
    ]
    lRoomTitles = [
      str(dRoom.get("title", ""))
      for dRoom in dModule.get("rooms", [])
      if isinstance(dRoom, dict)
    ]
    vMetadata = " ".join(
      str(dModule.get(vKey, "")) for vKey in ("difficulty", "moduleType", "accessTier")
    )
    vRoomText = " ".join(lRoomTitles)
    lTokens = fTokenise(
      f"{vTitle} {vTitle} {vTitle} {vSummary} {vDescription} "
      f"{' '.join(lKeyLearnings)} {' '.join(lTags)} {vMetadata} {vRoomText}"
    )
    lDocuments.append({
      "module": dModule,
      "tokens": lTokens,
      "counts": Counter(lTokens),
      "length": max(1, len(lTokens)),
      "haystack": fNormalise(
        f"{vTitle} {vSummary} {vDescription} "
        f"{' '.join(lKeyLearnings)} {' '.join(lTags)} {vMetadata} {vRoomText}"
      ),
    })
  return lDocuments


def fRankModules(
  pModules: list[dict[str, object]],
  pQueries: list[str],
  pLimit: int,
) -> list[dict[str, object]]:
  """Return a compact candidate set of modules for the model's semantic review."""

  lDocuments = fPrepareModuleDocuments(pModules)
  if not lDocuments:
    return []

  dDocumentFrequencies = fDocumentFrequencies(lDocuments)
  vAverageLength = sum(
    float(dDocument["length"]) for dDocument in lDocuments
  ) / len(lDocuments)
  lResults: list[dict[str, object]] = []

  for dDocument in lDocuments:
    vTotalScore = 0.0
    lMatchedQueries: list[str] = []
    lQueryEvidence: list[dict[str, object]] = []
    for vQuery in pQueries:
      lQueryTokens = fTokenise(vQuery)
      if not lQueryTokens:
        continue
      vScoredMatch = fScoreDocument(
        pDocument=dDocument,
        pQuery=vQuery,
        pQueryTokens=lQueryTokens,
        pDocumentFrequencies=dDocumentFrequencies,
        pDocumentCount=len(lDocuments),
        pAverageLength=vAverageLength,
      )
      if vScoredMatch is not None:
        vQueryScore, lMatchedTokens, vCoverage, vExactPhrase = vScoredMatch
        vTotalScore += vQueryScore
        lMatchedQueries.append(vQuery)
        lQueryEvidence.append({
          "query": vQuery,
          "matchedTokens": lMatchedTokens,
          "coverage": round(vCoverage, 3),
          "exactPhrase": vExactPhrase,
        })

    if vTotalScore <= 0:
      continue

    dModule = dDocument["module"]
    lRooms = [dRoom for dRoom in dModule.get("rooms", []) if isinstance(dRoom, dict)]
    lResults.append({
      "score": round(vTotalScore, 4),
      "matchedQueries": lMatchedQueries,
      "queryEvidence": lQueryEvidence,
      "code": dModule.get("code"),
      "title": dModule.get("title"),
      "summary": dModule.get("summary"),
      "description": dModule.get("description"),
      "url": dModule.get("url"),
      "tags": dModule.get("tags", []),
      "isPremium": dModule.get("isPremium"),
      "accessTier": dModule.get("accessTier"),
      "difficulty": dModule.get("difficulty"),
      "difficultyLevel": dModule.get("difficultyLevel"),
      "roomCount": dModule.get("roomCount"),
      "freeRoomCount": dModule.get("freeRoomCount"),
      "totalTimeMinutes": dModule.get("totalTimeMinutes"),
      "prerequisites": dModule.get("prerequisites", []),
      "nextSteps": dModule.get("nextSteps", []),
      "keyLearnings": dModule.get("keyLearnings", []),
      "roomCodes": [str(dRoom.get("code")) for dRoom in lRooms],
      "roomTitles": [str(dRoom.get("title")) for dRoom in lRooms],
    })

  lResults.sort(
    key=lambda pResult: (-float(pResult["score"]), str(pResult["title"]).casefold())
  )
  return lResults[:pLimit]


def fMain(pArguments: list[str] | None = None) -> int:
  """Search all-modules.json and emit machine-readable candidates."""

  vArguments = pArguments if pArguments is not None else sys.argv[1:]
  vInitialLocaliser = Localiser("en-GB")
  vParser = fBuildParser(vInitialLocaliser)
  dArguments = vars(vParser.parse_args(vArguments))
  vLocaliser = Localiser(str(dArguments["locale"]))
  lQueries = [
    str(vQuery).strip() for vQuery in dArguments["query"] if str(vQuery).strip()
  ]

  try:
    if not lQueries:
      print(vLocaliser.mText("search_query_required"), file=sys.stderr)
      return 2

    vLimit = max(1, min(200, int(dArguments["limit"])))
    dCache = fLoadModuleCache()
    if dCache is None:
      raise CacheError(f"{cModuleCachePath} does not exist.")

    lResults = fRankModules(dCache["modules"], lQueries, vLimit)
    if not lResults:
      print(vLocaliser.mText("module_search_no_results"), file=sys.stderr)
    print(json.dumps(lResults, ensure_ascii=False, indent=2))
    return 0
  except (CacheError, OSError, json.JSONDecodeError) as vError:
    print(vLocaliser.mText("fatal", error=str(vError)), file=sys.stderr)
    return 1
  finally:
    lQueries.clear()


if __name__ == "__main__":
  raise SystemExit(fMain())
