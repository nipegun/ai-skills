#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import csv
import io
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError

from indec import cMaximumBytes, cPortal, fDecode, fFetch, fFold, fMatches, fPositive


cSpreadsheet = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
cRelationshipId = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
cPricesTopic = cPortal + "/indec/web/Nivel4-Tema-3-5-31"
cPricesMetadata = cPortal + "/ftp/cuadros/economia/serie_ipc_metadatos.txt"
dPricesFiles = {
  "divisiones": cPortal + "/ftp/cuadros/economia/serie_ipc_divisiones.csv",
  "aperturas": cPortal + "/ftp/cuadros/economia/serie_ipc_aperturas.csv",
}


def fMonth(pText: str) -> str:
  vMatch = re.fullmatch(r"([0-9]{4})-?(0[1-9]|1[0-2])", pText)
  if not vMatch or vMatch[1] == "0000":
    raise argparse.ArgumentTypeError("Use YYYY-MM or YYYYMM for a month.")
  return vMatch[1] + vMatch[2]


def fNumber(pText: str):
  vText = pText.strip()
  if not vText or vText.upper() == "NA":
    return None
  try:
    return float(vText.replace(",", "."))
  except ValueError:
    return vText


def fPriceData(pArgs) -> dict:
  if pArgs.desde and pArgs.hasta and pArgs.desde > pArgs.hasta:
    raise ValueError("The start month must be no later than the end month.")
  vBody, dInfo = fFetch(dPricesFiles[pArgs.archivo])
  vReader = csv.DictReader(io.StringIO(fDecode(vBody), newline=""), delimiter=";")
  sColumns = {"Codigo", "Periodo", "Indice_IPC", "v_m_IPC", "v_i_a_IPC", "Region"}
  if not sColumns.issubset(vReader.fieldnames or []):
    raise ValueError("The INDEC IPC file has an unexpected column layout.")
  vDescriptionColumn = next((vField for vField in vReader.fieldnames if vField.startswith("Descripcion")), None)
  if vDescriptionColumn is None:
    raise ValueError("The IPC file does not include a description column.")

  vRegion = fFold(pArgs.region)
  vCode = pArgs.codigo if pArgs.codigo is not None else "0"
  vDescription = fFold(pArgs.descripcion or "")
  ldRows = []
  sRegions = set()
  for dRow in vReader:
    sRegions.add(dRow["Region"])
    if fFold(dRow["Region"]) != vRegion:
      continue
    if vDescription:
      vSelected = fFold(dRow[vDescriptionColumn]) == vDescription
    else:
      vSelected = dRow["Codigo"] == vCode
    if vSelected:
      ldRows.append(dRow)
  ldRows.sort(key=lambda pRow: pRow["Periodo"])
  lPeriods = [dRow["Periodo"] for dRow in ldRows]
  ldSelected = [
    dRow for dRow in ldRows
    if (not pArgs.desde or dRow["Periodo"] >= pArgs.desde)
    and (not pArgs.hasta or dRow["Periodo"] <= pArgs.hasta)
  ]
  if ldSelected and not pArgs.desde and not pArgs.hasta:
    vLatest = ldSelected[-1]["Periodo"]
    ldSelected = [dRow for dRow in ldSelected if dRow["Periodo"] == vLatest]

  return dInfo | {
    "topic": cPricesTopic,
    "metadata": cPricesMetadata,
    "base": "diciembre 2016 = 100",
    "coverage": [lPeriods[0], lPeriods[-1]] if lPeriods else [],
    "available_regions": sorted(sRegions),
    "data": [
      {
        "code": dRow["Codigo"],
        "description": dRow[vDescriptionColumn],
        "classification": dRow.get("Clasificador"),
        "region": dRow["Region"],
        "period": dRow["Periodo"],
        "index": fNumber(dRow["Indice_IPC"]),
        "monthly_percent": fNumber(dRow["v_m_IPC"]),
        "year_on_year_percent": fNumber(dRow["v_i_a_IPC"]),
      }
      for dRow in ldSelected
    ],
  }


def fReadWorkbook(pFile: str) -> tuple[bytes, dict]:
  if pFile.startswith(("http://", "https://")):
    return fFetch(pFile)
  vPath = Path(pFile).resolve()
  if vPath.stat().st_size > cMaximumBytes:
    raise ValueError("The workbook exceeds 32 MiB. Select a smaller official table.")
  return vPath.read_bytes(), {"source": str(vPath)}


def fXml(pWorkbook: zipfile.ZipFile, pName: str) -> ET.Element:
  if pWorkbook.getinfo(pName).file_size > cMaximumBytes:
    raise ValueError("A worksheet is too large to read with this command.")
  return ET.fromstring(pWorkbook.read(pName))


