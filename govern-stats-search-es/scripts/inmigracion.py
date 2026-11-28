#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from http.client import HTTPException
from urllib.error import HTTPError

from ine_api import fCountryKey, fCountrySeries, fFetch, fRequestUrl, fYearRange


cEmcrFirstYear = 2021
cEcpFirstYear = 2023
cArrivalDimension = "Año de llegada a España"
cSexAndAgeTotals = ("18:451", "356:15668")
dCensusCountryGroups = {"birth": "147098", "nationality": "147092"}
dSources = {
  "em": {
    "tables": {"birth": "24289", "nationality": "24287"},
    "birth_dimension": "Países y Continentes",
    "unit": "Movimientos migratorios",
    "concept": "23187",
    "filters": cSexAndAgeTotals,
  },
  "emcr": {
    "tables": {"birth": "69694", "nationality": "69693"},
    "birth_dimension": "Países",
    "unit": "Migraciones",
    "concept": "417690",
    "filters": ("349:16473",),
  },
  "ecp": {
    "tables": {"birth": "59012", "nationality": "59011"},
    "birth_dimension": "Países y Continentes",
    "unit": "Personas",
    "concept": "23187",
    "filters": (),
  },
  "census": {
    "tables": {"birth": "70341", "nationality": "70340"},
    "birth_dimension": "Países",
    "unit": "Personas",
    "concept": "17338",
    "filters": cSexAndAgeTotals,
  },
}


def fDownload(pUrl: str) -> tuple[list, str | None]:
  try:
    vPayload = fFetch(pUrl)
    if not isinstance(vPayload, list):
      raise ValueError("INE returned an unexpected response for this resource.")
    return vPayload, None
  except HTTPError as vError:
    vError.close()
    return [], f"INE API HTTP {vError.code}"
  except (OSError, ValueError, HTTPException) as vError:
    return [], str(vError)


def fTableRows(
  pSource: str,
  pCriterion: str,
  pCountry: str,
  pTimeFilter: tuple[str, str],
  pExtraFilters: tuple[str, ...] = (),
) -> tuple[dict, list[dict]]:
  dConfig = dSources[pSource]
  vTable = dConfig["tables"][pCriterion]
  vDimension = dConfig["birth_dimension"] if pCriterion == "birth" else "Nacionalidad"
  lFilters = (*dConfig["filters"], *pExtraFilters)
  lParameters = [("tv", vFilter) for vFilter in lFilters]
  lParameters.extend([pTimeFilter, ("tip", "AM")])
  vUrl = fRequestUrl("DATOS_TABLA", [vTable], lParameters)
  dSource = {
    "operation": pSource,
    "table": vTable,
    "source": f"https://www.ine.es/jaxiT3/Tabla.htm?t={vTable}",
    "api_url": vUrl,
  }

  lRows, vError = fDownload(vUrl)
  if vError is not None:
    return dSource | {"status": "request_failed", "error": vError}, []

  sValues = {"16473", dConfig["concept"]}
  sValues.update(vFilter.partition(":")[2] for vFilter in lFilters)
  lCandidates = fCountrySeries(lRows, vDimension, sValues, dConfig["unit"])
  vKey = fCountryKey(pCountry)
  lMatches = [(vName, dSeries) for vName, dSeries in lCandidates if fCountryKey(vName) == vKey]
  if not lMatches:
    return dSource | {
      "status": "country_not_listed" if lCandidates else "no_series",
      "available_labels": sorted({vName for vName, _ in lCandidates}),
    }, []
  return dSource | {"status": "found", "country_label": lMatches[0][0]}, [dSeries for _, dSeries in lMatches]


def fSingleSeries(
  pSource: str, pCriterion: str, pCountry: str, pDate: str
) -> tuple[dict, dict]:
  dSource, ldSeries = fTableRows(pSource, pCriterion, pCountry, ("date", pDate))
  if len(ldSeries) > 1:
    return dSource | {"status": "ambiguous_series"}, {}
  if not ldSeries:
    return dSource, {}
  return dSource | {"series": ldSeries[0].get("COD")}, ldSeries[0]


def fObservations(pSeries: dict):
  vData = pSeries.get("Data")
  if not isinstance(vData, list):
    return
  for dObservation in vData:
    if not isinstance(dObservation, dict) or dObservation.get("Secreto"):
      continue
    vCount = dObservation.get("Valor")
    vText = dObservation.get("Fecha")
    if type(vCount) not in (int, float) or not math.isfinite(vCount) or not isinstance(vText, str):
      continue
    try:
      vReference = date.fromisoformat(vText.partition("T")[0])
    except ValueError:
      continue
    vNumber = int(vCount) if int(vCount) == vCount else vCount
    yield vReference, vNumber, dObservation


