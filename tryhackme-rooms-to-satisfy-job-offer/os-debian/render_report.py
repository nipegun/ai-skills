#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Render a self-contained HTML report from reviewed recommendation data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from manage_rooms import Localiser, cLocales


cOutputFilename = "rooms-to-satisfy-offer.html"
cAllowedTiers = {"free", "premium", "max", "unknown"}
cStyles = """
:root {
  color-scheme: light dark;
  --background: #f4f6fb;
  --surface: #ffffff;
  --surface-muted: #eef1f8;
  --text: #182033;
  --text-muted: #5c6578;
  --border: #d8deeb;
  --accent: #5b50d6;
  --accent-soft: #ebe9ff;
  --free: #087a55;
  --premium: #a64b00;
  --maximum: #9b2c8f;
  --shadow: 0 18px 48px rgba(33, 43, 74, 0.10);
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #10131c;
    --surface: #191e2b;
    --surface-muted: #222838;
    --text: #edf0f7;
    --text-muted: #b3bbcb;
    --border: #343c50;
    --accent: #a8a0ff;
    --accent-soft: #2d285c;
    --free: #5bd8ad;
    --premium: #ffb56f;
    --maximum: #f5a1eb;
    --shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  }
}

* {
  box-sizing: border-box;
}

html {
  background: var(--background);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55;
}

body {
  margin: 0;
  min-width: 0;
}

main {
  margin: 0 auto;
  max-width: 72rem;
  min-width: 0;
  padding: 2.5rem 1.25rem 4rem;
  width: 100%;
}

main > *,
.metric-grid > *,
.table-scroll > * {
  min-width: 0;
}

h1,
h2,
h3 {
  line-height: 1.2;
  margin-top: 0;
}

h1 {
  font-size: clamp(2rem, 6vw, 3.5rem);
  letter-spacing: -0.04em;
  margin-bottom: 0.75rem;
}

h2 {
  font-size: clamp(1.4rem, 4vw, 2rem);
  margin-bottom: 1rem;
}

h3 {
  font-size: 1.15rem;
  margin-bottom: 0.8rem;
}

a {
  color: var(--accent);
  font-weight: 700;
  overflow-wrap: anywhere;
  text-underline-offset: 0.16em;
}

.eyebrow {
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  margin: 0 0 0.65rem;
  text-transform: uppercase;
}

.lede,
.section-description,
.footer-note {
  color: var(--text-muted);
}

.lede {
  font-size: 1.08rem;
  margin: 0;
  max-width: 58rem;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 1rem;
  box-shadow: var(--shadow);
  margin-top: 1.5rem;
  min-width: 0;
  padding: clamp(1rem, 4vw, 1.75rem);
}

.offer-text {
  background: var(--surface-muted);
  border-left: 0.3rem solid var(--accent);
  border-radius: 0.65rem;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 0.92rem;
  margin: 0;
  overflow-wrap: anywhere;
  padding: 1rem;
  white-space: pre-wrap;
}

.metric-grid {
  display: grid;
  gap: 0.8rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 10rem), 1fr));
  margin-top: 1rem;
}

.metric {
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 0.75rem;
  min-width: 0;
  padding: 0.9rem;
}

.metric strong {
  display: block;
  font-size: 1.45rem;
  line-height: 1.1;
}

.metric span {
  color: var(--text-muted);
  font-size: 0.82rem;
}

.report-section {
  margin-top: 2rem;
}

.table-scroll {
  border: 1px solid var(--border);
  border-radius: 0.85rem;
  overflow-x: auto;
}

table {
  border-collapse: collapse;
  min-width: 42rem;
  width: 100%;
}

table.modules {
  min-width: 58rem;
}

table.modules th {
  white-space: nowrap;
}

table.modules th:nth-child(1),
table.modules td:nth-child(1) {
  min-width: 10rem;
}

table.modules th:nth-child(4),
table.modules td:nth-child(4) {
  min-width: 13rem;
}

table.modules th:nth-child(5),
table.modules td:nth-child(5) {
  min-width: 16rem;
}

.module-rooms strong {
  display: block;
  font-weight: 700;
}

.module-rooms .muted {
  color: var(--text-muted);
  display: block;
  font-size: 0.8rem;
  margin-top: 0.3rem;
}

.room-list {
  margin: 0.25rem 0 0;
  padding-left: 1.05rem;
}

.room-list li {
  margin-bottom: 0.15rem;
  overflow-wrap: anywhere;
}

.module-time {
  white-space: nowrap;
}

caption.sr-only {
  height: 1px;
  margin: -1px;
  overflow: hidden;
  padding: 0;
  position: absolute;
  width: 1px;
}

th,
td {
  border-bottom: 1px solid var(--border);
  overflow-wrap: anywhere;
  padding: 0.85rem 0.9rem;
  text-align: left;
  vertical-align: top;
}

th {
  background: var(--surface-muted);
  color: var(--text-muted);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

tbody tr:last-child td {
  border-bottom: 0;
}

tbody tr:hover {
  background: var(--accent-soft);
}

.tier {
  border: 1px solid currentColor;
  border-radius: 999px;
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  padding: 0.18rem 0.55rem;
  white-space: nowrap;
}

.tier-free {
  color: var(--free);
}

.tier-premium {
  color: var(--premium);
}

.tier-max {
  color: var(--maximum);
}

.footer-note {
  font-size: 0.82rem;
  margin-top: 2rem;
}

@media (max-width: 40rem) {
  main {
    padding: 1.25rem 0.75rem 2.5rem;
  }

  .card {
    border-radius: 0.8rem;
    padding: 1rem;
  }

  table {
    font-size: 0.86rem;
    min-width: 36rem;
  }

  table.modules {
    min-width: 50rem;
  }

  th,
  td {
    padding: 0.7rem;
  }
}

@media print {
  :root {
    --background: #ffffff;
    --surface: #ffffff;
    --surface-muted: #f3f4f7;
    --text: #111111;
    --text-muted: #444444;
    --border: #bbbbbb;
    --accent: #3429a5;
    --shadow: none;
  }

  main {
    max-width: none;
    padding: 0;
  }

  .card {
    break-inside: avoid;
    box-shadow: none;
  }

  .table-scroll {
    overflow: visible;
  }

  table {
    min-width: 0;
  }
}
"""


