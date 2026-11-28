#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import getpass
import json
import os
import re
import sys
import unicodedata
import warnings
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


cPortal = "https://www.indec.gob.ar"
cCatalog = "https://api.indec.gob.ar"
cOpenApi = cCatalog + "/api/openapi?v=2"
cSeries = "https://apis.datos.gob.ar/series/api"
cMaximumBytes = 32 * 1024 * 1024
sOtherOfficialHosts = {"apis.datos.gob.ar", "infra.datos.gob.ar"}


def fOfficialUrl(pUrl: str) -> str:
  vParts = urlsplit(pUrl)
  vHost = vParts.hostname or ""
  vOfficial = vHost in {"indec.gob.ar", "censo.gob.ar"} or vHost.endswith((".indec.gob.ar", ".censo.gob.ar"))
  if vParts.scheme != "https" or vParts.username or vParts.password or vParts.port not in (None, 443):
    raise ValueError("Use a public HTTPS URL from the INDEC or national data portals.")
  if not vOfficial and vHost not in sOtherOfficialHosts:
    raise ValueError(f"Unsupported source host: {vHost}")
  return pUrl


def fFetch(
  pUrl: str,
  pAccept: str = "*/*",
  pToken: str | None = None,
  pCount: bool = False,
) -> tuple[bytes, dict]:
  vRequest = Request(fOfficialUrl(pUrl), headers={"Accept": pAccept})
  if pToken:
    vRequest.add_unredirected_header("Authorization", f"Bearer {pToken}")
  if pCount:
    vRequest.add_header("Prefer", "count=exact")

  with urlopen(vRequest, timeout=25) as vReply:
    vSource = fOfficialUrl(vReply.geturl())
    vBody = vReply.read(cMaximumBytes + 1)
    dInfo = {"source": vSource, "content_type": vReply.headers.get("Content-Type", "")}
    vRange = vReply.headers.get("Content-Range")
    if vRange:
      dInfo["content_range"] = vRange
  if len(vBody) > cMaximumBytes:
    raise ValueError("Response exceeds 32 MiB. Narrow the query or use the official download.")
  if not vBody.strip():
    raise ValueError("The server returned an empty response.")
  return vBody, dInfo


def fDecode(pBody: bytes) -> str:
  try:
    return pBody.decode("utf-8-sig")
  except UnicodeDecodeError:
    return pBody.decode("cp1252")


def fJson(pUrl: str, pToken: str | None = None, pCount: bool = False) -> tuple[object, dict]:
  vBody, dInfo = fFetch(pUrl, "application/json", pToken, pCount)
  try:
    return json.loads(vBody), dInfo
  except (UnicodeDecodeError, json.JSONDecodeError) as vError:
    raise ValueError("The server returned a body other than valid JSON.") from vError


def fFold(pText: str) -> str:
  vNormalized = unicodedata.normalize("NFKD", pText.casefold())
  return " ".join("".join(vChar for vChar in vNormalized if not unicodedata.combining(vChar)).split())


def fMatches(pNeedle: str, pText: str) -> bool:
  vText = fFold(pText)
  return all(vTerm in vText for vTerm in fFold(pNeedle).split())


def fParameter(pText: str) -> tuple[str, str]:
  vName, vSeparator, vValue = pText.partition("=")
  if not vSeparator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", vName):
    raise argparse.ArgumentTypeError("Use NAME=VALUE for each query parameter.")
  return vName, vValue


def fPositive(pText: str) -> int:
  vValue = int(pText)
  if vValue < 1:
    raise argparse.ArgumentTypeError("Use a positive integer.")
  return vValue


def fSlug(pText: str) -> str:
  if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", pText):
    raise argparse.ArgumentTypeError("Use the service slug from the INDEC catalogue.")
  return pText


def fPortalTarget(pPage: str) -> str:
  if re.fullmatch(r"[0-9]+/[0-9]+/[0-9]+", pPage):
    pPage = "/Nivel4/Tema/" + pPage
  vUrl = fOfficialUrl(urljoin(cPortal + "/", pPage))
  vParts = urlsplit(vUrl)
  if vParts.hostname not in {"www.indec.gob.ar", "indec.gob.ar"}:
    return vUrl

  vPath = vParts.path
  if vPath.startswith("/indec/web/") and not vPath.startswith("/indec/web/Buscador-"):
    vPath = "/" + vPath.removeprefix("/indec/web/").replace("-", "/")
  return urlunsplit((vParts.scheme, vParts.netloc, vPath, vParts.query, ""))