def fAnnual(pSource: str, pCriterion: str, pCountry: str, pStart: int, pEnd: int) -> dict:
  dSource, dSeries = fSingleSeries(pSource, pCriterion, pCountry, f"{pStart:04d}0101:{pEnd:04d}1231")
  ldYears = []
  for vReference, vCount, dObservation in fObservations(dSeries):
    if not pStart <= vReference.year <= pEnd or dObservation.get("T3_Periodo") != "A":
      continue
    if dObservation.get("T3_TipoDato") == "Definitivo":
      ldYears.append({"year": vReference.year, "count": vCount})
  if len({dYear["year"] for dYear in ldYears}) != len(ldYears):
    return dSource | {"status": "ambiguous_years", "years": []}
  if not ldYears and dSource["status"] == "found":
    dSource["status"] = "no_observations"
  return dSource | {"years": sorted(ldYears, key=lambda pYear: pYear["year"])}


def fEstimates(pCriterion: str, pCountry: str, pYears: set[int]) -> dict:
  vLast = max(pYears)
  vEnd = f"{vLast + 1:04d}0101" if vLast < 9999 else "99991231"
  dSource, dSeries = fSingleSeries("ecp", pCriterion, pCountry, f"{min(pYears):04d}0401:{vEnd}")
  dYears = {}
  for vReference, vCount, _ in fObservations(dSeries):
    if vReference.day != 1 or vReference.month not in (1, 4, 7, 10):
      continue
    # An observation dated 1 January belongs to the preceding year's fourth quarter.
    vThrough = vReference - timedelta(days=1)
    if vThrough.year not in pYears:
      continue
    vQuarter = (vThrough.month - 1) // 3 + 1
    dQuarters = dYears.setdefault(vThrough.year, {})
    if vQuarter in dQuarters:
      return dSource | {"status": "ambiguous_quarters", "years": []}
    dQuarters[vQuarter] = {"quarter": vQuarter, "through": vThrough.isoformat(), "count": vCount}

  ldYears = []
  for vYear, dQuarters in sorted(dYears.items()):
    ldQuarters = [dQuarters[vQuarter] for vQuarter in sorted(dQuarters)]
    ldYears.append({
      "year": vYear,
      "quarters": ldQuarters,
      "partial_sum": sum(dQuarter["count"] for dQuarter in ldQuarters),
    })
  if not ldYears and dSource["status"] == "found":
    dSource["status"] = "no_observations"
  return dSource | {"years": ldYears}


def fFlows(pCriterion: str, pCountry: str, pYears: tuple[int, int]) -> dict:
  vStart, vEnd = pYears
  lRanges = []
  if vStart < cEmcrFirstYear:
    lRanges.append(("em", vStart, min(vEnd, cEmcrFirstYear - 1)))
  if vEnd >= cEmcrFirstYear:
    lRanges.append(("emcr", max(vStart, cEmcrFirstYear), vEnd))

  with ThreadPoolExecutor(max_workers=len(lRanges)) as vPool:
    lTasks = [
      vPool.submit(fAnnual, vSource, pCriterion, pCountry, vFirst, vLast)
      for vSource, vFirst, vLast in lRanges
    ]
    ldAnnual = [vTask.result() for vTask in lTasks]

  ldYears = [dYear for dAnnual in ldAnnual for dYear in dAnnual["years"]]
  sMissing = set(range(vStart, vEnd + 1)) - {dYear["year"] for dYear in ldYears}
  dResult = {
    "annual_sources": ldAnnual,
    "definitive_total": sum(dYear["count"] for dYear in ldYears) if ldYears else None,
    "missing_definitive_years": sorted(sMissing),
  }
  sEstimateYears = {vYear for vYear in sMissing if vYear >= cEcpFirstYear}
  if sEstimateYears:
    dResult["first_estimates"] = fEstimates(pCriterion, pCountry, sEstimateYears)
  return dResult