class ReportError(RuntimeError):
  """Report invalid input without rendering untrusted markup."""


def fBuildParser() -> argparse.ArgumentParser:
  """Create the renderer command-line interface."""

  vParser = argparse.ArgumentParser(
    description="Render reviewed TryHackMe recommendations as a local HTML report."
  )
  vParser.add_argument("--input", required=True, help="Path to the report JSON file.")
  vParser.add_argument(
    "--output-directory",
    default=str(Path.cwd()),
    help="Directory that will receive rooms-to-satisfy-offer.html.",
  )
  return vParser


def fRequireText(pValue: object, pField: str) -> str:
  """Return a required non-empty string."""

  if not isinstance(pValue, str) or not pValue.strip():
    raise ReportError(f"{pField} must be a non-empty string.")
  return pValue.strip()


def fValidateCanonicalUrl(pUrl: str, pPathSegment: str) -> None:
  """Restrict report links to canonical TryHackMe room or module URLs."""

  vParsedUrl = urlparse(pUrl)
  if (
    vParsedUrl.scheme != "https"
    or vParsedUrl.netloc != "tryhackme.com"
    or re.fullmatch(
      rf"/{pPathSegment}/[A-Za-z0-9_-]+", vParsedUrl.path.rstrip("/")
    ) is None
    or vParsedUrl.params
    or vParsedUrl.query
    or vParsedUrl.fragment
  ):
    raise ReportError(f"Non-canonical TryHackMe {pPathSegment} URL: {pUrl}")


def fValidateRoomUrl(pUrl: str) -> None:
  """Restrict report links to canonical TryHackMe room URLs."""

  fValidateCanonicalUrl(pUrl, "room")


def fValidateModuleUrl(pUrl: str) -> None:
  """Restrict report links to canonical TryHackMe module URLs."""

  fValidateCanonicalUrl(pUrl, "module")