class cPage(HTMLParser):
  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.lText = []
    self.lLinks = []
    self.dAnchor = None
    self.vIgnore = None

  def handle_starttag(self, pTag, pAttributes):
    if pTag in {"script", "style"}:
      self.vIgnore = pTag
    if pTag == "a" and self.vIgnore is None:
      self.mCloseAnchor()
      dAttributes = dict(pAttributes)
      self.dAnchor = {
        "href": dAttributes.get("href") or "",
        "view": dAttributes.get("data-view") or "",
        "parts": [],
      }
    if pTag == "img" and self.dAnchor is not None:
      vAlt = dict(pAttributes).get("alt")
      if vAlt and vAlt.strip():
        self.dAnchor["parts"].append(vAlt.strip())

  def handle_endtag(self, pTag):
    if pTag == self.vIgnore:
      self.vIgnore = None
    if pTag == "a":
      self.mCloseAnchor()

  def handle_data(self, pText):
    vText = " ".join(pText.split())
    if self.vIgnore is not None or not vText:
      return
    self.lText.append(vText)
    if self.dAnchor is not None:
      self.dAnchor["parts"].append(vText)

  def mCloseAnchor(self):
    if self.dAnchor is not None:
      vLabel = " ".join(self.dAnchor["parts"])
      self.lLinks.append((vLabel, self.dAnchor["href"], self.dAnchor["view"]))
      self.dAnchor = None


def fLinkUrl(pPage: str, pHref: str, pView: str) -> str | None:
  vHref = pHref.strip()
  if not vHref or vHref.startswith(("#", "javascript:")):
    if not pView:
      return None
    vHref = "/indec/web/" + pView.strip("/").replace("/", "-")
  if urlsplit(pPage).hostname in {"www.indec.gob.ar", "indec.gob.ar"}:
    vHref = re.sub(r"^(?:\.\./)*(ftp/|uploads/)", r"/\1", vHref)
  vLink = urljoin(pPage, vHref)
  vParts = urlsplit(vLink)
  return vLink if vParts.scheme in {"http", "https"} else None


def fPageOutput(pUrl: str, pFind: str, pLimit: int) -> dict:
  vBody, dInfo = fFetch(pUrl, "text/html")
  vPage = cPage()
  vPage.feed(fDecode(vBody))
  vPage.close()
  vPage.mCloseAnchor()
  vText = " ".join(vPage.lText)
  if "The URL you requested has been blocked" in vText:
    raise ValueError("The INDEC server blocked the page request.")
  ldLinks = []
  sSeen = set()
  for vLabel, vHref, vView in vPage.lLinks:
    vLink = fLinkUrl(dInfo["source"], vHref, vView)
    if not vLink or not fMatches(pFind, vLabel + " " + vLink):
      continue
    vKey = (vLabel, vLink)
    if vKey not in sSeen:
      sSeen.add(vKey)
      ldLinks.append({"label": vLabel, "url": vLink})
  return dInfo | {"text": vText[:3000], "matched_links": len(ldLinks), "links": ldLinks[:pLimit]}


def fTopic(pArgs) -> dict:
  return fPageOutput(fPortalTarget(pArgs.pagina), pArgs.filtrar, pArgs.limite)


def fCatalog(pArgs) -> dict:
  vUrl = cCatalog + "/api/datasets?" + urlencode({"page": pArgs.pagina})
  vPayload, dInfo = fJson(vUrl)
  if not isinstance(vPayload, dict) or not isinstance(vPayload.get("data"), dict):
    raise ValueError("The catalogue returned an unexpected response.")
  dPage = vPayload["data"]
  ldServices = []
  for dService in dPage.get("items", []):
    vSearchable = " ".join(str(dService.get(vKey, "")) for vKey in ("name", "slug", "description", "area"))
    if fMatches(pArgs.filtrar, vSearchable):
      ldServices.append({vKey: dService.get(vKey) for vKey in ("name", "slug", "area", "description", "columns")})
  return dInfo | {
    "page": dPage.get("page"),
    "total_pages": dPage.get("totalPages"),
    "catalogue_count": dPage.get("count"),
    "services": ldServices,
  }


def fSchema(pArgs) -> dict:
  vPayload, dInfo = fJson(cOpenApi)
  if not isinstance(vPayload, dict) or not isinstance(vPayload.get("spec"), dict):
    raise ValueError("The OpenAPI document is unavailable.")
  dSpec = vPayload["spec"]
  dPaths = dSpec.get("paths", {})
  vPath = "/" + pArgs.servicio
  if vPath not in dPaths:
    raise ValueError(f"Service not listed in OpenAPI: {pArgs.servicio}")
  dSchema = dSpec.get("components", {}).get("schemas", {}).get(pArgs.servicio)
  return dInfo | {"servers": dSpec.get("servers"), "path": vPath, "operation": dPaths[vPath], "schema": dSchema}


def fApiData(pArgs) -> dict:
  vToken = os.environ.get("INDEC_API_TOKEN", "").strip()
  if not vToken:
    if not sys.stdin.isatty():
      raise ValueError("Set INDEC_API_TOKEN or run this command in an interactive terminal to enter the token.")
    try:
      with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        vToken = getpass.getpass("Ingresá el token de la API del INDEC (entrada oculta) ").strip()
    except getpass.GetPassWarning as vError:
      raise ValueError("Hidden input is unavailable in this terminal. Set INDEC_API_TOKEN instead.") from vError
    except (EOFError, KeyboardInterrupt) as vError:
      raise ValueError("INDEC token entry was cancelled.") from vError
    if not vToken:
      raise ValueError("Token entry skipped. Use the INDEC reports and public tables when available.")
  lParameters = list(pArgs.param)
  if not any(vName == "limit" for vName, _ in lParameters):
    lParameters.append(("limit", "100"))
  vUrl = cCatalog + "/v1/" + pArgs.servicio + "?" + urlencode(lParameters)
  vPayload, dInfo = fJson(vUrl, vToken, pArgs.contar)
  return dInfo | {"response": vPayload}


