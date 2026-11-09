# Configuration reduction

## Baseline and migration

Use the target's known-working `/boot/config-$(uname -r)` or `/proc/config.gz`; the inventory helper copies it when readable. If unavailable, obtain the config from that exact Debian kernel package or extract IKCONFIG from its image. Do not silently replace an unknown baseline with `defconfig` and claim equivalent support.

Check the new release's `Documentation/process/changes.rst` against the installed toolchain. Build natively for the target architecture by default. `uname -m`, Debian's architecture and Kbuild `ARCH` use different names (for example x86_64/amd64/x86); do not pass one as another. Cross-compilation requires the actual target inventory, config and explicit toolchain setup.

Use a pristine verified source directory and a separate, fresh output directory. Define absolute `vSource`, `vBuild`, `vInventory`, `vRun` and `vSkill` paths for the current run, and keep `O="$vBuild"` consistent on every make call. Copy the baseline, run `listnewconfig` before migration, preserve its output, then `olddefconfig`. Save the resulting config as `baseline-migrated.config`. Review new, renamed and removed symbols; defaults alone do not establish compatibility.

Example commands once those paths exist:

```bash
cp "$vInventory/baseline.config" "$vBuild/.config"
make -C "$vSource" O="$vBuild" listnewconfig > "$vRun/new-symbols.txt"
make -C "$vSource" O="$vBuild" olddefconfig
cp "$vBuild/.config" "$vRun/baseline-migrated.config"
```

## Module pruning

`candidate-modules.lsmod` contains the union of loaded modules, modules bound to devices, alias matches, dependency closure and explicit `--extra-module` entries. These are candidates, not a whitelist ready for blind use. Reconcile the file with previous snapshots, boot modules, software needs, blacklists and new-source driver mappings. Write the reviewed result as `required-modules.lsmod` with the `Module Size Used by` header and one `module_name 0 0` row per retained module.

Run:

```bash
make -C "$vSource" O="$vBuild" LSMOD="$vRun/required-modules.lsmod" localmodconfig
make -C "$vSource" O="$vBuild" olddefconfig
cp "$vBuild/.config" "$vRun/after-localmodconfig.config"
```

Read warnings about unmapped modules. Do not feed `yes` to configuration to hide unresolved choices. If the target requires input, capture and resolve each choice using the coverage ledger, then rerun the operation. Do not use `LMC_KEEP=drivers:fs` or preserve entire USB/network/storage trees as the finished result. A narrow temporary `LMC_KEEP` can help investigate a mapping issue, but must be reviewed and reduced before completion.

`localmodconfig` chiefly trims modules; it does not fully remove unwanted built-ins or identify firmware/user-space dependencies. It cannot enable a previously disabled driver merely because its name appears in the keep list. A module name is not reliably a Kconfig symbol. Inspect the new Makefile/Kbuild and Kconfig definitions, including parent gates, composite objects and `select`/`imply` relationships.

## Aggressive second pass

Review the entire remaining `y`/`m` feature set by subsystem. Assign retained options to hardware evidence, boot requirements, active software, security, or a named dependency. Remove unrelated vendor platforms, drivers for absent devices, unused filesystems, obsolete protocols, unused emulation/virtualization, instrumentation and development facilities when their absence is established. A loaded generic distro module without a required use can also be removed after review.

Do not adopt a blanket allnoconfig/tinyconfig baseline: required `depends on` parents are not enabled automatically just because a leaf was requested. Do not replace every `m` with `y`; doing so can increase the image and alter probing order, firmware timing and unloading behavior. Keep built-ins required before the initramfs is accessible, and use modules for other supported drivers when practical. All module-based boot dependencies must be present in the generated initramfs.

Use the release's `scripts/config --file "$vBuild/.config"` for explicit edits, followed by `olddefconfig`. Examples of optional removal targets, **only after checking actual requirements**, include debug info, KUnit, GCOV, KCOV, fault injection, unused tracing, test drivers and unused filesystems. Do not treat every `DEBUG_*` symbol as removable or disable `EXPERT`-hidden core functions indiscriminately.

Special cases:

