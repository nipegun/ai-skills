# Mandatory stable-module compatibility loop

## Selection rule

The desired result is the newest **supported stable kernel that compiles every required module in a stable version**. Kernel version priority is subordinate to complete hardware and system coverage. This rule is mandatory, not a user-selectable optimization mode.

Inventory first. Required in-tree modules inherit the stable kernel's source version; required external families such as NVIDIA or ZFS need their own stable/production release catalog. Verify the vendor's actual release channel through primary sources and record the version, official source, matching user-space/firmware requirements and stability evidence. A larger version number does not establish stability. A required update to a newer stable driver is a dependency to report, not permission to change the running driver.

Use the newest applicable vendor-supported stable module release by default. Honor an explicitly pinned stable driver version if the user requires it. An obsolete installed version failing to compile is not enough to reject a kernel when a newer eligible official stable release works. Never choose beta/development modules, discard a required device, or invent an API patch for a module merely to retain a newer kernel. A narrowly documented Kconfig change to expose a required dependency is different from patching the module's API implementation.

## Iteration

1. Read the current kernel.org feed. `fetch_source.py` hardcodes descending numeric selection among non-EOL final `stable`, `longterm` and final `mainline` entries. Prerelease suffixes are excluded. This considers the current release of each supported line, not archived patch levels or EOL series.
2. Download and authenticate the selected candidate in a fresh directory. Build its target configuration, kernel, headers and required in-tree modules. Compile every required stable external module against those exact headers/configuration and record return codes and logs. Preserve the same stable module catalog across kernel attempts; if a module version changes, reassess the earlier failures instead of reusing them.
3. If a build fails, distinguish a genuine kernel API/driver incompatibility from missing dependencies, wrong compiler options, a trimmed prerequisite, unavailable headers, permissions, signature/download problems or OOM. Fix environmental/configuration errors on the same candidate. Do not record them as kernel incompatibilities.
4. For a real incompatibility, add the failed kernel/module/version, nonzero return code, cause and nonempty log to `compatibility-report.json`. Invoke `fetch_source.py` again with `--compatibility-report` and a new output directory. Its selector excludes the documented incompatible candidate and chooses the highest remaining supported stable release. Repeat configuration/build/coverage for that kernel; do not reuse artifacts from another version.
5. Continue automatically until the kernel and **all** required stable modules compile successfully. A successful image build alone is insufficient. No extra confirmation is needed merely to try a lower stable kernel within this workflow. If the supported candidate list is exhausted, report the specific incompatible modules and leave the result incomplete; do not silently use a beta or EOL kernel.

The selector validates report structure, stable module declarations, matching versions, failure categories, nonzero return codes and actual nonempty local logs. It records the log SHA-256 values in the selection manifest. It does not interpret compiler diagnostics or authenticate the truth of a hand-written report; the agent must classify actual evidence correctly. A selection manifest explicitly leaves compatibility pending until the full builds and coverage checks complete.

## Compatibility report format

Use this JSON shape, replacing the illustrative names, versions and paths with verified facts. This example is a schema illustration, not evidence about a real driver:

```json
{
  "required_modules": {
    "vendor_gpu": {
      "version": "1.2.3",
      "channel": "stable",
      "stability_evidence": "https://vendor.example/production-releases"
    }
  },
  "attempts": [
    {
      "kernel": "7.3.3",
      "module_results": [
        {
          "module": "vendor_gpu",
          "version": "1.2.3",
          "result": "incompatible",
          "failure_kind": "kernel-api",
          "exit_code": 2,
          "reason": "A required kernel API is absent; confirmed in source and compiler output.",
          "log": "attempt-01/module-build.log"
        }
      ]
    }
  ]
}
```

Module `channel` must be `stable`, with official HTTPS stability evidence. Report results are `compatible`, `incompatible` or `environment-error`. Incompatible results must name a required module at its selected stable version, supply a nonzero integer exit code and a reason, and reference an existing nonempty log. Paths may be absolute or relative to the report. Accepted incompatibility categories are `kernel-api` and `required-driver-unavailable`; environmental errors never exclude a candidate. Successful results use `exit_code: 0` and preserve their build log for final review. A later complete successful attempt for all catalog entries clears an earlier rejection of that kernel.

An empty module catalog is permitted only when discovery establishes that no external module or explicit in-tree compatibility blocker needs separate tracking. Kernel/configuration/hardware coverage still must pass. Keep additional build evidence in the report as needed, including config hashes, kernel build status, component module filenames, firmware and user-space versions. The final successful attempt must cover every required family and all its components.

For another candidate, after saving actual incompatibility evidence:

```bash
python3 "$vSkill/scripts/fetch_source.py" --work-dir "$vRun/attempt-02/download" \
  --keyring "$vRun/release-keys.gpg" --compatibility-report "$vRun/compatibility-report.json"
```

Omit `--compatibility-report` only on the initial attempt, or supply an initialized report with no rejections. `--resolve-only` can inspect the next candidate without downloading. There is no arbitrary-version or skip-signature override.

## Delivery conditions

Record the selected kernel, required stable module versions, official stability evidence, every rejected candidate and its reason, and the final successful compilation logs. Include the target coverage map and explicitly identify required driver/user-space/firmware updates on the machine. A stable external driver that compiled successfully but is not installed is a validated prerequisite, not a change already applied to the host.

Recheck the feed before delivery. A newer candidate is not automatically compatible; evaluate it with the same stable-module rule or describe the delivered version as the newest verified compatible candidate as of the recorded check. Preserve the existing kernel until an explicitly requested installation and successful target boot. Compilation/inspection do not establish actual display, suspend or boot behavior.
