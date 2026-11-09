#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Audit effective Kconfig values against evidence-bearing requirements."""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path


def fReadConfig(pPath):
  dValues = {}
  for vLine in pPath.read_text(encoding="utf-8").splitlines():
    vMatch = re.fullmatch(r"(CONFIG_[A-Za-z0-9_]+)=(.*)", vLine)
    if vMatch:
      dValues[vMatch[1]] = vMatch[2]
      continue
    vMatch = re.fullmatch(r"# (CONFIG_[A-Za-z0-9_]+) is not set", vLine)
    if vMatch:
      dValues[vMatch[1]] = "n"
  if not dValues:
    raise ValueError(f"No Kconfig entries found in {pPath}")
  return dValues


def fAudit(pConfig, pRequirements):
  if not isinstance(pRequirements, dict) or not pRequirements:
    raise ValueError("Requirements must be a nonempty object keyed by CONFIG_ symbols.")
  lFailures = []
  for vSymbol, dRequirement in pRequirements.items():
    if not re.fullmatch(r"CONFIG_[A-Za-z0-9_]+", vSymbol) or not isinstance(dRequirement, dict):
      raise ValueError(f"Invalid requirement entry: {vSymbol}")
    vReason = dRequirement.get("reason")
    lAllowed = dRequirement.get("allowed")
    if (not isinstance(vReason, str) or not vReason.strip()
        or not isinstance(lAllowed, list) or not lAllowed
        or any(not isinstance(vValue, str) for vValue in lAllowed)):
      raise ValueError(f"{vSymbol} requires nonempty 'allowed' strings and an evidence 'reason'.")
    vActual = pConfig.get(vSymbol)
    # Missing is distinct from n: a removed or misspelled symbol requires review.
    if vActual not in lAllowed:
      lFailures.append({"symbol": vSymbol, "actual": vActual, "allowed": lAllowed, "reason": vReason})
  return lFailures


def fMain():
  if sys.version_info < (3, 13):
    raise RuntimeError("Python 3.13 or later is required.")
  vParser = argparse.ArgumentParser(description=__doc__)
  vParser.add_argument("--config", required=True, type=Path)
  vParser.add_argument("--baseline", required=True, type=Path)
  vParser.add_argument("--requirements", required=True, type=Path)
  vParser.add_argument("--output", required=True, type=Path, help="A new JSON report path")
  vArgs = vParser.parse_args()
  dConfig = fReadConfig(vArgs.config)
  dBaseline = fReadConfig(vArgs.baseline)
  dRequirements = json.loads(vArgs.requirements.read_text(encoding="utf-8"))
  lFailures = fAudit(dConfig, dRequirements)
  lChanges = [
    {"symbol": vSymbol, "before": dBaseline.get(vSymbol), "after": dConfig.get(vSymbol)}
    for vSymbol in sorted(dBaseline.keys() | dConfig.keys())
    if dBaseline.get(vSymbol) != dConfig.get(vSymbol)
  ]
  dReport = {
    "created_at_utc": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d@%H-%M-%S.%f")[:-3],
    "config_sha256": hashlib.sha256(vArgs.config.read_bytes()).hexdigest(),
    "baseline_sha256": hashlib.sha256(vArgs.baseline.read_bytes()).hexdigest(),
    "requirements_sha256": hashlib.sha256(vArgs.requirements.read_bytes()).hexdigest(),
    "requirement_count": len(dRequirements),
    "requirements_satisfied": not lFailures,
    "failures": lFailures,
    "changes": lChanges,
    "counts": {
      "baseline_y": sum(vValue == "y" for vValue in dBaseline.values()),
      "baseline_m": sum(vValue == "m" for vValue in dBaseline.values()),
      "effective_y": sum(vValue == "y" for vValue in dConfig.values()),
      "effective_m": sum(vValue == "m" for vValue in dConfig.values()),
    },
    "scope": "Declared effective values only; not hardware completeness, binary size or boot verification.",
  }
  vArgs.output.parent.mkdir(parents=True, exist_ok=True)
  with vArgs.output.open("x", encoding="utf-8") as vFile:
    json.dump(dReport, vFile, indent=2, ensure_ascii=False)
    vFile.write("\n")
  print(json.dumps({"requirements_satisfied": not lFailures, "failures": lFailures}, indent=2))
  return 2 if lFailures else 0


if __name__ == "__main__":
  try:
    sys.exit(fMain())
  except (OSError, ValueError, RuntimeError) as vError:
    print(f"Configuration audit failed: {vError}", file=sys.stderr)
    sys.exit(1)