def fResidents(pCriterion: str, pCountry: str, pYears: tuple[int, int]) -> dict:
  vTable = dSources["census"]["tables"][pCriterion]
  vGroup = dCensusCountryGroups[pCriterion]
  vLookup = fRequestUrl("VALORES_GRUPOSTABLA", [vTable, vGroup], [("det", "1")])
  dLookup = {"api_url": vLookup, "source": f"https://www.ine.es/jaxiT3/Tabla.htm?t={vTable}"}
  ldValues, vError = fDownload(vLookup)
  if vError is not None:
    return dLookup | {"status": "request_failed", "error": vError}

  ldLabels = [
    dValue for dValue in ldValues
    if isinstance(dValue, dict) and isinstance(dValue.get("Nombre"), str)
  ]
  vKey = fCountryKey(pCountry)
  ldMatches = [dValue for dValue in ldLabels if fCountryKey(dValue["Nombre"]) == vKey]
  if len(ldMatches) != 1:
    return dLookup | {
      "status": "ambiguous_country" if ldMatches else "country_not_listed",
      "available_labels": sorted({dValue["Nombre"] for dValue in ldMatches or ldLabels}),
    }

  dCountry = ldMatches[0]
  dVariable = dCountry.get("Variable")
  vVariableId = str(dVariable.get("Id")) if isinstance(dVariable, dict) else ""
  vValueId = str(dCountry.get("Id"))
  if not vVariableId.isdecimal() or not vValueId.isdecimal():
    return dLookup | {"status": "country_filter_unavailable"}
  vFilter = f"{vVariableId}:{vValueId}"
  dSource, ldSeries = fTableRows("census", pCriterion, pCountry, ("nult", "1"), (vFilter,))
  dSource["country_lookup_url"] = vLookup
  lCounts = []
  for dSeries in ldSeries:
    vLabel = next(
      (
        dMeta.get("Nombre") for dMeta in dSeries["MetaData"]
        if isinstance(dMeta, dict) and dMeta.get("T3_Variable") == cArrivalDimension
      ),
      None,
    )
    for vReference, vCount, _ in fObservations(dSeries):
      lCounts.append((vReference, vLabel, vCount))
  if not lCounts:
    if dSource["status"] == "found":
      dSource["status"] = "no_observations"
    return dSource

  vReference = max(vDate for vDate, _, _ in lCounts)
  dSource["reference_date"] = vReference.isoformat()
  vStart, vEnd = pYears
  sCovered = set()
  ldCohorts = []
  for vDate, vLabel, vCount in lCounts:
    if vDate != vReference or not isinstance(vLabel, str):
      continue
    vMatch = re.fullmatch(r"([0-9]{4})(?:-([0-9]{4}))?", vLabel)
    if vMatch is None:
      continue
    vFirst = int(vMatch[1])
    vLast = int(vMatch[2] or vMatch[1])
    if not vStart <= vFirst <= vLast <= vEnd:
      continue
    sYears = set(range(vFirst, vLast + 1))
    if sCovered.intersection(sYears):
      return dSource | {"status": "overlapping_cohorts"}
    sCovered.update(sYears)
    ldCohorts.append({"arrival_period": vLabel, "count": vCount})

  return dSource | {
    "status": "found" if ldCohorts else "no_cohorts",
    "cohorts": sorted(ldCohorts, key=lambda pCohort: pCohort["arrival_period"]),
    "total": sum(dCohort["count"] for dCohort in ldCohorts) if ldCohorts else None,
    "uncovered_arrival_years": sorted(set(range(vStart, vEnd + 1)) - sCovered),
  }


def fMain() -> None:
  vParser = argparse.ArgumentParser(description="Read immigration flows and residents by arrival year from INE.")
  vParser.add_argument("country", help="Country name as listed by INE.")
  vParser.add_argument("--years", type=fYearRange, metavar="START:END", required=True)
  vParser.add_argument("--by", choices=("birth", "nationality"), default="birth")
  vParser.add_argument("--measure", choices=("flows", "residents", "both"), default="flows")
  vArgs = vParser.parse_args()
  if not vArgs.country.strip():
    vParser.error("Provide a country name.")

  dMeasures = {"flows": fFlows, "residents": fResidents}
  lMeasures = list(dMeasures) if vArgs.measure == "both" else [vArgs.measure]
  dOutput = {"country": vArgs.country, "criterion": vArgs.by, "years": list(vArgs.years)}
  with ThreadPoolExecutor(max_workers=len(lMeasures)) as vPool:
    dTasks = {
      vMeasure: vPool.submit(dMeasures[vMeasure], vArgs.by, vArgs.country, vArgs.years)
      for vMeasure in lMeasures
    }
    for vMeasure, vTask in dTasks.items():
      dOutput[vMeasure] = vTask.result()
  print(json.dumps(dOutput, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  fMain()