def fWorkbookSheets(pWorkbook: zipfile.ZipFile) -> dict[str, str]:
  vBook = fXml(pWorkbook, "xl/workbook.xml")
  vRelationships = fXml(pWorkbook, "xl/_rels/workbook.xml.rels")
  dTargets = {
    dLink.get("Id"): dLink.get("Target")
    for dLink in vRelationships if (dLink.get("Type") or "").endswith("/worksheet")
  }
  dSheets = {}
  for vSheet in vBook.findall(f"{cSpreadsheet}sheets/{cSpreadsheet}sheet"):
    vTarget = dTargets.get(vSheet.get(cRelationshipId))
    if not vTarget:
      continue
    vPath = vTarget.lstrip("/") if vTarget.startswith("/") else posixpath.normpath("xl/" + vTarget)
    dSheets[vSheet.get("name")] = vPath
  return dSheets


def fTextRun(pNode: ET.Element) -> str:
  return "".join(vPart.text or "" for vPart in pNode.iter(f"{cSpreadsheet}t"))


def fCell(pCell: ET.Element, pStrings: list[str]):
  vType = pCell.get("t")
  if vType == "inlineStr":
    return fTextRun(pCell)
  vText = pCell.findtext(f"{cSpreadsheet}v")
  if vText is None:
    return None
  if vType == "s":
    return pStrings[int(vText)]
  if vType == "b":
    return vText == "1"
  if vType in {"str", "e", "d"}:
    return vText
  if re.fullmatch(r"[+-]?[0-9]+", vText):
    return int(vText)
  return fNumber(vText)


def fWorkbookData(pArgs) -> dict:
  vBody, dInfo = fReadWorkbook(pArgs.archivo)
  with zipfile.ZipFile(io.BytesIO(vBody)) as vWorkbook:
    dSheets = fWorkbookSheets(vWorkbook)
    if not dSheets:
      raise ValueError("The XLSX package has no worksheets.")
    lSheets = list(dSheets)
    if pArgs.hoja in dSheets:
      vName = pArgs.hoja
    else:
      vIndex = int(pArgs.hoja) if pArgs.hoja.isdecimal() else 0
      if not 1 <= vIndex <= len(lSheets):
        raise ValueError(f"Choose a worksheet from: {', '.join(lSheets)}")
      vName = lSheets[vIndex - 1]
    lStrings = []
    if "xl/sharedStrings.xml" in vWorkbook.namelist():
      lStrings = [fTextRun(vNode) for vNode in fXml(vWorkbook, "xl/sharedStrings.xml")]
    vSheet = fXml(vWorkbook, dSheets[vName])

  ldRows = []
  for vRow in vSheet.findall(f"{cSpreadsheet}sheetData/{cSpreadsheet}row"):
    dCells = {}
    for vCell in vRow.findall(f"{cSpreadsheet}c"):
      vValue = fCell(vCell, lStrings)
      if vValue is not None and vValue != "":
        dCells[vCell.get("r")] = vValue
    if dCells:
      ldRows.append({"row": vRow.get("r"), "cells": dCells})
  ldMatch = [
    dRow for dRow in ldRows
    if fMatches(pArgs.filtrar, " ".join(str(vValue) for vValue in dRow["cells"].values()))
  ]
  return dInfo | {
    "sheets": lSheets,
    "sheet": vName,
    "context_rows": ldRows[:pArgs.encabezados],
    "matched_rows": len(ldMatch),
    "rows": ldMatch[:pArgs.limite],
  }


def fMain() -> int:
  vParser = argparse.ArgumentParser(description="Read public INDEC spreadsheets and IPC time series.")
  vCommands = vParser.add_subparsers(dest="comando", required=True)
  vWorkbook = vCommands.add_parser("xlsx", help="Read a worksheet from an official XLSX file.")
  vWorkbook.add_argument("archivo", help="Official URL or local XLSX path.")
  vWorkbook.add_argument("--hoja", default="1", help="Worksheet name or one-based position.")
  vWorkbook.add_argument("--filtrar", default="")
  vWorkbook.add_argument("--encabezados", type=fPositive, default=6)
  vWorkbook.add_argument("--limite", type=fPositive, default=30)
  vWorkbook.set_defaults(handler=fWorkbookData)

  vPrices = vCommands.add_parser("ipc", help="Read the national or regional CPI from INDEC CSV files.")
  vPrices.add_argument("--archivo", choices=dPricesFiles, default="divisiones")
  vPrices.add_argument("--region", default="Nacional")
  vCriterion = vPrices.add_mutually_exclusive_group()
  vCriterion.add_argument("--codigo")
  vCriterion.add_argument("--descripcion")
  vPrices.add_argument("--desde", type=fMonth)
  vPrices.add_argument("--hasta", type=fMonth)
  vPrices.set_defaults(handler=fPriceData)

  vArgs = vParser.parse_args()
  try:
    dOutput = vArgs.handler(vArgs)
  except HTTPError as vError:
    vError.close()
    print(f"HTTP {vError.code} from {vError.url}", file=sys.stderr)
    return 1
  except (OSError, ValueError, HTTPException, KeyError, IndexError, ET.ParseError, zipfile.BadZipFile) as vError:
    print(str(vError), file=sys.stderr)
    return 1
  print(json.dumps(dOutput, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(fMain())
