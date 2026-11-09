# Target discovery and coverage

## Preflight

Complete and show the [initial dependency notice](build-and-delivery.md#initial-dependency-notice) before running the inventory helper. Its preliminary checks use the available shell and Debian package tools; they must work even when Python or hardware-discovery packages are missing. Missing optional reports remain review items rather than a reason to install every optional tool.

Confirm where the inventory commands run. Record `/etc/os-release`, `uname -a`, `dpkg --print-architecture`, `lscpu`, `systemd-detect-virt`, `/proc/1/cgroup`, available RAM and free space. Check writable project-local storage for both the build and uncompressed source; reserve tens of GiB and more for debug information or extra rebuilds. Choose jobs using available RAM as well as CPUs; about 2 GiB per job is a conservative starting estimate, not a guarantee.

Use an ordinary build user. If only a root shell is available, select or prepare an unprivileged build environment within the user's authorization before executing source build scripts. In a container, collect the actual target inventory outside it and use the container only for compilation. ARM/Device Tree boards require their board-specific DTB, boot-image format and bootloader integration; a generic `.deb` is not sufficient evidence of bootability.

Run `inventory.py` on the target. Its command failures remain visible in `inventory.json`; inspect them. The collector does not automatically gain privilege or install missing tools. A status of `partial` requires resolution or a documented explanation. Read-only elevated discovery can recover restricted details when already authorized. Do not capture private keys, Wi-Fi passwords or keyfile contents; hardware reports and network identifiers should stay local.

## What to collect beyond the snapshot

| Area | Evidence | Why it changes configuration |
| --- | --- | --- |
| CPU and platform | CPU vendor/features, architecture, DMI, ACPI/DT, firmware mode, SMBIOS | CPU family, topology, SMP, NUMA, timers, interrupt controllers, platform drivers, microcode and mitigations |
| Physical devices | `lspci -Dnnk`, `lsusb`, `lsusb -t`, all sysfs device modaliases and bound driver links | PCI/USB/platform/ACPI/HID/I2C/SPI/SDIO/virtio drivers, including inactive and built-in drivers |
| Storage and boot | `findmnt`, `lsblk`, `/proc/mdstat`, fstab/crypttab, swaps, initramfs listing, boot parameters | Controller → partition → RAID → dm/LVM/LUKS → root filesystem; root by UUID, network root, resume and early crypto |
| Runtime software | Running/enabled services, loaded modules, mounts, network interfaces, installed relevant packages | Namespaces, cgroups, nftables, VPN, bridge/TUN/TAP, overlay, FUSE, virtualization, tracing/BPF if used |
| Displays and audio | GPU drivers, connectors, HDMI/DP audio, ALSA, codecs, SOF/DSP topology files | DRM, framebuffer/console, GPU helpers, sound buses, codec and firmware dependencies |
| Power and peripherals | Laptop buttons/lid, battery, thermal, fan, sensors, rfkill, Bluetooth, camera, touchpad, readers, docks | ACPI/WMI/HID quirks, suspend/resume, USB composite functions and firmware |
| External modules | `dkms status`, current module filename/license/version, `/usr/src` package metadata | NVIDIA, ZFS, VirtualBox or other DKMS compatibility and signing; headers alone do not solve API changes |
| Boot trust | `mokutil --sb-state`, firmware mode, signing policy and enrolled public certs where readable | Kernel PE signature, trusted module keys, lockdown and separate external-module signatures |

Use `lsinitramfs` (or the installed initramfs generator's equivalent) to inspect the current boot image. Derive required drivers from the root chain rather than preserving every module found there: a distribution initramfs may itself contain generic extras. Read crypttab without exposing secret key contents; identify cipher/hash requirements and resume devices. For LVM, encrypted volumes and RAID, inspect `pvs/vgs/lvs`, `dmsetup ls --tree`, `cryptsetup status <mapped-name>`, `mdadm --detail <array>` as relevant. Avoid commands that print encryption keys.

Inspect `/etc/modules`, `modules-load.d`, `modprobe.d`, initramfs configuration and hooks for explicitly required modules, soft dependencies, blacklists or replacement drivers. A blacklist or an alias resolving to several drivers requires interpretation; do not load candidates to probe them automatically. Network printers may need only IP networking, while USB printers can require USB userspace access or `usblp`; distinguish these cases.

For the current real hardware, exercise ordinary features only if doing so is appropriate: connect the owner's usual peripherals, use Wi-Fi/Bluetooth, camera, audio and external displays, then take another snapshot. Ask a focused question only when absent devices or an active workflow cannot be inferred. Do not suspend/reboot a working machine merely to collect an inventory. Preserve module evidence from multiple snapshots and reconcile it with devices and software; a temporary tool such as `configs`, an unused VM module or a transient tunnel is not automatically a permanent requirement.

## Coverage ledger

Create a tab-separated file with columns:

`id | evidence | device_or_requirement | driver_or_feature | new_source_symbol | required_value | dependencies | firmware | disposition | unresolved_reason`

Use actual tab delimiters in the file. Each observed device/function and boot/software requirement needs a row. Suggested dispositions: `retain`, `remove`, `userspace-only`, `covered-by-parent`, `unresolved`. Include integrated drivers with no module link, devices lacking aliases, disabled/unbound devices and external modules. For `covered-by-parent` and `userspace-only`, record the specific parent/interface and evidence. An empty alias resolution does not justify removing a device.

Resolve current modaliases with read-only `modprobe --resolve-alias` and dependencies with `modprobe --show-depends`; neither command loads modules. Record the kernel release used for this lookup. Current `modules.alias`, `modules.builtin`, `modules.builtin.modinfo` and module metadata describe the old kernel and are discovery aids, not proof about the new one. Names and configuration symbols may change between releases.

Trace drivers into the new source's Makefile/Kbuild, Kconfig and device ID tables. `rg` by module/object name is a useful starting point, not a complete resolver for composite modules. Where a driver did not exist or was disabled in the old kernel, inspect the new source's supported IDs and options directly. Classify module candidates before making the final keep list.

Repeat the coverage check after compilation against the staged **new** modules and built-in metadata. Every unresolved required item prevents claiming hardware completeness. List disconnected-device assumptions and firmware or vendor-driver blockers in the delivered report.
