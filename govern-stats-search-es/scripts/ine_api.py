#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import json
import sys
import unicodedata
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


cBaseUrl = "https://servicios.ine.es/wstempus/js/ES"
cMaximumResponseBytes = 16 * 1024 * 1024
dEndpointArguments = {
  "OPERACIONES_DISPONIBLES": 0,
  "OPERACION": 1,
  "TABLAS_OPERACION": 1,
  "PERIODICIDADES": 0,
  "GRUPOS_TABLA": 1,
  "VALORES_GRUPOSTABLA": 2,
  "SERIES_TABLA": 1,
  "SERIES_OPERACION": 1,
  "DATOS_TABLA": 1,
  "DATOS_SERIE": 1,
}


def fParameter(pText: str) -> tuple[str, str]:
  vName, vSeparator, vValue = pText.partition("=")
  if not vSeparator or not vName.isidentifier():
    raise argparse.ArgumentTypeError("Use name=value for each query parameter.")
  return vName, vValue


def fRequestUrl(
  pEndpoint: str,
  pIdentifiers: list[str],
  pParameters: list[tuple[str, str]],
) -> str:
  lSegments = [pEndpoint]
  for vIdentifier in pIdentifiers:
    if pEndpoint in {"DATOS_TABLA", "SERIES_TABLA"} and vIdentifier.lower().endswith(".px"):
      lSegments.extend(vIdentifier.removeprefix("/").split("/"))
    else:
      lSegments.append(vIdentifier)

  if any(vSegment in {"", ".", ".."} or "/" in vSegment or "\\" in vSegment for vSegment in lSegments):
    raise ValueError("Use an INE identifier or a PC-Axis table path.")

  vPath = "/".join(quote(vSegment, safe="") for vSegment in lSegments)
  vQuery = urlencode(pParameters)
  return f"{cBaseUrl}/{vPath}?{vQuery}" if vQuery else f"{cBaseUrl}/{vPath}"


def fFetch(pUrl: str) -> dict | list:
  vRequest = Request(pUrl, headers={"Accept": "application/json"})
  with urlopen(vRequest, timeout=30) as vReply:
    vBody = vReply.read(cMaximumResponseBytes + 1)

  if len(vBody) > cMaximumResponseBytes:
    raise ValueError("INE response exceeds 16 MiB. Narrow the filters or use the official file download.")
  if not vBody.strip():
    raise ValueError("INE returned an empty response body.")

  try:
    vPayload = json.loads(vBody)
  except (UnicodeDecodeError, json.JSONDecodeError) as vError:
    raise ValueError("INE returned an invalid JSON response.") from vError
  if not isinstance(vPayload, (list, dict)):
    raise ValueError("INE returned an unexpected JSON value.")
  return vPayload


def fFold(pText: str) -> str:
  vNormalized = unicodedata.normalize("NFKD", pText.casefold())
  return "".join(vCharacter for vCharacter in vNormalized if not unicodedata.combining(vCharacter))


def fCountryKey(pName: str) -> str:
  vName = " ".join(fFold(pName).split())
  # The census uses "España" for birthplace and "Española" for nationality.
  return "espana" if vName == "espanola" else vName


def fCountrySeries(
  pRows: list,
  pDimension: str,
  pValues: set[str],
  pUnit: str = "Personas",
) -> list[tuple[str, dict]]:
  lEntries = []
  for dSeries in pRows:
    if not isinstance(dSeries, dict) or dSeries.get("T3_Unidad") != pUnit:
      continue

    vMetadata = dSeries.get("MetaData")
    if not isinstance(vMetadata, list):
      continue
    ldMetadata = [dValue for dValue in vMetadata if isinstance(dValue, dict)]
    sValues = {str(dValue.get("Id")) for dValue in ldMetadata}
    if not pValues.issubset(sValues):
      continue

    for dValue in ldMetadata:
      if dValue.get("T3_Variable") == pDimension and isinstance(dValue.get("Nombre"), str):
        lEntries.append((dValue["Nombre"], dSeries))
  return lEntries


def fYearRange(pText: str) -> tuple[int, int]:
  try:
    vStart, vEnd = map(int, pText.split(":"))
  except ValueError as vError:
    raise argparse.ArgumentTypeError("Use START:END for a year range.") from vError
  if not 1 <= vStart <= vEnd <= 9999:
    raise argparse.ArgumentTypeError("Use years from 1 to 9999, with the start no later than the end.")
  return vStart, vEnd


def fMatches(pRow: object, pTerms: list[str]) -> bool:
  if not isinstance(pRow, dict):
    return False

  lLabels = [str(pRow.get(vField, "")) for vField in ("Nombre", "Codigo", "COD", "Id", "Cod_IOE")]
  if pRow.get("Cod_IOE"):
    lLabels.append(f"IOE{pRow['Cod_IOE']}")
  vText = fFold(" ".join(lLabels))
  return all(vTerm in vText for vTerm in pTerms)


def fResult(pUrl: str, pPayload: dict | list, pFind: str, pLimit: int | None) -> dict:
  dOutput = {"url": pUrl, "response": pPayload}
  lTerms = fFold(pFind).split()
  if isinstance(pPayload, list):
    lMatches = [vItem for vItem in pPayload if fMatches(vItem, lTerms)] if lTerms else pPayload
    vTruncated = pLimit is not None and len(lMatches) > pLimit
    dOutput.update(
      received=len(pPayload),
      matched=len(lMatches),
      truncated=vTruncated,
      response=lMatches[:pLimit] if vTruncated else lMatches,
    )
  elif lTerms or pLimit is not None:
    raise ValueError("Use --find and --limit with list responses. Use date or nult to select series observations.")
  return dOutput


def fMain() -> int:
  vParser = argparse.ArgumentParser(description="Query the official Spanish INE JSON API.")
  vParser.add_argument("endpoint", choices=dEndpointArguments)
  vParser.add_argument("identifiers", nargs="*")
  vParser.add_argument("--param", action="append", type=fParameter, default=[], metavar="NAME=VALUE")
  vParser.add_argument("--find", default="", help="Match each term in an item name or identifier.")
  vParser.add_argument("--limit", type=int, help="Limit the number of list items printed after filtering.")
  vArgs = vParser.parse_args()

  vExpected = dEndpointArguments[vArgs.endpoint]
  if len(vArgs.identifiers) != vExpected:
    vParser.error(f"{vArgs.endpoint} requires {vExpected} identifier(s).")
  if vArgs.limit is not None and vArgs.limit < 1:
    vParser.error("--limit must be a positive integer.")
  sParameters = {vName for vName, _ in vArgs.param}
  if {"date", "nult"} <= sParameters:
    vParser.error("Choose date for a range or nult for the latest periods.")
  try:
    vUrl = fRequestUrl(vArgs.endpoint, vArgs.identifiers, vArgs.param)
  except ValueError as vError:
    vParser.error(str(vError))

  try:
    vPayload = fFetch(vUrl)
    dOutput = fResult(vUrl, vPayload, vArgs.find, vArgs.limit)
  except HTTPError as vError:
    vError.close()
    print(f"INE API HTTP {vError.code} for {vUrl}", file=sys.stderr)
    return 1
  except (OSError, ValueError, HTTPException) as vError:
    print(f"{vError} URL: {vUrl}", file=sys.stderr)
    return 1

  print(json.dumps(dOutput, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(fMain())