def fRequireOptionalCount(pValue: object, pField: str) -> int | None:
  """Return an optional non-negative integer field."""

  if pValue is None:
    return None
  if not isinstance(pValue, int) or isinstance(pValue, bool) or pValue < 0:
    raise ReportError(f"{pField} must be a non-negative integer when present.")
  return pValue


def fLoadReport(pInputPath: Path) -> dict[str, object]:
  """Load and validate the model-reviewed report contract."""

  try:
    with pInputPath.open("r", encoding="utf-8") as vFile:
      vPayload = json.load(vFile)
  except (OSError, json.JSONDecodeError) as vError:
    raise ReportError(f"Could not read report data from {pInputPath}: {vError}") from vError

  if not isinstance(vPayload, dict):
    raise ReportError("The report root must be a JSON object.")

  vLocale = fRequireText(vPayload.get("locale"), "locale")
  if vLocale not in cLocales:
    raise ReportError(f"Unsupported locale: {vLocale}")
  fRequireText(vPayload.get("offerTranslated"), "offerTranslated")
  fRequireText(vPayload.get("roleAssessment"), "roleAssessment")

  lSections = vPayload.get("sections")
  if not isinstance(lSections, list) or not lSections:
    raise ReportError("sections must be a non-empty list.")

  for vSectionIndex, dSection in enumerate(lSections):
    if not isinstance(dSection, dict):
      raise ReportError(f"sections[{vSectionIndex}] must be an object.")
    fRequireText(dSection.get("title"), f"sections[{vSectionIndex}].title")
    lRows = dSection.get("rows")
    if not isinstance(lRows, list) or not lRows:
      raise ReportError(f"sections[{vSectionIndex}].rows must be a non-empty list.")

    for vRowIndex, dRow in enumerate(lRows):
      if not isinstance(dRow, dict):
        raise ReportError(
          f"sections[{vSectionIndex}].rows[{vRowIndex}] must be an object."
        )
      fRequireText(dRow.get("room"), "room")
      vUrl = fRequireText(dRow.get("url"), "url")
      fValidateRoomUrl(vUrl)
      vTier = fRequireText(dRow.get("tier"), "tier").lower()
      if vTier not in cAllowedTiers:
        raise ReportError(f"Unsupported room tier: {vTier}")
      fRequireText(dRow.get("why"), "why")

  lModuleSections = vPayload.get("moduleSections", [])
  if not isinstance(lModuleSections, list):
    raise ReportError("moduleSections must be a list.")

  for vSectionIndex, dSection in enumerate(lModuleSections):
    if not isinstance(dSection, dict):
      raise ReportError(f"moduleSections[{vSectionIndex}] must be an object.")
    fRequireText(dSection.get("title"), f"moduleSections[{vSectionIndex}].title")
    lRows = dSection.get("rows")
    if not isinstance(lRows, list) or not lRows:
      raise ReportError(
        f"moduleSections[{vSectionIndex}].rows must be a non-empty list."
      )

    for vRowIndex, dRow in enumerate(lRows):
      if not isinstance(dRow, dict):
        raise ReportError(
          f"moduleSections[{vSectionIndex}].rows[{vRowIndex}] must be an object."
        )
      fRequireText(dRow.get("module"), "module")
      vUrl = fRequireText(dRow.get("url"), "url")
      fValidateModuleUrl(vUrl)
      vTier = fRequireText(dRow.get("tier"), "tier").lower()
      if vTier not in cAllowedTiers:
        raise ReportError(f"Unsupported module tier: {vTier}")
      fRequireText(dRow.get("why"), "why")
      fRequireOptionalCount(dRow.get("timeMinutes"), "timeMinutes")
      fRequireOptionalCount(dRow.get("roomCount"), "roomCount")
      lRecommendedRooms = dRow.get("recommendedRooms", [])
      if not isinstance(lRecommendedRooms, list):
        raise ReportError("recommendedRooms must be a list.")
      for vRoomIndex, vRoomName in enumerate(lRecommendedRooms):
        fRequireText(vRoomName, f"recommendedRooms[{vRoomIndex}]")

  lGaps = vPayload.get("gaps", [])
  if not isinstance(lGaps, list):
    raise ReportError("gaps must be a list.")
  for vGapIndex, dGap in enumerate(lGaps):
    if not isinstance(dGap, dict):
      raise ReportError(f"gaps[{vGapIndex}] must be an object.")
    fRequireText(dGap.get("requirement"), "requirement")
    fRequireText(dGap.get("coverage"), "coverage")

  dCatalogue = vPayload.get("catalogue", {})
  if not isinstance(dCatalogue, dict):
    raise ReportError("catalogue must be an object.")
  for vKey in (
    "roomCount",
    "validatedUrlCount",
    "freeCount",
    "premiumCount",
    "moduleCount",
  ):
    vValue = dCatalogue.get(vKey, 0)
    if not isinstance(vValue, int) or isinstance(vValue, bool) or vValue < 0:
      raise ReportError(f"catalogue.{vKey} must be a non-negative integer.")

  return vPayload


