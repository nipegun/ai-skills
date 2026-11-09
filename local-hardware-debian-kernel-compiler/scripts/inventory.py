#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Collect read-only target evidence without loading drivers or changing the host."""

import argparse
import datetime
import gzip
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def fRun(pArguments, pTimeout=30, pAllowedCodes=(0,)):
  if not shutil.which(pArguments[0]):
    return {"argv": pArguments, "status": "missing-command", "stdout": "", "stderr": ""}
  try:
    dEnvironment = os.environ.copy()
    dEnvironment["LC_ALL"] = "C"
    vResult = subprocess.run(pArguments, capture_output=True, text=True, errors="replace",
      timeout=pTimeout, env=dEnvironment, check=False)
    return {
      "argv": pArguments, "status": "ok" if vResult.returncode in pAllowedCodes else "failed",
      "returncode": vResult.returncode, "stdout": vResult.stdout, "stderr": vResult.stderr,
    }
  except (OSError, subprocess.TimeoutExpired) as vError:
    return {"argv": pArguments, "status": "failed", "stdout": "", "stderr": str(vError)}


def fRead(pPath, pWarnings):
  try:
    return pPath.read_text(encoding="utf-8", errors="replace")
  except OSError as vError:
    pWarnings.append({"path": str(pPath), "error": str(vError)})
    return ""


def fModuleName(pName):
  return pName.replace("-", "_")


def fCollectDevices(pRelease, pModules, pWarnings):
  lDevices = []
  dAliases = {}
  for vDirectory, lDirectories, lFiles in os.walk("/sys/devices", followlinks=False,
      onerror=lambda pError: pWarnings.append({"path": pError.filename, "error": str(pError)})):
    vPath = Path(vDirectory)
    vDriverLink = vPath / "driver"
    if "modalias" not in lFiles and not vDriverLink.is_symlink():
      continue
    dDevice = {"sysfs_path": str(vPath), "modalias": "", "driver": None, "module": None}
    if "modalias" in lFiles:
      dDevice["modalias"] = fRead(vPath / "modalias", pWarnings).strip()
    try:
      if vDriverLink.is_symlink():
        dDevice["driver"] = vDriverLink.resolve(strict=True).name
      if (vDriverLink / "module").is_symlink():
        dDevice["module"] = fModuleName((vDriverLink / "module").resolve(strict=True).name)
        pModules.setdefault(dDevice["module"], set()).add(f"bound:{vPath}")
    except OSError as vError:
      pWarnings.append({"path": str(vDriverLink), "error": str(vError)})
    vAlias = dDevice["modalias"]
    if vAlias:
      if vAlias not in dAliases:
        dAliases[vAlias] = fRun(["modprobe", "--set-version", pRelease, "--resolve-alias", "--", vAlias])
      dResolution = dAliases[vAlias]
      lCandidates = [fModuleName(vLine.strip()) for vLine in dResolution["stdout"].splitlines()
        if re.fullmatch(r"[A-Za-z0-9_-]+", vLine.strip())]
      dDevice["candidate_modules"] = lCandidates
      dDevice["alias_status"] = dResolution["status"]
      if not lCandidates:
        dDevice["needs_review"] = "No current-kernel alias match; inspect built-ins and new source."
      for vModule in lCandidates:
        pModules.setdefault(vModule, set()).add(f"alias:{vAlias}")
    lDevices.append(dDevice)
  return lDevices, dAliases


def fCollectModuleDetails(pRelease, pModules):
  dDetails = {}
  lPending = sorted(pModules)
  while lPending:
    vModule = lPending.pop()
    if vModule in dDetails:
      continue
    dInfo = fRun(["modinfo", "--set-version", pRelease, vModule])
    dDependencies = fRun(["modprobe", "--set-version", pRelease, "--show-depends",
      "--ignore-install", "--", vModule])
    dDetails[vModule] = {"modinfo": dInfo, "dependencies": dDependencies}
    for vLine in dDependencies["stdout"].splitlines():
      if not vLine.startswith("insmod "):
        continue
      aParts = vLine.split()
      if len(aParts) < 2:
        continue
      vName = re.sub(r"\.ko(?:\.(?:xz|gz|zst))?$", "", Path(aParts[1]).name)
      if not re.fullmatch(r"[A-Za-z0-9_-]+", vName):
        continue
      vName = fModuleName(vName)
      pModules.setdefault(vName, set()).add(f"dependency:{vModule}")
      if vName not in dDetails:
        lPending.append(vName)
  return dDetails


