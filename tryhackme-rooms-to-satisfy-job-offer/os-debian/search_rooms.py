#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Rank cached TryHackMe rooms for one or more job-skill queries."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import re
import sys
import unicodedata

from manage_rooms import CacheError, Localiser, cCachePath, cLocales, fLoadCache


cStopWords = {
  "a", "an", "and", "are", "as", "at", "be", "by", "cyber", "de", "del", "el",
  "en", "for", "from", "in", "is", "la", "las", "los", "of", "on", "or",
  "para", "que", "se", "the", "to", "un", "una", "with", "y",
}
cTokenAliases = {
  "analyse": "analysis",
  "analysing": "analysis",
  "analyze": "analysis",
  "analyzing": "analysis",
  "actors": "actor",
  "apis": "api",
  "assess": "assessment",
  "assessing": "assessment",
  "assessments": "assessment",
  "attacks": "attack",
  "automate": "automation",
  "automated": "automation",
  "campaigns": "campaign",
  "detect": "detection",
  "detecting": "detection",
  "detections": "detection",
  "enriched": "enrich",
  "enriching": "enrich",
  "enrichment": "enrich",
  "feeds": "feed",
  "indicators": "indicator",
  "investigations": "investigation",
  "iocs": "ioc",
  "report": "reporting",
  "reports": "reporting",
  "requirements": "requirement",
  "rules": "rule",
  "tracked": "track",
  "tracking": "track",
  "tracks": "track",
  "ttps": "ttp",
  "workflows": "workflow",
}
cGenericSecurityTokens = {
  "analysis",
  "cyber",
  "detection",
  "incident",
  "intelligence",
  "monitoring",
  "platform",
  "response",
  "security",
  "threat",
}


def fNormalise(pText: str) -> str:
  """Normalise accents and casing while preserving technical punctuation."""

  vDecomposed = unicodedata.normalize("NFKD", pText.casefold())
  return "".join(vCharacter for vCharacter in vDecomposed if not unicodedata.combining(vCharacter))


def fTokenise(pText: str) -> list[str]:
  """Extract useful English and technical tokens from a query or room."""

  lTokens = re.findall(r"[a-z0-9][a-z0-9+.#_-]*", fNormalise(pText))
  return [
    cTokenAliases.get(vToken, vToken)
    for vToken in lTokens
    if vToken not in cStopWords and len(vToken) > 1
  ]


def fBuildParser(pLocaliser: Localiser) -> argparse.ArgumentParser:
  """Create the room-search command-line interface."""

  vParser = argparse.ArgumentParser(
    description=pLocaliser.mText("search_description")
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
    default=60,
    help=pLocaliser.mText("arg_limit"),
  )
  vParser.add_argument(
    "--locale",
    choices=cLocales,
    default=pLocaliser.vLocale,
    help=pLocaliser.mText("arg_locale"),
  )
  return vParser


def fPrepareDocuments(
  pRooms: list[dict[str, object]],
) -> list[dict[str, object]]:
  """Build weighted token statistics once for the complete cache."""

  lDocuments: list[dict[str, object]] = []
  for dRoom in pRooms:
    if dRoom.get("listed") is False:
      continue
    dValidation = dRoom.get("validation")
    if not isinstance(dValidation, dict) or dValidation.get("valid") is not True:
      continue

    vTitle = str(dRoom.get("title", ""))
    vDescription = str(dRoom.get("description", ""))
    vMetadata = " ".join(
      str(dRoom.get(vKey, ""))
      for vKey in ("difficulty", "roomType", "accessTier")
    )
    lTokens = fTokenise(f"{vTitle} {vTitle} {vTitle} {vDescription} {vMetadata}")
    lDocuments.append({
      "room": dRoom,
      "tokens": lTokens,
      "counts": Counter(lTokens),
      "length": max(1, len(lTokens)),
      "haystack": fNormalise(f"{vTitle} {vDescription} {vMetadata}"),
    })
  return lDocuments


def fDocumentFrequencies(
  pDocuments: list[dict[str, object]],
) -> Counter[str]:
  """Count how many rooms contain each catalogue term."""

  dFrequencies: Counter[str] = Counter()
  for dDocument in pDocuments:
    dFrequencies.update(set(dDocument["tokens"]))
  return dFrequencies


