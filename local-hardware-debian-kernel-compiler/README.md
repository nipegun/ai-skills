# Local Hardware Debian Kernel Compiler

This skill builds a minimal Debian kernel package for one specific computer. It finds the computer's hardware, checks which kernel features that hardware and the running system really use, removes the rest, and compiles `linux-image-*.deb` and matching `linux-headers-*.deb` packages with the upstream `make bindeb-pkg` target.

The kernel it targets is **the newest stable Linux release that can compile every required module in a stable version**. If a required external module, such as a vendor GPU driver or ZFS, cannot build against the newest stable kernel, the skill records the evidence and moves down to the next supported stable or LTS kernel. It keeps doing this until every required module compiles. It never uses a beta or development module to force a newer kernel, and it never drops a required device to make a build pass.

The skill works with Claude Code and OpenAI Codex.

## What you get

- `linux-image-<release>_<version>_<arch>.deb` and the matching `linux-headers-…deb`, with a unique local suffix such as `-localhw-<config-id>` so they never collide with the Debian kernel.
- The final `.config`, the migrated baseline config, the config diff and an audit of every declared requirement.
- A hardware inventory, a coverage ledger (`coverage.tsv`) that maps each device and boot requirement to its driver and Kconfig symbol, and a `requirements.json` file with the reason for each required option.
- Source download, signature and kernel selection records, the build log, a compatibility report and SHA-256 checksums and sizes of the packages.
- Exact installation and rollback instructions. The skill does not run them unless you ask it to.

Each result says clearly what was checked: source verification, compilation, offline package inspection and real boot on the target. A build that has not been booted is reported as "built and offline-inspected; target boot not verified".

## Kernel selection policy

This policy is mandatory. You cannot switch it off.

