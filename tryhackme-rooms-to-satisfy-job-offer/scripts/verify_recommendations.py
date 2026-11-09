#!/usr/bin/env python3

"""Verify only the TryHackMe links selected for a recommendation report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


cMaximumInputBytes = 4 * 1024 * 1024
cMaximumUrls = 500
cUserAgent = (
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
  "AppleWebKit/537.36 (KHTML, like Gecko) "
  "Chrome/124.0.0.0 Safari/537.36"
)
cCanonicalPath = re.compile(r"/(?:room|module)/[A-Za-z0-9_-]+")


class RecommendationVerificationError(RuntimeError):
  """Report an invalid input or unsafe redirect without exposing private data."""


def fRequireTryHackMeHttps(pUrl: str) -> None:
  """Reject requests and redirects outside HTTPS TryHackMe domains."""

  try:
    dParsed = urlparse(pUrl)
    vPort = dParsed.port
  except ValueError as vError:
    raise RecommendationVerificationError("The URL contains an invalid port.") from vError

  vHost = (dParsed.hostname or "").casefold()
  if (
    dParsed.scheme.casefold() != "https"
    or not (vHost == "tryhackme.com" or vHost.endswith(".tryhackme.com"))
    or dParsed.username is not None
    or dParsed.password is not None
    or vPort not in (None, 443)
  ):
    raise RecommendationVerificationError(
      "Recommendation checks are restricted to HTTPS TryHackMe URLs."
    )


def fRequireCanonicalRecommendationUrl(pUrl: str) -> str:
  """Return a canonical room or module URL, rejecting all other inputs."""

  fRequireTryHackMeHttps(pUrl)
  dParsed = urlparse(pUrl)
  if (
    (dParsed.hostname or "").casefold() != "tryhackme.com"
    or dParsed.query
    or dParsed.fragment
    or not cCanonicalPath.fullmatch(dParsed.path)
  ):
    raise RecommendationVerificationError(
      "Every checked link must be a canonical TryHackMe room or module URL."
    )
  return pUrl


class TryHackMeRedirectHandler(urllib.request.HTTPRedirectHandler):
  """Allow redirects only while they remain on TryHackMe over HTTPS."""

  def redirect_request(
    self,
    pRequest: urllib.request.Request,
    pFilePointer: object,
    pCode: int,
    pMessage: str,
    pHeaders: object,
    pNewUrl: str,
  ) -> urllib.request.Request | None:
    fRequireTryHackMeHttps(pNewUrl)
    return super().redirect_request(
      pRequest,
      pFilePointer,
      pCode,
      pMessage,
      pHeaders,
      pNewUrl,
    )


def fExtractRecommendationUrls(pPayload: object) -> list[str]:
  """Extract and deduplicate reviewed room and module URLs from report JSON."""

  if not isinstance(pPayload, dict):
    raise RecommendationVerificationError("The report input must be a JSON object.")

  lUrls: list[str] = []
  sSeen: set[str] = set()
  for vSectionKey in ("sections", "moduleSections"):
    lSections = pPayload.get(vSectionKey, [])
    if not isinstance(lSections, list):
      raise RecommendationVerificationError(f"{vSectionKey} must be a list.")
    for dSection in lSections:
      if not isinstance(dSection, dict) or not isinstance(dSection.get("rows", []), list):
        raise RecommendationVerificationError(
          f"Every {vSectionKey} entry must contain a rows list."
        )
      for dRow in dSection.get("rows", []):
        if not isinstance(dRow, dict) or not isinstance(dRow.get("url"), str):
          raise RecommendationVerificationError(
            "Every recommendation row must contain a URL string."
          )
        vUrl = fRequireCanonicalRecommendationUrl(dRow["url"])
        if vUrl not in sSeen:
          sSeen.add(vUrl)
          lUrls.append(vUrl)

  if not lUrls:
    raise RecommendationVerificationError(
      "The report does not contain any room or module URLs to verify."
    )
  if len(lUrls) > cMaximumUrls:
    raise RecommendationVerificationError(
      f"The report contains more than {cMaximumUrls} unique URLs."
    )
  return lUrls


def fLoadRecommendationUrls(pPath: Path) -> list[str]:
  """Read a bounded report JSON file and return its canonical URLs."""

  try:
    if pPath.stat().st_size > cMaximumInputBytes:
      raise RecommendationVerificationError("The report input is unexpectedly large.")
    dPayload = json.loads(pPath.read_text(encoding="utf-8"))
  except RecommendationVerificationError:
    raise
  except (OSError, json.JSONDecodeError) as vError:
    raise RecommendationVerificationError(
      "The report input could not be read as UTF-8 JSON."
    ) from vError
  return fExtractRecommendationUrls(dPayload)


def fRetryAfterSeconds(pHeaders: object) -> float | None:
  """Return a bounded numeric Retry-After value when present."""

  try:
    vRawValue = str(pHeaders.get("Retry-After", "")).strip()
    if not vRawValue:
      return None
    return min(60.0, max(0.0, float(vRawValue)))
  except (AttributeError, TypeError, ValueError):
    return None


def fProbeUrl(
  pOpener: urllib.request.OpenerDirector,
  pUrl: str,
  pTimeoutSeconds: float,
) -> dict[str, object]:
  """Perform one bounded GET and return only non-sensitive status metadata."""

  vResponse = None
  try:
    vRequest = urllib.request.Request(
      pUrl,
      headers={
        "Accept": "text/html,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "User-Agent": cUserAgent,
      },
      method="GET",
    )
    vResponse = pOpener.open(vRequest, timeout=pTimeoutSeconds)
    vStatus = int(vResponse.getcode() or 0)
    vFinalUrl = str(vResponse.geturl() or pUrl)
    fRequireTryHackMeHttps(vFinalUrl)
    vResponse.read(1)
    return {
      "status": vStatus,
      "finalUrl": vFinalUrl,
      "retryAfter": fRetryAfterSeconds(vResponse.headers),
    }
  except urllib.error.HTTPError as vError:
    vResponse = vError
    return {
      "status": int(vError.code),
      "finalUrl": str(vError.geturl() or pUrl),
      "retryAfter": fRetryAfterSeconds(vError.headers),
    }
  except RecommendationVerificationError:
    return {"status": None, "finalUrl": pUrl, "error": "unsafe-redirect"}
  except (OSError, TimeoutError, urllib.error.URLError):
    return {"status": None, "finalUrl": pUrl, "error": "transport-error"}
  finally:
    if vResponse is not None:
      vResponse.close()


def fCheckUrl(
  pOpener: urllib.request.OpenerDirector,
  pUrl: str,
  pTimeoutSeconds: float,
  pRetryDelaySeconds: float,
) -> dict[str, object]:
  """Probe a URL and recheck it exactly once when the first result is not 200."""

  vUrl = fRequireCanonicalRecommendationUrl(pUrl)
  lAttempts = [fProbeUrl(pOpener, vUrl, pTimeoutSeconds)]
  if lAttempts[0].get("status") != 200:
    vRetryAfter = lAttempts[0].get("retryAfter")
    vWait = (
      float(vRetryAfter)
      if isinstance(vRetryAfter, (int, float))
      else pRetryDelaySeconds
    )
    if vWait > 0:
      time.sleep(vWait)
    lAttempts.append(fProbeUrl(pOpener, vUrl, pTimeoutSeconds))

  return {
    "url": vUrl,
    "valid": lAttempts[-1].get("status") == 200,
    "attempts": lAttempts,
  }


def fBuildParser() -> argparse.ArgumentParser:
  """Create the platform-neutral command-line interface."""

  vParser = argparse.ArgumentParser(
    description=(
      "Verify only the canonical TryHackMe links selected for a final report; "
      "every non-200 result is rechecked once."
    )
  )
  vSource = vParser.add_mutually_exclusive_group(required=True)
  vSource.add_argument(
    "--input",
    type=Path,
    help="Reviewed report JSON whose room and module links should be checked.",
  )
  vSource.add_argument(
    "--url",
    action="append",
    help="Canonical room or module URL to check; repeat for more than one.",
  )
  vParser.add_argument(
    "--request-delay",
    type=float,
    default=0.25,
    help="Pause in seconds between different links (default: 0.25).",
  )
  vParser.add_argument(
    "--retry-delay",
    type=float,
    default=1.25,
    help="Pause before the one allowed recheck (default: 1.25).",
  )
  vParser.add_argument(
    "--timeout",
    type=float,
    default=20.0,
    help="Timeout in seconds for each GET (default: 20).",
  )
  return vParser


def fMain(pArguments: list[str] | None = None) -> int:
  """Verify selected links and emit a concise machine-readable summary."""

  dArguments = fBuildParser().parse_args(pArguments)
  if dArguments.request_delay < 0 or dArguments.retry_delay < 0:
    print("Delays must be non-negative.", file=sys.stderr)
    return 2
  if dArguments.timeout <= 0:
    print("Timeout must be greater than zero.", file=sys.stderr)
    return 2

  try:
    if dArguments.input is not None:
      lUrls = fLoadRecommendationUrls(dArguments.input)
    else:
      lUrls = []
      sSeen: set[str] = set()
      for vRawUrl in dArguments.url or []:
        vUrl = fRequireCanonicalRecommendationUrl(vRawUrl)
        if vUrl not in sSeen:
          sSeen.add(vUrl)
          lUrls.append(vUrl)
      if not lUrls:
        raise RecommendationVerificationError("At least one URL is required.")
      if len(lUrls) > cMaximumUrls:
        raise RecommendationVerificationError(
          f"No more than {cMaximumUrls} unique URLs may be checked."
        )
  except RecommendationVerificationError as vError:
    print(str(vError), file=sys.stderr)
    return 2

  vOpener = urllib.request.build_opener(TryHackMeRedirectHandler())
  lResults: list[dict[str, object]] = []
  for vIndex, vUrl in enumerate(lUrls):
    lResults.append(fCheckUrl(
      vOpener,
      vUrl,
      pTimeoutSeconds=float(dArguments.timeout),
      pRetryDelaySeconds=float(dArguments.retry_delay),
    ))
    if vIndex + 1 < len(lUrls) and dArguments.request_delay > 0:
      time.sleep(float(dArguments.request_delay))

  lFailures = [dResult for dResult in lResults if dResult["valid"] is not True]
  dSummary = {
    "checked": len(lResults),
    "http200": len(lResults) - len(lFailures),
    "retried": sum(len(dResult["attempts"]) > 1 for dResult in lResults),
    "failed": lFailures,
  }
  print(json.dumps(dSummary, ensure_ascii=False, indent=2))
  return 1 if lFailures else 0


if __name__ == "__main__":
  raise SystemExit(fMain())