def fScoreDocument(
  pDocument: dict[str, object],
  pQuery: str,
  pQueryTokens: list[str],
  pDocumentFrequencies: Counter[str],
  pDocumentCount: int,
  pAverageLength: float,
) -> tuple[float, list[str], float, bool] | None:
  """Apply BM25 only when token coverage provides meaningful evidence."""

  dCounts: Counter[str] = pDocument["counts"]
  vLength = float(pDocument["length"])
  vScore = 0.0
  cK1 = 1.5
  cB = 0.75
  sQueryTokens = set(pQueryTokens)
  sMatchedTokens = {
    vToken for vToken in sQueryTokens if dCounts.get(vToken, 0) > 0
  }
  if not sMatchedTokens:
    return None

  vCoverage = len(sMatchedTokens) / len(sQueryTokens)
  vNormalisedQuery = fNormalise(pQuery).strip()
  vExactPhrase = (
    len(vNormalisedQuery) >= 3
    and vNormalisedQuery in str(pDocument["haystack"])
  )
  sSpecificQueryTokens = sQueryTokens.difference(cGenericSecurityTokens)
  sSpecificMatchedTokens = sMatchedTokens.intersection(sSpecificQueryTokens)
  if sSpecificQueryTokens and not sSpecificMatchedTokens and not vExactPhrase:
    return None
  vRareThreshold = max(8, int(pDocumentCount * 0.015))
  sRareTokens = {
    vToken
    for vToken in sMatchedTokens
    if vToken not in cGenericSecurityTokens
    and pDocumentFrequencies.get(vToken, 0) <= vRareThreshold
  }
  if len(sQueryTokens) == 1:
    vMeaningfulMatch = True
  elif len(sQueryTokens) == 2:
    vMeaningfulMatch = vCoverage == 1.0
  else:
    vMeaningfulMatch = (
      vExactPhrase
      or vCoverage >= 0.5
      or (bool(sRareTokens) and len(sMatchedTokens) >= 2 and vCoverage >= 0.25)
    )
  if not vMeaningfulMatch:
    return None

  for vToken in sMatchedTokens:
    vFrequency = dCounts.get(vToken, 0)
    if vFrequency <= 0:
      continue
    vDocumentFrequency = pDocumentFrequencies.get(vToken, 0)
    vIdf = math.log(
      1 + (pDocumentCount - vDocumentFrequency + 0.5) / (vDocumentFrequency + 0.5)
    )
    vDenominator = vFrequency + cK1 * (
      1 - cB + cB * vLength / max(1.0, pAverageLength)
    )
    vScore += vIdf * (vFrequency * (cK1 + 1)) / vDenominator

  if vExactPhrase:
    vScore += 8.0
  vScore *= 0.5 + vCoverage
  vScore += min(4.0, len(sRareTokens) * 1.25)
  return vScore, sorted(sMatchedTokens), vCoverage, vExactPhrase


def fRankRooms(
  pRooms: list[dict[str, object]],
  pQueries: list[str],
  pLimit: int,
) -> list[dict[str, object]]:
  """Return a compact candidate set for the model's semantic review."""

  lDocuments = fPrepareDocuments(pRooms)
  if not lDocuments:
    return []

  dDocumentFrequencies = fDocumentFrequencies(lDocuments)
  vAverageLength = sum(float(dDocument["length"]) for dDocument in lDocuments) / len(lDocuments)
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

    dRoom = dDocument["room"]
    lResults.append({
      "score": round(vTotalScore, 4),
      "matchedQueries": lMatchedQueries,
      "queryEvidence": lQueryEvidence,
      "code": dRoom.get("code"),
      "title": dRoom.get("title"),
      "description": dRoom.get("description"),
      "url": dRoom.get("url"),
      "isPremium": dRoom.get("isPremium"),
      "accessTier": dRoom.get("accessTier"),
      "difficulty": dRoom.get("difficulty"),
      "roomType": dRoom.get("roomType"),
    })

  lResults.sort(
    key=lambda pResult: (-float(pResult["score"]), str(pResult["title"]).casefold())
  )
  return lResults[:pLimit]


def fMain(pArguments: list[str] | None = None) -> int:
  """Search all-rooms.json and emit machine-readable candidates."""

  vArguments = pArguments if pArguments is not None else sys.argv[1:]
  vInitialLocaliser = Localiser("en-GB")
  vParser = fBuildParser(vInitialLocaliser)
  dArguments = vars(vParser.parse_args(vArguments))
  vLocaliser = Localiser(str(dArguments["locale"]))
  lQueries = [str(vQuery).strip() for vQuery in dArguments["query"] if str(vQuery).strip()]

  try:
    if not lQueries:
      print(vLocaliser.mText("search_query_required"), file=sys.stderr)
      return 2

    vLimit = max(1, min(200, int(dArguments["limit"])))
    dCache = fLoadCache()
    if dCache is None:
      raise CacheError(f"{cCachePath} does not exist.")

    lResults = fRankRooms(dCache["rooms"], lQueries, vLimit)
    if not lResults:
      print(vLocaliser.mText("search_no_results"), file=sys.stderr)
    print(json.dumps(lResults, ensure_ascii=False, indent=2))
    return 0
  except (CacheError, OSError, json.JSONDecodeError) as vError:
    print(vLocaliser.mText("fatal", error=str(vError)), file=sys.stderr)
    return 1
  finally:
    lQueries.clear()


if __name__ == "__main__":
  raise SystemExit(fMain())