def fMain():
  if sys.version_info < (3, 13):
    raise RuntimeError("Python 3.13 or later is required.")
  if platform.system() != "Linux":
    raise RuntimeError("Collect inventory on the actual Linux target.")
  vParser = argparse.ArgumentParser(description=__doc__)
  vParser.add_argument("--output-dir", required=True, type=Path, help="A new local directory")
  vParser.add_argument("--extra-module", action="append", default=[], help="Known required module; repeatable")
  vArgs = vParser.parse_args()
  for vModule in vArgs.extra_module:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", vModule):
      raise ValueError(f"Invalid module name: {vModule}")
  vOutput = vArgs.output_dir.resolve()
  vOutput.mkdir(parents=True, exist_ok=False)
  vReports = vOutput / "reports"
  vReports.mkdir()
  lWarnings = []
  vRelease = platform.release()
  dCommands = {
    "uname": ["uname", "-a"],
    "architecture": ["dpkg", "--print-architecture"],
    "cpu": ["lscpu", "--json"],
    "pci": ["lspci", "-Dnnk"],
    "usb": ["lsusb"],
    "usb-tree": ["lsusb", "-t"],
    "block": ["lsblk", "--json", "--paths", "--output", "NAME,KNAME,TYPE,FSTYPE,MOUNTPOINTS,PKNAME,UUID,PARTUUID"],
    "mounts": ["findmnt", "--json", "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"],
    "swap": ["swapon", "--show", "--output", "NAME,TYPE,SIZE,USED,PRIO"],
    "interfaces": ["ip", "-details", "-json", "link", "show"],
    "dkms": ["dkms", "status"],
    "secure-boot": ["mokutil", "--sb-state"],
    "services-running": ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--no-legend"],
    "services-enabled": ["systemctl", "list-unit-files", "--state=enabled", "--no-pager", "--no-legend"],
    "packages": ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n"],
    "hardware": ["lshw", "-json"],
    "rfkill": ["rfkill", "--json"],
    "audio": ["aplay", "-l"],
    "space": ["df", "-B1", str(vOutput)],
  }
  dReports = {}
  for vName, lCommand in dCommands.items():
    dResult = fRun(lCommand, pTimeout=90 if vName == "hardware" else 30)
    (vReports / f"{vName}.txt").write_text(dResult["stdout"], encoding="utf-8")
    dReports[vName] = {vKey: vValue for vKey, vValue in dResult.items() if vKey != "stdout"}
    dReports[vName]["output_file"] = f"reports/{vName}.txt"
  dReports["virtualization"] = fRun(["systemd-detect-virt"], pAllowedCodes=(0, 1))
  dReports["container"] = fRun(["systemd-detect-virt", "--container"], pAllowedCodes=(0, 1))
  dModules = {}
  vLoaded = fRead(Path("/proc/modules"), lWarnings)
  for vLine in vLoaded.splitlines():
    if vLine.split():
      dModules.setdefault(fModuleName(vLine.split()[0]), set()).add("loaded")
  for vModule in vArgs.extra_module:
    dModules.setdefault(fModuleName(vModule), set()).add("explicit-requirement")
  lDevices, dAliases = fCollectDevices(vRelease, dModules, lWarnings)
  dModuleDetails = fCollectModuleDetails(vRelease, dModules)
  lFiles = [
    "/etc/os-release", "/etc/fstab", "/proc/cmdline", "/proc/filesystems", "/proc/swaps",
    "/proc/mdstat", "/proc/meminfo", "/proc/1/cgroup", "/proc/asound/cards",
    f"/lib/modules/{vRelease}/modules.builtin", f"/lib/modules/{vRelease}/modules.softdep",
  ]
  dSnapshots = {}
  for vName in lFiles:
    vPath = Path(vName)
    if vPath.exists():
      dSnapshots[vName] = fRead(vPath, lWarnings)
  vConfigSource = None
  for vPath in (Path(f"/boot/config-{vRelease}"), Path("/proc/config.gz")):
    if not vPath.exists():
      continue
    try:
      vConfig = gzip.decompress(vPath.read_bytes()) if vPath.suffix == ".gz" else vPath.read_bytes()
      if b"CONFIG_" not in vConfig:
        raise ValueError("No Kconfig entries in candidate baseline.")
      (vOutput / "baseline.config").write_bytes(vConfig)
      vConfigSource = str(vPath)
      break
    except (OSError, ValueError, EOFError) as vError:
      lWarnings.append({"path": str(vPath), "error": str(vError)})
  if not vConfigSource:
    lWarnings.append({"error": "No readable running-kernel baseline config; obtain it before configuration."})
  if not lDevices:
    lWarnings.append({"error": "No sysfs devices collected; target visibility is incomplete."})
  lReview = [dDevice["sysfs_path"] for dDevice in lDevices if dDevice.get("needs_review")]
  dInventory = {
    "created_at_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d@%H-%M-%S.%f")[:-3],
    "kernel_release": vRelease, "machine": platform.machine(), "effective_uid": os.geteuid(),
    "status": "partial" if (lWarnings or lReview
      or any(dResult["status"] != "ok" for dResult in dReports.values())
      or any(dData["modinfo"]["status"] != "ok" or dData["dependencies"]["status"] != "ok"
        for dData in dModuleDetails.values())) else "collected-needs-review",
    "baseline_source": vConfigSource, "efi_present": Path("/sys/firmware/efi").exists(),
    "commands": dReports, "files": dSnapshots, "devices": lDevices,
    "alias_resolution": dAliases, "module_details": dModuleDetails,
    "candidate_module_evidence": {vName: sorted(sReasons) for vName, sReasons in sorted(dModules.items())},
    "devices_requiring_review": lReview, "warnings": lWarnings,
    "limits": ["One snapshot cannot establish disconnected or disabled hardware.",
      "Current-kernel aliases do not prove new-kernel support.",
      "Built-in drivers, boot requirements and software still need explicit review."],
  }
  with (vOutput / "inventory.json").open("x", encoding="utf-8") as vFile:
    json.dump(dInventory, vFile, indent=2, ensure_ascii=False)
    vFile.write("\n")
  (vOutput / "loaded-modules.txt").write_text(vLoaded, encoding="utf-8")
  (vOutput / "candidate-modules.lsmod").write_text("Module Size Used by\n" +
    "".join(f"{vName} 0 0\n" for vName in sorted(dModules)), encoding="utf-8")
  print(json.dumps({"output_directory": str(vOutput), "status": dInventory["status"],
    "devices": len(lDevices), "candidate_modules": len(dModules), "warnings": lWarnings}, indent=2))
  return 0


if __name__ == "__main__":
  try:
    sys.exit(fMain())
  except (OSError, ValueError, RuntimeError) as vError:
    print(f"Inventory failed: {vError}", file=sys.stderr)
    sys.exit(1)