def fEscape(pValue: object) -> str:
  """Escape text for safe insertion into HTML."""

  return html.escape(str(pValue), quote=True)


def fFormatNumber(pValue: int, pLocale: str) -> str:
  """Format metric integers without changing process locale."""

  vFormatted = f"{pValue:,}"
  return vFormatted.replace(",", ".") if pLocale.startswith("es-") else vFormatted


def fTierLabel(pTier: str, pLocaliser: Localiser) -> str:
  """Translate one normalised access tier."""

  dTierKeys = {
    "free": "tier_free",
    "premium": "tier_premium",
    "max": "tier_max",
    "unknown": "tier_unknown",
  }
  return pLocaliser.mText(dTierKeys[pTier])


def fRenderRecommendationTable(
  pSection: dict[str, object],
  pLocaliser: Localiser,
) -> str:
  """Render one recommendation group as an accessible HTML table."""

  lRows: list[str] = []
  for dRow in pSection["rows"]:
    vTier = str(dRow["tier"]).lower()
    lRows.append(
      "<tr>"
      f'<td><a href="{fEscape(dRow["url"])}" target="_blank" '
      f'rel="noopener noreferrer">{fEscape(dRow["room"])}</a></td>'
      f'<td><span class="tier tier-{fEscape(vTier)}">'
      f'{fEscape(fTierLabel(vTier, pLocaliser))}</span></td>'
      f'<td>{fEscape(dRow["why"])}</td>'
      "</tr>"
    )

  vDescription = str(pSection.get("description", "")).strip()
  vDescriptionHtml = (
    f'<p class="section-description">{fEscape(vDescription)}</p>'
    if vDescription
    else ""
  )
  return (
    '<section class="report-section">'
    f'<h2>{fEscape(pSection["title"])}</h2>'
    f'{vDescriptionHtml}'
    '<div class="table-scroll">'
    '<table>'
    f'<caption class="sr-only">{fEscape(pSection["title"])}</caption>'
    '<thead><tr>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_room_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_tier_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_relevance_column"))}</th>'
    '</tr></thead>'
    f'<tbody>{"".join(lRows)}</tbody>'
    '</table>'
    '</div>'
    '</section>'
  )


def fFormatDuration(
  pMinutes: int | None,
  pLocale: str,
  pLocaliser: Localiser,
) -> str:
  """Express a module duration in whole hours, or minutes below one hour."""

  if pMinutes is None:
    return "—"
  if pMinutes < 60:
    return pLocaliser.mText(
      "report_minutes_short",
      value=fFormatNumber(pMinutes, pLocale),
    )
  vHours = round(pMinutes / 60)
  return pLocaliser.mText(
    "report_hours_short",
    value=fFormatNumber(max(1, vHours), pLocale),
  )