- Debug info/BTF: `CONFIG_DEBUG_INFO_NONE=y` can avoid large debug artifacts, but BPF CO-RE, observability tools or external modules may require BTF or related metadata. Inspect those uses before choosing it. Compare the effective config, not just commands issued to `scripts/config`.
- CPU: retain the target vendor and required instruction baseline, SMP/topology, microcode path, power/thermal management and mitigations. Do not inject `-march=native`, force LTO or choose an unsupported CPU subtype as a generic optimization. NUMA, IOMMU, PCIe services and RAS can be needed on the actual platform.
- Firmware boot: retain EFI/ACPI or Device Tree and the target bootloader's image requirements, framebuffer/console/input for recovery, RTC and entropy support. Preserve Secure Boot/lockdown policy where in use.
- Debian user space: preserve executable loaders, ELF/script support, futexes, epoll/eventfd/signalfd/timerfd, UNIX sockets, `/proc`, sysfs, tmpfs, devtmpfs, devpts and required cgroups/namespaces/security facilities. Derive exact symbols from the release and the installed init system. Retain 32-bit compatibility if applications use it, including existing Wine/Steam or multilib needs.
- Networking: real networking needs protocols as well as NIC drivers. Account for IPv4/IPv6, nftables/netfilter, NetworkManager, Wi-Fi authentication crypto, VPN/TUN, bridge, VLAN, routing and virtual interfaces actually used. Do not infer their absence from a quiet snapshot.
- Storage: preserve filesystem features used on disk, ACL/xattr/security labels, partition parsers and mount options. Trace LUKS/dm-crypt/LVM/RAID/multipath and crypto dependencies to the physical controller. FUSE, overlay, loop, squashfs, NFS and removable-media filesystems depend on real workflows, not just current mounts.
- Power: sleeping sensors, Bluetooth, radios, USB functions and GPU power states are still current hardware. Retain suspend/resume/hibernation only as applicable, including swap/resume support and firmware-loader timing.
- Security: preserve CPU mitigations, relevant LSMs (for example AppArmor), cryptography, keyrings and module-signing controls. Missing Debian certificate paths should be replaced by the correct local trust arrangement; never disable required trust checks merely to make compilation succeed.

For each coherent reduction, preserve the preceding config, run `olddefconfig`, audit required values and inspect the diff. Restore the smallest needed dependency closure if a required value falls back to `n`. Do not re-enable broad subsystems without evidence. Newly selected hidden helpers are legitimate requirements; record their parent driver/feature rather than trying to force them off.

## Requirements file

Write `requirements.json` from the target's coverage ledger. It is a JSON object keyed by the actual new-release symbols. Each value has `allowed` (a nonempty list of exact textual config values) and `reason` (specific evidence). Example **fragment**, not a complete boot profile:

```json
{
  "CONFIG_BLK_DEV_INITRD": {
    "allowed": ["y"],
    "reason": "Target boots through an initramfs with the root-storage modules."
  },
  "CONFIG_EXT4_FS": {
    "allowed": ["y", "m"],
    "reason": "Root filesystem is ext4; when modular it must be in the initramfs."
  }
}
```

Use only values valid for this target; the sample is inappropriate for a root filesystem other than ext4. Require `y` when early availability cannot rely on initramfs. For string values, include the config's literal quotes, for example `"allowed": ["\"-localhw-example\""]`. Requirements can also enforce a reviewed exclusion with `"allowed": ["n"]`. A missing symbol is a failure even when `n` is allowed: investigate renames/removal and adjust the ledger rather than silently ignoring a misspelled option.

Run with a new report filename for each revision:

```bash
python3 "$vSkill/scripts/audit_config.py" --config "$vBuild/.config" \
  --baseline "$vRun/baseline-migrated.config" --requirements "$vRun/requirements.json" \
  --output "$vRun/config-audit-final.json"
"$vSource/scripts/diffconfig" "$vRun/baseline-migrated.config" "$vBuild/.config" > "$vRun/config.diff"
```

Exit code 2 means declared requirements are unmet; exit code 1 means the audit could not run. Success proves only the explicit value constraints, not dependency-independent bootability or completeness of the input requirements. Compare retained/removed symbol counts and package/installed sizes when available; symbol counts alone do not measure bytes or performance.

## Primary references

- [Kconfig configuration targets](https://docs.kernel.org/kbuild/kconfig.html): migration, mini-config and dependency constraints.
- [Kconfig language](https://docs.kernel.org/kbuild/kconfig-language.html): types, defaults, selections and dependency semantics.
- [Kernel build overview](https://docs.kernel.org/admin-guide/README.html): output directories and configuration workflow.
- [Upstream localmodconfig implementation](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/scripts/kconfig/streamline_config.pl): inspect the **downloaded release's** copy for exact behavior.
