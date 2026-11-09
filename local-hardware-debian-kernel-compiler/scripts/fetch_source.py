#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Select signed stable kernel sources, descending after documented module incompatibility."""

import argparse
import datetime
import hashlib
import json
import lzma
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


cReleaseFeed = "https://www.kernel.org/releases.json"
sAllowedHosts = {"www.kernel.org", "kernel.org", "cdn.kernel.org", "mirrors.edge.kernel.org"}


def fCheckUrl(pUrl):
  vParsed = urllib.parse.urlsplit(pUrl)
  if (vParsed.scheme != "https" or vParsed.hostname not in sAllowedHosts
      or vParsed.username or vParsed.password or vParsed.port not in (None, 443)
      or vParsed.query or vParsed.fragment):
    raise ValueError(f"Not an allowed kernel.org HTTPS URL: {pUrl}")
  return pUrl


class KernelRedirectHandler(urllib.request.HTTPRedirectHandler):
  """Restrict redirects before making the redirected request."""

  def redirect_request(pSelf, pRequest, pResponse, pCode, pMessage, pHeaders, pNewUrl):
    fCheckUrl(pNewUrl)
    return super().redirect_request(pRequest, pResponse, pCode, pMessage, pHeaders, pNewUrl)


def fOpen(pUrl):
  vRequest = urllib.request.Request(fCheckUrl(pUrl), headers={
    "User-Agent": "local-hardware-debian-kernel-compiler/1"
  })
  return urllib.request.build_opener(KernelRedirectHandler()).open(vRequest, timeout=90)


def fWriteJson(pPath, pData):
  with pPath.open("x", encoding="utf-8") as vFile:
    json.dump(pData, vFile, indent=2, ensure_ascii=False)
    vFile.write("\n")


def fReadIncompatibilities(pPath):
  if pPath is None:
    return {}
  dReport = json.loads(pPath.read_text(encoding="utf-8"))
  if not isinstance(dReport, dict):
    raise ValueError("The compatibility report must be a JSON object.")
  dModules = dReport.get("required_modules")
  lAttempts = dReport.get("attempts")
  if not isinstance(dModules, dict) or not isinstance(lAttempts, list):
    raise ValueError("The report requires required_modules and attempts.")
  for vName, dModule in dModules.items():
    if (not isinstance(dModule, dict) or dModule.get("channel") != "stable"
        or not isinstance(dModule.get("version"), str) or not dModule["version"]
        or not isinstance(dModule.get("stability_evidence"), str)
        or not dModule["stability_evidence"].startswith("https://")):
      raise ValueError(f"{vName}: a stable module version and HTTPS stability evidence are required.")
  dRejected = {}
  for dAttempt in lAttempts:
    if not isinstance(dAttempt, dict):
      raise ValueError("Each attempt must be a JSON object.")
    vVersion = dAttempt.get("kernel", "")
    if not isinstance(vVersion, str) or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", vVersion):
      raise ValueError("Attempts must refer to final stable kernel versions.")
    lResults = dAttempt.get("module_results")
    if not isinstance(lResults, list):
      raise ValueError(f"{vVersion}: module_results must be a list.")
    lFailures = []
    for dResult in lResults:
      if not isinstance(dResult, dict) or dResult.get("module") not in dModules:
        raise ValueError(f"{vVersion}: every result must identify a required module.")
      vModule = dResult["module"]
      if dResult.get("version") != dModules[vModule]["version"]:
        raise ValueError(f"{vVersion}: stale result for {vModule}; reassess the chosen stable module version.")
      vOutcome = dResult.get("result")
      if vOutcome not in ("compatible", "incompatible", "environment-error"):
        raise ValueError(f"{vVersion}: invalid module result.")
      vExitCode = dResult.get("exit_code")
      vLogName = dResult.get("log")
      if (type(vExitCode) is not int or not isinstance(vLogName, str) or not vLogName
          or (vOutcome == "compatible") != (vExitCode == 0)):
        raise ValueError(f"{vVersion}: result requires a consistent exit code and a build log.")
      vLog = Path(vLogName)
      if not vLog.is_absolute():
        vLog = pPath.resolve().parent / vLog
      if not vLog.is_file() or vLog.stat().st_size == 0:
        raise ValueError(f"{vVersion}: build log is missing or empty: {vLog}")
      if vOutcome != "incompatible":
        continue
      if dResult.get("failure_kind") not in ("kernel-api", "required-driver-unavailable"):
        raise ValueError("Only kernel API/driver incompatibility permits descending kernel versions.")
      vReason = dResult.get("reason")
      if not isinstance(vReason, str) or not vReason.strip():
        raise ValueError(f"{vVersion}: incompatibility requires an evidence-based reason.")
      lFailures.append({"module": vModule, "version": dResult["version"],
        "reason": vReason, "failure_kind": dResult["failure_kind"],
        "log": str(vLog.resolve()), "log_sha256": hashlib.sha256(vLog.read_bytes()).hexdigest()})
    if lFailures:
      dRejected[vVersion] = lFailures
    elif (dModules and {dResult["module"] for dResult in lResults} == set(dModules)
        and all(dResult["result"] == "compatible" for dResult in lResults)):
      dRejected.pop(vVersion, None)
  return dRejected