def fSeriesJson(pUrl: str) -> tuple[object, dict]:
  try:
    import requests
  except ImportError:
    return fJson(pUrl)

  try:
    with requests.get(fOfficialUrl(pUrl), timeout=25, stream=True) as vReply:
      vReply.raise_for_status()
      dInfo = {"source": fOfficialUrl(vReply.url), "content_type": vReply.headers.get("Content-Type", "")}
      vBody = bytearray()
      for vChunk in vReply.iter_content(chunk_size=65536):
        vBody.extend(vChunk)
        if len(vBody) > cMaximumBytes:
          raise ValueError("Response exceeds 32 MiB. Narrow the requested series or date range.")
  except requests.RequestException as vError:
    raise ValueError(f"Series API request failed: {vError}") from vError

  try:
    return json.loads(vBody), dInfo
  except (UnicodeDecodeError, json.JSONDecodeError) as vError:
    raise ValueError("The Series API returned a body other than valid JSON.") from vError


def fSearchSeries(pArgs) -> dict:
  if pArgs.desplazamiento < 0:
    raise ValueError("The search offset must be zero or positive.")
  dParameters = {"q": pArgs.texto, "limit": pArgs.limite}
  if pArgs.desplazamiento:
    dParameters["start"] = pArgs.desplazamiento
  vUrl = cSeries + "/search/?" + urlencode(dParameters)
  vPayload, dInfo = fSeriesJson(vUrl)
  return dInfo | {"response": vPayload}


def fSeries(pArgs) -> dict:
  lParameters = [("ids", pArgs.ids)]
  if pArgs.desde:
    lParameters.append(("start_date", pArgs.desde))
  if pArgs.hasta:
    lParameters.append(("end_date", pArgs.hasta))
  if pArgs.limite:
    lParameters.append(("limit", str(pArgs.limite)))
  lParameters.append(("metadata", "full"))
  vUrl = cSeries + "/series/?" + urlencode(lParameters)
  vPayload, dInfo = fSeriesJson(vUrl)
  return dInfo | {"response": vPayload}


def fMain() -> int:
  vParser = argparse.ArgumentParser(description="Find and read official Argentine statistics from INDEC.")
  vCommands = vParser.add_subparsers(dest="comando", required=True)

  vTopic = vCommands.add_parser("tema", help="Read a topic, report listing or other official HTML page.")
  vTopic.add_argument("pagina", help="Portal URL, path or a topic identifier such as 3/5/31.")
  vTopic.add_argument("--filtrar", default="")
  vTopic.add_argument("--limite", type=fPositive, default=30)
  vTopic.set_defaults(handler=fTopic)

  vCatalog = vCommands.add_parser("catalogo", help="Read public metadata from the INDEC API catalogue.")
  vCatalog.add_argument("--pagina", type=fPositive, default=1)
  vCatalog.add_argument("--filtrar", default="")
  vCatalog.set_defaults(handler=fCatalog)

  vSchema = vCommands.add_parser("esquema", help="Read the published OpenAPI schema for a service.")
  vSchema.add_argument("servicio", type=fSlug)
  vSchema.set_defaults(handler=fSchema)

  vApi = vCommands.add_parser("api", help="Query INDEC data with INDEC_API_TOKEN or a hidden terminal prompt.")
  vApi.add_argument("servicio", type=fSlug)
  vApi.add_argument("--param", action="append", type=fParameter, default=[], metavar="NAME=VALUE")
  vApi.add_argument("--contar", action="store_true", help="Ask the service to return the total in Content-Range.")
  vApi.set_defaults(handler=fApiData)

  vSearch = vCommands.add_parser("series-buscar", help="Find series in the national time-series API.")
  vSearch.add_argument("texto")
  vSearch.add_argument("--limite", type=fPositive, default=10)
  vSearch.add_argument("--desplazamiento", type=int, default=0)
  vSearch.set_defaults(handler=fSearchSeries)

  vSeries = vCommands.add_parser("series", help="Read national API time series with full metadata.")
  vSeries.add_argument("ids", help="One or more comma-separated series IDs.")
  vSeries.add_argument("--desde")
  vSeries.add_argument("--hasta")
  vSeries.add_argument("--limite", type=fPositive)
  vSeries.set_defaults(handler=fSeries)

  vArgs = vParser.parse_args()
  try:
    dOutput = vArgs.handler(vArgs)
  except HTTPError as vError:
    vError.close()
    print(f"HTTP {vError.code} from {vError.url}", file=sys.stderr)
    return 1
  except (OSError, ValueError, HTTPException) as vError:
    print(str(vError), file=sys.stderr)
    return 1
  print(json.dumps(dOutput, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(fMain())
