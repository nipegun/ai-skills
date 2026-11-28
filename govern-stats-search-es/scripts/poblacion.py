#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from urllib.error import HTTPError

from ine_api import fCountryKey, fCountrySeries, fFetch, fRequestUrl, fYearRange


dTables = {
  "birth": ("68528", "Países"),
  "nationality": ("68527", "Nacionalidad"),
}
dHistoricalTables = {
  "birth": ("56937", "Países y Continentes"),
  "nationality": ("56936", "Nacionalidad"),
}
cCensusFirstYear = 2021
dPopulationFilters = {"349": "16473", "260": "17338", "18": "451"}
dHistoricalFilters = {"356": "15668", "18": "451"}
sPopulationValues = set(dPopulationFilters.values())


def fObservations(pSeries: dict, pYears: tuple[int, int] | None) -> list[dict]:
  vData = pSeries.get("Data")
  if not isinstance(vData, list):
    return []

  ldObservations = []
  for dObservation in vData:
    if not isinstance(dObservation, dict):
      continue
    vDate = str(dObservation.get("Fecha", "")).partition("T")[0]
    vYearText = vDate[:4]
    if vDate[4:] != "-01-01" or not vYearText.isdecimal():
      continue
    if pYears is None or pYears[0] <= int(vYearText) <= pYears[1]:
      ldObservations.append(dObservation)
  return sorted(ldObservations, key=lambda pObservation: pObservation["Fecha"])


def fAnnualChanges(pObservations: list[dict]) -> list[dict]:
  dCounts = {}
  for dObservation in pObservations:
    vYear = int(dObservation["Fecha"][:4])
    vCount = dObservation.get("Valor")
    vNumeric = type(vCount) in (int, float) and math.isfinite(vCount)
    if vYear in dCounts or not vNumeric or dObservation.get("Secreto"):
      dCounts[vYear] = None
    else:
      dCounts[vYear] = vCount

  ldChanges = []
  for vYear, vCount in dCounts.items():
    vPrevious = dCounts.get(vYear - 1)
    if vCount is None or vPrevious is None:
      continue
    vChange = vCount - vPrevious
    ldChanges.append({
      "year": vYear,
      "change": vChange,
      "percent": round(vChange / vPrevious * 100, 2) if vPrevious else None,
    })
  return ldChanges


def fQuery(pCriterion: str, pCountry: str, pYears: tuple[int, int] | None) -> dict:
  vHistorical = pYears is not None and pYears[0] < cCensusFirstYear
  vTable, vDimension = (dHistoricalTables if vHistorical else dTables)[pCriterion]
  dFilters = dHistoricalFilters if vHistorical else dPopulationFilters
  lParameters = [("tv", f"{vVariable}:{vValue}") for vVariable, vValue in dFilters.items()]
  lParameters.append(("tip", "AM"))
  if pYears is None:
    lParameters.append(("nult", "1"))
  else:
    vStart, vEnd = pYears
    lParameters.append(("date", f"{vStart:04d}0101:{vEnd:04d}0101"))

  vUrl = fRequestUrl("DATOS_TABLA", [vTable], lParameters)
  dResult = {
    "criterion": pCriterion,
    "table": vTable,
    "source": f"https://www.ine.es/jaxiT3/Tabla.htm?t={vTable}",
    "api_url": vUrl,
  }
  try:
    vPayload = fFetch(vUrl)
    if not isinstance(vPayload, list):
      raise ValueError("INE returned an unexpected response for this table.")
  except HTTPError as vError:
    vError.close()
    return dResult | {"status": "request_failed", "error": f"INE API HTTP {vError.code}"}
  except (OSError, ValueError, HTTPException) as vError:
    return dResult | {"status": "request_failed", "error": str(vError)}

  sRequiredValues = sPopulationValues.union(dFilters.values())
  lEntries = fCountrySeries(vPayload, vDimension, sRequiredValues)
  if not lEntries:
    return dResult | {"status": "no_series"}

  vKey = fCountryKey(pCountry)
  lMatches = [(vName, dSeries) for vName, dSeries in lEntries if fCountryKey(vName) == vKey]
  if not lMatches:
    return dResult | {
      "status": "country_not_listed",
      "available_labels": sorted({vName for vName, _ in lEntries}),
    }
  if len(lMatches) > 1:
    return dResult | {"status": "ambiguous_country", "matching_labels": [vName for vName, _ in lMatches]}

  vName, dSeries = lMatches[0]
  ldObservations = fObservations(dSeries, pYears)
  dResult.update({
    "status": "found" if ldObservations else "no_observations",
    "country_label": vName,
    "series": dSeries.get("COD"),
    "unit": dSeries["T3_Unidad"],
    "observations": ldObservations,
  })
  if pYears is not None and pYears[0] < pYears[1]:
    sObserved = {int(dObservation["Fecha"][:4]) for dObservation in ldObservations}
    dResult["missing_years"] = [vYear for vYear in range(pYears[0], pYears[1] + 1) if vYear not in sObserved]
    dResult["annual_changes"] = fAnnualChanges(ldObservations)
  return dResult


def fMain() -> int:
  vParser = argparse.ArgumentParser(description="Get annual population counts for residents of Spain by country from INE.")
  vParser.add_argument("country", help="Country name as listed by INE.")
  vPeriodArguments = vParser.add_mutually_exclusive_group()
  vPeriodArguments.add_argument("--year", type=int, help="One reference year. Default is the latest annual data.")
  vPeriodArguments.add_argument("--years", type=fYearRange, metavar="START:END", help="Inclusive reference year range.")
  vParser.add_argument("--by", choices=(*dTables, "both"), default="both")
  vArgs = vParser.parse_args()
  if not vArgs.country.strip():
    vParser.error("Provide a country name.")
  if vArgs.year is not None and not 1 <= vArgs.year <= 9999:
    vParser.error("--year must be between 1 and 9999.")

  vPeriod = (vArgs.year, vArgs.year) if vArgs.year is not None else vArgs.years
  lCriteria = list(dTables) if vArgs.by == "both" else [vArgs.by]
  with ThreadPoolExecutor(max_workers=len(lCriteria)) as vExecutor:
    lFutures = [vExecutor.submit(fQuery, vCriterion, vArgs.country, vPeriod) for vCriterion in lCriteria]
    ldResults = [vFuture.result() for vFuture in lFutures]

  dOutput = {"country": vArgs.country, "year": vArgs.year, "results": ldResults}
  if vArgs.years is not None:
    dOutput["years"] = list(vArgs.years)
  print(json.dumps(dOutput, ensure_ascii=False, indent=2))
  return 1 if all(dResult["status"] == "request_failed" for dResult in ldResults) else 0


if __name__ == "__main__":
  raise SystemExit(fMain())