def fSelectRelease(pFeed, pRejected):
  lCandidates = []
  for dRelease in pFeed.get("releases", []):
    vVersion = dRelease.get("version", "")
    if (dRelease.get("moniker") in ("stable", "longterm", "mainline")
        and dRelease.get("iseol") is False
        and re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", vVersion)):
      aParts = tuple(int(vPart) for vPart in vVersion.split("."))
      lCandidates.append((aParts + (0,) * (3 - len(aParts)), dRelease))
  if not lCandidates:
    raise ValueError("The official feed contains no eligible final stable release.")
  lCandidates.sort(key=lambda pItem: pItem[0], reverse=True)
  lEligible = [dRelease for vParts, dRelease in lCandidates if dRelease["version"] not in pRejected]
  if not lEligible:
    raise ValueError("All supported stable candidates have documented module incompatibilities; no compatible candidate remains.")
  dSelected = lEligible[0].copy()
  vVersion = dSelected["version"]
  vMajor = vVersion.split(".")[0]
  vBase = f"https://cdn.kernel.org/pub/linux/kernel/v{vMajor}.x/linux-{vVersion}"
  # A final mainline entry can point to an unsigned snapshot. Require the signed release archive.
  if not dSelected.get("pgp") or not str(dSelected.get("source", "")).endswith(".tar.xz"):
    dSelected["source"] = f"{vBase}.tar.xz"
    dSelected["pgp"] = f"{vBase}.tar.sign"
  for vField, vSuffix in (("source", ".tar.xz"), ("pgp", ".tar.sign")):
    vUrl = fCheckUrl(dSelected[vField])
    if PurePosixPath(urllib.parse.urlsplit(vUrl).path).name != f"linux-{vVersion}{vSuffix}":
      raise ValueError(f"Unexpected {vField} filename in release metadata.")
  return dSelected, [dRelease["version"] for vParts, dRelease in lCandidates]


def fDownload(pUrl, pDestination):
  vPartial = pDestination.with_name(pDestination.name + ".part")
  if pDestination.exists() or vPartial.exists():
    raise FileExistsError(f"Refusing to replace {pDestination} or its partial download.")
  vHash = hashlib.sha256()
  with fOpen(pUrl) as vResponse, vPartial.open("xb") as vFile:
    while vChunk := vResponse.read(1024 * 1024):
      vFile.write(vChunk)
      vHash.update(vChunk)
  vPartial.rename(pDestination)
  return vHash.hexdigest()


def fMain():
  if sys.version_info < (3, 13):
    raise RuntimeError("Python 3.13 or later is required.")
  vParser = argparse.ArgumentParser(description=__doc__)
  vParser.add_argument("--work-dir", required=True, type=Path, help="A new directory for this run")
  vParser.add_argument("--keyring", type=Path, help="GPG keyring containing authenticated release keys")
  vParser.add_argument("--resolve-only", action="store_true", help="Save release selection only")
  vParser.add_argument("--compatibility-report", type=Path,
    help="Stable required modules and documented kernel incompatibilities; selects the next lower stable candidate")
  vArgs = vParser.parse_args()
  dRejected = fReadIncompatibilities(vArgs.compatibility_report)
  vKeyring = None
  if not vArgs.resolve_only:
    if not vArgs.keyring or not vArgs.keyring.is_file():
      raise ValueError("A verified release --keyring file is required for source download.")
    if not shutil.which("gpgv"):
      raise RuntimeError("gpgv is required to authenticate the source.")
    vKeyring = vArgs.keyring.resolve()
  vWork = vArgs.work_dir.resolve()
  vWork.mkdir(parents=True, exist_ok=False)
  with fOpen(cReleaseFeed) as vResponse:
    vRaw = vResponse.read(2 * 1024 * 1024 + 1)
  if len(vRaw) > 2 * 1024 * 1024:
    raise ValueError("Release feed is unexpectedly large.")
  (vWork / "releases.json").write_bytes(vRaw)
  dRelease, lCandidates = fSelectRelease(json.loads(vRaw), dRejected)
  dManifest = {
    "resolved_at_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d@%H-%M-%S.%f")[:-3],
    "feed": cReleaseFeed,
    "release": dRelease,
    "selection_policy": "newest-supported-stable-not-rejected-by-required-stable-modules",
    "stable_candidates_descending": lCandidates,
    "rejected_kernels": dRejected,
    "compatibility_status": "pending-complete-build-and-module-coverage",
    "state": "selected",
  }
  fWriteJson(vWork / "selection.json", dManifest)
  if vArgs.resolve_only:
    print(json.dumps(dManifest, indent=2))
    return 0
  vVersion = dRelease["version"]
  vArchive = vWork / f"linux-{vVersion}.tar.xz"
  vSignature = vWork / f"linux-{vVersion}.tar.sign"
  print(f"Downloading Linux {vVersion} (highest eligible stable compatibility candidate).", flush=True)
  dManifest["archive_sha256"] = fDownload(dRelease["source"], vArchive)
  dManifest["signature_sha256"] = fDownload(dRelease["pgp"], vSignature)
  vTar = vWork / f"linux-{vVersion}.tar"
  with lzma.open(vArchive, "rb") as vInput, vTar.open("xb") as vOutput:
    shutil.copyfileobj(vInput, vOutput, length=1024 * 1024)
  vGpgHome = vWork / "gnupg-verify"
  vGpgHome.mkdir(mode=0o700)
  with (vWork / "signature-verification.log").open("x", encoding="utf-8") as vLog:
    subprocess.run([
      "gpgv", "--homedir", str(vGpgHome), "--keyring", str(vKeyring),
      "--status-fd", "1", str(vSignature), str(vTar)
    ], stdout=vLog, stderr=subprocess.STDOUT, check=True)
  dManifest["keyring_sha256"] = hashlib.sha256(vKeyring.read_bytes()).hexdigest()
  vSources = vWork / "source"
  vSources.mkdir()
  with tarfile.open(vTar, "r:") as vBundle:
    for vMember in vBundle.getmembers():
      aParts = PurePosixPath(vMember.name).parts
      if not aParts or aParts[0] != f"linux-{vVersion}" or ".." in aParts:
        raise ValueError(f"Unexpected archive path: {vMember.name}")
    vBundle.extractall(vSources, filter="data")
  dManifest["state"] = "verified-and-extracted"
  dManifest["source_directory"] = str(vSources / f"linux-{vVersion}")
  fWriteJson(vWork / "source-manifest.json", dManifest)
  print(json.dumps(dManifest, indent=2))
  return 0


if __name__ == "__main__":
  try:
    sys.exit(fMain())
  except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError, lzma.LZMAError) as vError:
    print(f"Source acquisition failed: {vError}", file=sys.stderr)
    sys.exit(1)