def fRenderModuleRoomsCell(
  pRow: dict[str, object],
  pLocale: str,
  pLocaliser: Localiser,
) -> str:
  """Describe how many rooms a module holds and which are already recommended."""

  vRoomCount = pRow.get("roomCount")
  lRecommendedRooms = [
    str(vRoomName) for vRoomName in pRow.get("recommendedRooms", [])
  ]
  lParts: list[str] = []

  if isinstance(vRoomCount, int):
    lParts.append(
      "<strong>"
      + fEscape(
        pLocaliser.mText(
          "report_module_room_total_one"
          if vRoomCount == 1
          else "report_module_room_total",
          count=fFormatNumber(vRoomCount, pLocale),
        )
      )
      + "</strong>"
    )
  if lRecommendedRooms:
    lParts.append(
      '<span class="muted">'
      + fEscape(
        pLocaliser.mText(
          "report_module_rooms_recommended_one"
          if len(lRecommendedRooms) == 1
          else "report_module_rooms_recommended",
          count=fFormatNumber(len(lRecommendedRooms), pLocale),
        )
      )
      + "</span>"
      + '<ul class="room-list">'
      + "".join(f"<li>{fEscape(vRoomName)}</li>" for vRoomName in lRecommendedRooms)
      + "</ul>"
    )
  if not lParts:
    return "<td>—</td>"
  return f'<td class="module-rooms">{"".join(lParts)}</td>'


def fRenderModuleTable(
  pSection: dict[str, object],
  pLocale: str,
  pLocaliser: Localiser,
) -> str:
  """Render one advised module group as an accessible HTML table."""

  lRows: list[str] = []
  for dRow in pSection["rows"]:
    vTier = str(dRow["tier"]).lower()
    vMinutes = dRow.get("timeMinutes")
    lRows.append(
      "<tr>"
      f'<td><a href="{fEscape(dRow["url"])}" target="_blank" '
      f'rel="noopener noreferrer">{fEscape(dRow["module"])}</a></td>'
      f'<td><span class="tier tier-{fEscape(vTier)}">'
      f'{fEscape(fTierLabel(vTier, pLocaliser))}</span></td>'
      f'<td class="module-time">'
      f'{fEscape(fFormatDuration(vMinutes if isinstance(vMinutes, int) else None, pLocale, pLocaliser))}</td>'
      f'{fRenderModuleRoomsCell(dRow, pLocale, pLocaliser)}'
      f'<td>{fEscape(dRow["why"])}</td>'
      "</tr>"
    )

  vDescription = str(pSection.get("description", "")).strip()
  vDescriptionHtml = (
    f'<p class="section-description">{fEscape(vDescription)}</p>'
    if vDescription
    else ""
  )
  return (
    '<section class="report-section">'
    f'<h2>{fEscape(pSection["title"])}</h2>'
    f'{vDescriptionHtml}'
    '<div class="table-scroll">'
    '<table class="modules">'
    f'<caption class="sr-only">{fEscape(pSection["title"])}</caption>'
    '<thead><tr>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_module_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_tier_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_module_time_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_module_rooms_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_relevance_column"))}</th>'
    '</tr></thead>'
    f'<tbody>{"".join(lRows)}</tbody>'
    '</table>'
    '</div>'
    '</section>'
  )


def fRenderGapsTable(
  pGaps: list[dict[str, object]],
  pLocaliser: Localiser,
) -> str:
  """Render requirements not fully covered by the catalogue."""

  if not pGaps:
    return ""
  lRows = [
    "<tr>"
    f'<td>{fEscape(dGap["requirement"])}</td>'
    f'<td>{fEscape(dGap["coverage"])}</td>'
    "</tr>"
    for dGap in pGaps
  ]
  return (
    '<section class="report-section">'
    f'<h2>{fEscape(pLocaliser.mText("report_gaps_heading"))}</h2>'
    '<div class="table-scroll">'
    '<table>'
    f'<caption class="sr-only">{fEscape(pLocaliser.mText("report_gaps_heading"))}</caption>'
    '<thead><tr>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_requirement_column"))}</th>'
    f'<th scope="col">{fEscape(pLocaliser.mText("report_coverage_column"))}</th>'
    '</tr></thead>'
    f'<tbody>{"".join(lRows)}</tbody>'
    '</table>'
    '</div>'
    '</section>'
  )


