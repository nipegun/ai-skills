# Source, build and package delivery

## Source

Resolve [kernel.org/releases.json](https://www.kernel.org/releases.json) for each build. Follow the [mandatory stable-module compatibility loop](compatibility.md): start with the numerically highest non-EOL final release among `stable`, `longterm` and final `mainline` entries, then descend after documented incompatibility with a required stable module. Including final mainline accommodates a new final release before it acquires a `stable` label; prereleases are excluded. Save the feed, ordered candidates and rejection evidence with a UTC timestamp, and keep each candidate fixed throughout its build.

The helper refuses arbitrary version selection but accepts `--compatibility-report` to exclude kernels with documented stable-module incompatibilities. If metadata changes shape, source download fails, or verification fails, resolve that problem; those failures do not justify a kernel downgrade. Never skip verification or call a cached version the newest compatible candidate without checking the current feed and module catalog.

Read the current [kernel.org signature instructions](https://www.kernel.org/signature.html). Create a dedicated GnuPG home **inside the run directory** with permissions 0700. Retrieve the applicable maintainer public keys through kernel.org WKD or another authenticated official route, inspect full fingerprints against official maintainer information, then export only those authenticated keys to a local keyring. A key downloaded from an arbitrary keyserver by short ID is insufficient. Record the authentication method and full fingerprints; account for legitimate rotations rather than hardcoding old keys forever.

Example operations after defining `vGpgHome`, `vReleaseMaintainer`, `vVerifiedFingerprint` and `vRun` from that evidence:

```bash
gpg --homedir "$vGpgHome" --auto-key-locate clear,wkd --locate-keys "$vReleaseMaintainer"
gpg --homedir "$vGpgHome" --with-colons --fingerprint
gpg --homedir "$vGpgHome" --export "$vVerifiedFingerprint" > "$vRun/release-keys.gpg"
python3 "$vSkill/scripts/fetch_source.py" --work-dir "$vRun/download" --keyring "$vRun/release-keys.gpg"
```

The script downloads `.tar.xz` and `.tar.sign` through HTTPS, decompresses to `.tar`, runs `gpgv` against that uncompressed tar, then extracts with Python's `data` filter. It retains the compressed source, uncompressed source, signature, release feed, hashes and verification log. A partial run is evidence of failure, not a usable source; retry in a new directory. Do not execute build scripts from unverified sources. A final mainline feed entry pointing to a snapshot is replaced by the signed final-release archive path, never accepted unsigned.

## Dependencies and resources

### Initial dependency notice

**This notice is mandatory at the start of every build workflow**, after lightweight environment checks and before invoking `inventory.py`, downloading kernel sources or compiling. Present it in the user's language; do not leave the dependency list only in a saved file or silently install packages before explaining what is missing.

Use the available shell and Debian tools for these checks, not the Python helpers whose prerequisites are being checked:

1. Read `/etc/os-release`, `dpkg --print-architecture`, `id -u` and execution-environment evidence. If inventory and compilation run on different systems, check both and label which machine each package/command applies to. Do not recommend installing build tools on the target when only the build environment needs them.
2. Use `command -v` for executable availability and `dpkg-query -W` with an explicit format such as `'${binary:Package}\t${db:Status-Status}\t${Version}\n'` for package state/version. A package merely listed in dpkg, left with configuration files or partially installed does not satisfy the dependency. Record query failures as unknown and resolve them before presenting the list as complete. Use actual tool version output when minimum versions matter; an installed package name alone is insufficient.
3. Select requirements from [the package guidance below](#package-selection-and-resources) for the planned stage. Check basic inventory/source tools and known build requirements now. Keep conditional tools such as BTF/`pahole`, Rust, interactive configuration interfaces, Secure Boot signing and external-module tooling separate until evidence makes them necessary. Do not turn every missing optional inventory command into a mandatory package.
4. For packages needing installation or an update, inspect `apt-cache policy` and package/provider metadata in the configured repositories. Choose the real package names available for this Debian release. Report absent candidates or unknown/stale metadata rather than guessing names or adding repositories. If an index refresh is needed, include `apt update` before the installation command and recheck candidates after the authorized refresh. Do not promise that an unverified candidate meets a minimum version.
5. Check `python3 --version` if the command exists. The helpers need Python 3.13+. If Python is absent or too old, verify that the proposed package candidate or an already installed alternative interpreter satisfies that requirement. Record the interpreter path and use it consistently for all helper invocations. Do not present `apt install python3` as a fix when the available candidate is still too old; explain the concrete blocker and a suitable environment/interpreter option without replacing Debian's system interpreter or upgrading the distribution automatically.

The user-facing notice must contain:

- the checked Debian release, architecture and machine/environment;
- a concise list or table of **missing or outdated required packages**, with purpose and any relevant installed/minimum/candidate version;
- a ready-to-copy `apt install --no-install-recommends` command using **only actual package names needing action**, deduplicated, and the instruction to run it **as root, without `sudo`**; APT will resolve their dependencies;
- any conditional requirements still awaiting hardware/configuration evidence and any blockers that an install command cannot resolve.

For example, **only if the checks actually show these two packages are missing**, a Spanish notice can say:

> Faltan `pciutils`, para identificar los dispositivos PCI, y `usbutils`, para identificar los dispositivos USB. Ejecuta como root:

```bash
apt install --no-install-recommends pciutils usbutils
```

Generate the real notice from the current machine; do not reuse this example as a fixed recommendation. If all currently required packages and versions are ready, explicitly say that no additional packages are needed for this stage, omit installation commands, and continue. If suitable candidates are unavailable, list those blockers separately; a command for other missing packages must not be described as sufficient to proceed.

Showing the notice is informational and does not create an extra approval gate when installation is already authorized. Execute package-management commands only within the existing authorization; otherwise leave the copyable command for the user. After installation, repeat the affected availability/version checks before starting the dependent stage. Continue independent work where possible. Once the verified source and final config establish additional requirements, show a supplemental notice containing only the new changes before compilation, including required version updates.

### Package selection and resources

Inspect the selected source's `Documentation/process/changes.rst`, `make help` and packaging scripts. Typical Debian build dependencies are `build-essential`, `bc`, `bison`, `flex`, `libssl-dev`, `libelf-dev`, `libncurses-dev`, `dwarves`, `pkg-config`, `rsync`, `cpio`, `kmod`, `xz-utils`, `zstd`, `lz4`, `dpkg-dev`, `debhelper`, `fakeroot`, `python3`, `gnupg`, `gpgv`, `dirmngr`, `ca-certificates` and `curl`; actual requirements depend on the config and release. Inventory tools include `pciutils`, `usbutils`, `lshw`, `iproute2`, `util-linux`, `mokutil` and `alsa-utils`. Do not install DKMS or large optional stacks just to query their status.

Check tool versions before a long build, including compiler/binutils and `pahole` when BTF is enabled. Install only missing dependencies within the user's authorization, running package-management commands as root rather than assuming `sudo`. Do not launch a distribution upgrade to satisfy the toolchain; use a suitable isolated Debian build environment or report the blocker. The supplied helpers require Python 3.13+; on older Debian use an appropriate build environment for the helper or reproduce its documented read-only collection carefully on the target, without mislabeling a container inventory as the host's.

Base parallelism on available RAM, free disk, CPU count and user constraints. Bound `-j` explicitly, record the choice and reduce it on an OOM failure. Check for required Rust support only if the selected config/release needs it. Keep diagnostic logs for failures; do not delete large work directories before the user has the final artifacts.

## Build

Use a version suffix unique to this configuration, for example `-localhw-<config-id>`, via `CONFIG_LOCALVERSION`; disable `CONFIG_LOCALVERSION_AUTO` and keep command-line `LOCALVERSION` empty to avoid unintended suffixes. Derive a short ID (for example the first 12 hexadecimal SHA-256 characters) from the reviewed config before assigning the suffix, keep the complete kernel release within Kbuild's length limit, and save the final config hash separately. Give rebuilds an increasing Debian package revision. The kernel release must not collide with the distribution kernel or a different local configuration.

Resolve distribution-specific trust paths before compilation. In particular, a Debian baseline can refer to certificate files unavailable in pristine upstream source. Configure the correct local signing/trust keys. An automatically generated module-signing key does not sign the EFI image or make it trusted by firmware. Never clear trusted/revocation key inputs or disable module-signature enforcement without considering the target policy.

After configuration and its requirement audit, define the known `vVersion`, `vConfigId`, `vRevision` and `vJobs`, then build as an unprivileged user. With Bash `pipefail` enabled, an illustrative command is:

```bash
set -o pipefail
make -C "$vSource" O="$vBuild" -j"$vJobs" LOCALVERSION= \
  KDEB_PKGVERSION="${vVersion}-${vRevision}+localhw.${vConfigId}" bindeb-pkg \
  2>&1 | tee "$vRun/build.log"
```

Use the selected release's upstream package target, not obsolete `make-kpkg` or a hand-assembled image-only `.deb`. Verify its actual output paths; packages are normally emitted in the parent of the build output. Record `make -s -C "$vSource" O="$vBuild" LOCALVERSION= kernelrelease` and check it against package contents. Archive the final `.config`, `System.map`, `Module.symvers` and generated metadata. Re-run the requirement audit if the build changed the config, or compare its hash to the audited final config.

Keep the `linux-image-*` package and corresponding `linux-headers-*` package as deliverables. Upstream builds may also create `linux-libc-dev`, debug packages and build metadata. Do not recommend installing every `.deb` with a wildcard or replacing Debian's `linux-libc-dev` as part of a kernel install. Headers are useful for external modules even though the image package is the primary requested result.

## Offline package inspection

Inspect the exact package paths with `dpkg-deb --info` and `dpkg-deb --contents`. Extract with `dpkg-deb --extract` into fresh directories under the run workspace; this does not run package hooks or install anything. Inspect control scripts using `dpkg-deb --control`. Check:

1. Package version and architecture match the source, target and local suffix; boot image, config, System.map and module tree are present at the paths appropriate to the target architecture. Headers match the same release, and preserve the artifacts needed to build external modules.
2. The packaged config matches the audited config. All required modules exist or have an explicitly recorded built-in replacement. For built-ins inspect the new `modules.builtin`, `modules.builtin.modinfo` and effective config; lack of a `.ko` is not automatically failure.
3. Run `depmod -b "$vStage" "$vKernelRelease"` against the extracted new module tree, never against the live one. If the package uses a different module root, adapt staging/depmod options to that layout. Check for missing hard/soft dependencies and symbol problems against the new `System.map`/`Module.symvers` as applicable.
4. Resolve every inventoried modalias against staging, for example `modprobe --dirname "$vStage" --set-version "$vKernelRelease" --resolve-alias "$vAlias"`. Use `--show-depends` to inspect dependencies without loading anything. Compare to the coverage ledger, not just to old driver names. Verify built-in aliases through generated metadata and source when necessary. Explicitly cover requirements that have no modalias: filesystems, crypto, platform/DT, software features and early boot.
5. List firmware for required new modules using `modinfo` against their staged files, and inspect built-in/source firmware declarations. Match required files against the target `/lib/firmware`, compressed variants and owning Debian packages. Resolve alternative-name lists and optional firmware using device/revision-specific evidence rather than assuming every advertised name is mandatory. Include CPU microcode and GPU/audio topology data where needed. Do not redistribute proprietary firmware inside the kernel package without an appropriate license.
6. Required DKMS/external modules must compile at their selected stable versions against the new kernel and preserve the target's signing policy. Prefer an isolated copy/build tree or DKMS tree inside the workspace; avoid modifying the live DKMS database during package-only work. Check headers and `Module.symvers`, vermagic, firmware, module API compatibility and any GPL-only-symbol restrictions. If an eligible stable vendor driver cannot compile due to kernel incompatibility, record the failure and automatically try the next lower supported stable kernel using [the compatibility loop](compatibility.md). Do not substitute a beta module or drop that device. Only exhausted compatible candidates leave this workflow blocked by module compatibility.
7. Inspect package initramfs/bootloader hooks and the target's generator configuration. For module-based root dependencies, verify an initramfs contains the storage/filesystem/crypto modules, their firmware, decrypt/RAID/LVM userspace and appropriate compression support in the kernel. If possible generate an offline initramfs against staging with an isolated configuration and inspect it. Do not call `update-initramfs` or bootloader update commands on the live system during package-only work. If an offline initramfs cannot be checked, label boot-chain validation pending installation; do not report it verified.
8. Secure Boot enabled: ensure the delivered EFI kernel image is signed by a key accepted by the target boot chain and that modules/external modules have accepted signatures. Keep signing private keys out of packages/reports. Sign before final packaging or rebuild the package properly after image signing; retain control metadata and regenerate checksums. A signed `.deb` or `gpgv`-verified source is unrelated to firmware trust. Enrollment or changing firmware settings is a separate authorized action. An unsigned artifact with unresolved Secure Boot requirements is a build artifact, not a ready-to-boot result.

The package build alone cannot prove bootability, suspend/resume or full device behavior. Do not fabricate such checks. A VM boot can inspect generic boot behavior but cannot validate the physical target's devices.

## Delivery

Refresh the official release selection into a new directory with `fetch_source.py --resolve-only --compatibility-report <report-json>`. If a newer unrejected stable candidate appears, evaluate its compatibility with the same required stable module catalog. The output target is the newest stable candidate that passes every required module build, which may be older than the newest upstream release. Document the selection timestamp and every compatibility-driven descent; do not label a merely selected or partially built candidate compatible.

Provide image and matching headers paths, SHA-256 checksums, package and installed sizes, exact upstream/local/package versions and architecture. Include:

- source feed/selection/verification records and toolchain versions;
- inventory, target/environment identity and peripheral assumptions;
- `coverage.tsv`, required-module list, `requirements.json`, baseline and final configs;
- config diff/audit, reasoned removal summary and unresolved retained groups;
- build/inspection logs, firmware package dependencies, external-module status and boot trust status;
- explicit status of source verification, compilation, offline checks and actual target boot.

Write `compatibility-report.md` for the run, with concrete evidence and pending items. A compilation failure has no installable deliverable; a generated package with unresolved mandatory hardware/trust requirements must be marked incomplete. Do not claim every current device is supported while a required row remains unresolved.

For a ready artifact, give an installation command using **the exact image and headers filenames** with `apt install /absolute/image.deb /absolute/headers.deb` as root, plus separately identified firmware dependencies. Explain that package hooks normally generate the initramfs and update the bootloader; inspect their success, check required boot modules and external modules, and verify available `/boot`/EFI space before rebooting. Do not execute installation or reboot unless requested. Keep the known-working distribution kernel and its menu entry for rollback.

After an explicitly authorized boot, validate the reported release, root mounts, firmware logs and each required device/function, including networking, display/audio, input, USB, power management and any dock/peripheral requirements. Record failures and fix the configuration before calling the result hardware-verified. Until then use “built and offline-inspected; target boot not verified.”

## Primary references

- [Official releases](https://www.kernel.org/releases.json) and [signature verification](https://www.kernel.org/signature.html).
- [Debian Linux Kernel Handbook, custom packages](https://kernel-team.pages.debian.net/kernel-handbook/ch-common-tasks.html).
- [Kernel build requirements](https://docs.kernel.org/process/changes.html).
- [External module builds](https://docs.kernel.org/kbuild/modules.html).
- [Kernel module signing](https://docs.kernel.org/admin-guide/module-signing.html).
- [Debian package-state queries](https://manpages.debian.org/trixie/dpkg/dpkg-query.1.en.html), [APT candidate queries](https://manpages.debian.org/trixie/apt/apt-cache.8.en.html) and [APT installation behavior](https://manpages.debian.org/trixie/apt/apt-get.8.en.html).