1. The skill reads [kernel.org/releases.json](https://www.kernel.org/releases.json) and sorts the supported final `stable`, `longterm` and `mainline` releases from newest to oldest. Release candidates and end-of-life series are excluded.
2. For each required external module it selects the newest official stable release from the vendor, and records the version and the official page that proves it is stable.
3. It builds the highest kernel candidate and compiles every required module against the generated headers.
4. If a module fails because of a real kernel incompatibility (`kernel-api` or `required-driver-unavailable`), the failure, its exit code and its log go into `compatibility-report.json`. The skill then selects the next lower candidate and starts again from a fresh directory.
5. Environment problems, such as missing tools, invalid configuration, out-of-memory errors, download or signature failures or missing permissions, are fixed on the same candidate. They never cause a lower kernel to be selected.

If no supported stable kernel works, the skill lists the incompatible modules and reports the result as incomplete.

## Requirements

- Debian (or a Debian-based build environment) on the target architecture. Cross-compilation needs the real target inventory and an explicit toolchain.
- Python 3.13 or newer for the helper scripts. They use only the standard library.
- Kernel build tools. The skill checks which ones are missing before it starts. The usual set is `build-essential`, `bc`, `bison`, `flex`, `libssl-dev`, `libelf-dev`, `libncurses-dev`, `dwarves`, `pkg-config`, `rsync`, `cpio`, `kmod`, `xz-utils`, `zstd`, `lz4`, `dpkg-dev`, `debhelper`, `fakeroot`, `gnupg`, `gpgv`, `dirmngr`, `ca-certificates` and `curl`.
- Inventory tools: `pciutils`, `usbutils`, `lshw`, `iproute2`, `util-linux`, `mokutil` and `alsa-utils`.
- Tens of GiB of free disk space and about 2 GiB of RAM for each parallel build job.
- Network access to `kernel.org` for the source and the release signing keys.

You do not need to install everything in advance. At the start of every build, the skill shows a **dependency notice**. It lists only the packages that are missing or too old on your machine, explains why each one is needed and gives one ready-to-copy command to run as root, without `sudo`, for example:

```bash
apt install --no-install-recommends pciutils usbutils
```

Conditional tools, such as `pahole` for BTF, Rust, Secure Boot signing tools or external-module tooling, are only requested once the configuration shows they are needed.

## Installing the skill

Copy or link this folder into your agent's skills directory:

```bash
# Claude Code
cp -r local-hardware-debian-kernel-compiler ~/.claude/skills/

# OpenAI Codex
cp -r local-hardware-debian-kernel-compiler ~/.codex/skills/
```

Codex reads the agent definition in `agents/openai.yaml`. Claude Code ignores that file.

## Usage

Ask the agent in plain language, for example:

- "Build a minimal kernel for this computer."
- "Make a custom Debian kernel .deb for this laptop. It uses the NVIDIA driver."
- "Compile the smallest kernel that still supports all my hardware and my LUKS root."

In Codex you can also call it directly:

```text
Use $local-hardware-debian-kernel-compiler to build minimal Debian kernel packages for this computer.
```

Tell the agent about devices that are not connected right now, such as a dock, a USB printer or an external sound card, and about any driver version you must keep. A single hardware snapshot cannot see what is unplugged.

## Workflow

1. **Dependency notice.** Read-only checks of the Debian release, architecture, environment and installed tools, followed by the notice described above.
2. **Inventory and coverage.** `scripts/inventory.py` collects devices, modaliases, loaded modules, storage, mounts, network interfaces, services, Secure Boot state and the running kernel's config. The agent then builds `coverage.tsv` against the new kernel source.
3. **Select modules and fetch the kernel.** The agent records the stable version of each required external module. `scripts/fetch_source.py` selects the kernel candidate, downloads it, verifies its GPG signature and extracts it.
4. **Reduce the configuration.** Migrate the working config with `olddefconfig`, run `localmodconfig` with a reviewed module list, then do a second pass by subsystem to remove unused drivers, file systems, protocols and debug features.
5. **Audit the configuration.** `scripts/audit_config.py` checks the effective config against `requirements.json` and lists every change from the baseline.
6. **Build and inspect.** `make bindeb-pkg`, compilation of every required external module, then offline inspection of the packages: contents, `depmod`, modalias coverage, firmware, initramfs and Secure Boot.
7. **Deliver.** Paths, versions, checksums, sizes, records and installation and rollback instructions.

If step 6 finds a real module incompatibility, the skill goes back to step 3 with the next lower kernel.

By default all files go into a fresh directory under `_/temp/kernel-build/` in your project. The skill never modifies `/usr/src/linux` or the installed module tree.

## Helper scripts

All three scripts need Python 3.13 or newer and refuse to overwrite an existing output. They support the workflow; they do not prove that a kernel will boot.

| Script | What it does | Main outputs |
| --- | --- | --- |
| `scripts/inventory.py` | Collects read-only evidence about the target. It never loads or unloads drivers. | `inventory.json`, `reports/*.txt`, `baseline.config`, `loaded-modules.txt`, `candidate-modules.lsmod` |
| `scripts/fetch_source.py` | Selects the newest eligible stable kernel, downloads it from kernel.org over HTTPS, verifies the signature with `gpgv` and extracts it safely. | `releases.json`, `selection.json`, the archive and signature, `signature-verification.log`, `source/`, `source-manifest.json` |
| `scripts/audit_config.py` | Compares the effective config with the baseline and with `requirements.json`. | A JSON report with failures, changes and `y`/`m` counts |

Examples:

```bash
python3 scripts/inventory.py --output-dir "$vRun/inventory" --extra-module nvidia

python3 scripts/fetch_source.py --work-dir "$vRun/attempt-01/download" \
  --keyring "$vRun/release-keys.gpg"

# Only show which kernel would be selected, without downloading it
python3 scripts/fetch_source.py --work-dir "$vRun/check" --resolve-only \
  --compatibility-report "$vRun/compatibility-report.json"

python3 scripts/audit_config.py --config "$vBuild/.config" \
  --baseline "$vRun/baseline-migrated.config" \
  --requirements "$vRun/requirements.json" \
  --output "$vRun/config-audit-final.json"
```

Exit codes: `0` means success. `1` means the script could not run. `audit_config.py` returns `2` when a declared requirement is not met.

## What the skill will not do

- Load or unload drivers, unbind devices, suspend the machine, change firmware or change boot settings while collecting information.
- Install the packages, update the initramfs or bootloader, or reboot, unless you ask for it separately.
- Use `sudo` automatically or run the build as root.
- Use beta, release candidate, development or end-of-life kernels or modules, or patch a module's code to force compatibility.
- Skip source signature verification or accept keys found by short ID on a keyserver.
- Disable CPU mitigations, required security modules, module signing or Secure Boot checks to make the build easier.
- Remove a device that is required but not yet identified. Unknown information is treated as unknown, not as absent.
- Remove the running Debian kernel. It stays installed as a fallback.

## Limits

- The result is the smallest configuration the evidence supports, not a mathematically minimal one. Kconfig dependencies and shared helper code are legitimate parts of the kernel.
- Firmware and CPU microcode are not part of the kernel package. The report lists the Debian packages and files they need.
- With Secure Boot enabled, the kernel image and modules must be signed with a key that the target's boot chain accepts. An unsigned package is a build artifact, not a ready-to-boot result.
- On ARM and Device Tree boards, a generic `.deb` is not enough. The board's DTB, image format and bootloader integration also have to be handled.
- Only a real boot on the target computer can confirm that displays, audio, suspend and the other devices work.

## Folder layout

```text
local-hardware-debian-kernel-compiler/
├── SKILL.md                      # Instructions the agent follows
├── README.md                     # This file
├── agents/
│   └── openai.yaml               # Agent definition for OpenAI Codex
├── references/
│   ├── discovery.md              # Target discovery and coverage ledger
│   ├── compatibility.md          # Stable-module compatibility loop and report format
│   ├── configuration.md          # Config migration, reduction and requirements.json
│   └── build-and-delivery.md     # Dependency notice, source, build, inspection and delivery
└── scripts/
    ├── inventory.py
    ├── fetch_source.py
    └── audit_config.py
```

## Official references

- [Linux kernel releases](https://www.kernel.org/releases.json) and [signature verification](https://www.kernel.org/signature.html)
- [Kconfig configuration targets](https://docs.kernel.org/kbuild/kconfig.html) and [Kconfig language](https://docs.kernel.org/kbuild/kconfig-language.html)
- [Kernel build requirements](https://docs.kernel.org/process/changes.html)
- [Building external modules](https://docs.kernel.org/kbuild/modules.html)
- [Kernel module signing](https://docs.kernel.org/admin-guide/module-signing.html)
- [Debian Linux Kernel Handbook: common tasks](https://kernel-team.pages.debian.net/kernel-handbook/ch-common-tasks.html)