def fBuildHtml(pReport: dict[str, object]) -> str:
  """Build the complete escaped report in memory."""

  vLocale = str(pReport["locale"])
  vLocaliser = Localiser(vLocale)
  vDocumentTitle = str(
    pReport.get("documentTitle", vLocaliser.mText("report_default_title"))
  ).strip()
  vGeneratedAt = str(
    pReport.get(
      "generatedAt",
      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
  )
  dCatalogue = pReport.get("catalogue", {})
  lMetrics = [
    ("roomCount", "report_room_count"),
    ("validatedUrlCount", "report_validated_urls"),
    ("freeCount", "report_free_rooms"),
    ("premiumCount", "report_premium_rooms"),
  ]
  if int(dCatalogue.get("moduleCount", 0)) > 0:
    lMetrics.append(("moduleCount", "report_module_count"))
  lMetricCards = [
    '<div class="metric">'
    f'<strong>{fEscape(fFormatNumber(int(dCatalogue.get(vKey, 0)), vLocale))}</strong>'
    f'<span>{fEscape(vLocaliser.mText(vLabelKey))}</span>'
    '</div>'
    for vKey, vLabelKey in lMetrics
  ]
  lRecommendationSections = [
    fRenderRecommendationTable(dSection, vLocaliser)
    for dSection in pReport["sections"]
  ]
  lModuleSections = [
    fRenderModuleTable(dSection, vLocale, vLocaliser)
    for dSection in pReport.get("moduleSections", [])
  ]

  return (
    '<!doctype html>\n'
    f'<html lang="{fEscape(vLocale)}">\n'
    '<head>\n'
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    f'<title>{fEscape(vDocumentTitle)}</title>\n'
    f'<style>{cStyles}</style>\n'
    '</head>\n'
    '<body>\n'
    '<main>\n'
    f'<p class="eyebrow">{fEscape(vLocaliser.mText("report_eyebrow"))}</p>'
    f'<h1>{fEscape(vDocumentTitle)}</h1>'
    f'<p class="lede">{fEscape(vLocaliser.mText("report_lede"))}</p>'
    '<section class="card">'
    f'<h2>{fEscape(vLocaliser.mText("report_offer_heading"))}</h2>'
    f'<div class="offer-text">{fEscape(pReport["offerTranslated"])}</div>'
    '</section>'
    '<section class="card">'
    f'<h2>{fEscape(vLocaliser.mText("report_role_heading"))}</h2>'
    f'<p>{fEscape(pReport["roleAssessment"])}</p>'
    f'<h3>{fEscape(vLocaliser.mText("report_catalogue_heading"))}</h3>'
    f'<div class="metric-grid">{"".join(lMetricCards)}</div>'
    '</section>'
    f'{"".join(lRecommendationSections)}'
    f'{"".join(lModuleSections)}'
    f'{fRenderGapsTable(pReport.get("gaps", []), vLocaliser)}'
    '<p class="footer-note">'
    f'{fEscape(vLocaliser.mText("report_generated_label"))}: {fEscape(vGeneratedAt)}. '
    f'{fEscape(vLocaliser.mText("report_source_note"))}'
    '</p>'
    '</main>\n'
    '</body>\n'
    '</html>\n'
  )


def fMain(pArguments: list[str] | None = None) -> int:
  """Validate report data and create the fixed HTML output file."""

  vArguments = pArguments if pArguments is not None else sys.argv[1:]
  vParser = fBuildParser()
  dArguments = vars(vParser.parse_args(vArguments))

  try:
    vInputPath = Path(str(dArguments["input"])).expanduser().resolve(strict=True)
    vOutputDirectory = Path(str(dArguments["output_directory"])).expanduser().resolve(strict=True)
    if not vOutputDirectory.is_dir():
      raise ReportError(f"Output directory is not a directory: {vOutputDirectory}")

    dReport = fLoadReport(vInputPath)
    vHtml = fBuildHtml(dReport)
    vOutputPath = vOutputDirectory / cOutputFilename
    vOutputPath.write_text(vHtml, encoding="utf-8")
    os.chmod(vOutputPath, 0o644)
    vLocaliser = Localiser(str(dReport["locale"]))
    print(vLocaliser.mText("report_file_created", path=vOutputPath))
    return 0
  except (OSError, ReportError) as vError:
    print(f"Report generation stopped: {vError}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(fMain())
