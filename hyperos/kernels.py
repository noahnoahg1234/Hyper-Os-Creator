"""Kernels: download Linux kernels from the internet or build custom kernels."""
from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from typing import Any, Dict, List, Optional

from . import config, downloads, net

RELEASES_URL = "https://www.kernel.org/releases.json"

# Ready-to-boot kernels (bzImage + initramfs) that run straight away in QEMU.
PREBUILT: List[Dict[str, Any]] = [
    {"id": "alpine-virt", "name": "Alpine Linux virt kernel",
     "description": "Small prebuilt Linux kernel + initramfs for virtual machines.",
     "base": "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/netboot/",
     "files": ["vmlinuz-virt", "initramfs-virt"]},
    {"id": "alpine-lts", "name": "Alpine Linux LTS kernel",
     "description": "Prebuilt long-term-support Linux kernel + initramfs (works on real hardware).",
     "base": "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/netboot/",
     "files": ["vmlinuz-lts", "initramfs-lts"]},
]

# Feature switches for the custom Linux kernel builder -> Kconfig options.
LINUX_FEATURES: Dict[str, Dict[str, Any]] = {
    "base": {"label": "Bootable base (64-bit, printk, TTY, ELF)", "options": [
        "CONFIG_64BIT=y", "CONFIG_PRINTK=y", "CONFIG_TTY=y", "CONFIG_BINFMT_ELF=y", "CONFIG_BINFMT_SCRIPT=y",
        "CONFIG_BLK_DEV_INITRD=y", "CONFIG_RD_GZIP=y", "CONFIG_DEVTMPFS=y", "CONFIG_DEVTMPFS_MOUNT=y"]},
    "serial": {"label": "Serial console", "options": ["CONFIG_SERIAL_8250=y", "CONFIG_SERIAL_8250_CONSOLE=y"]},
    "vga": {"label": "VGA text console", "options": ["CONFIG_VT=y", "CONFIG_VGA_CONSOLE=y", "CONFIG_VT_CONSOLE=y"]},
    "framebuffer": {"label": "Framebuffer graphics", "options": [
        "CONFIG_FB=y", "CONFIG_FB_VESA=y", "CONFIG_FB_EFI=y", "CONFIG_FRAMEBUFFER_CONSOLE=y", "CONFIG_DRM=y"]},
    "usb": {"label": "USB keyboards and storage", "options": [
        "CONFIG_USB_SUPPORT=y", "CONFIG_USB=y", "CONFIG_USB_XHCI_HCD=y", "CONFIG_USB_EHCI_HCD=y",
        "CONFIG_USB_HID=y", "CONFIG_HID_GENERIC=y", "CONFIG_USB_STORAGE=y"]},
    "network": {"label": "Networking (TCP/IP + virtio/e1000)", "options": [
        "CONFIG_NET=y", "CONFIG_INET=y", "CONFIG_PACKET=y", "CONFIG_UNIX=y", "CONFIG_NETDEVICES=y",
        "CONFIG_E1000=y", "CONFIG_VIRTIO_NET=y"]},
    "storage": {"label": "Disks (SATA, NVMe, virtio) + ext4/FAT", "options": [
        "CONFIG_BLOCK=y", "CONFIG_ATA=y", "CONFIG_SATA_AHCI=y", "CONFIG_BLK_DEV_NVME=y", "CONFIG_VIRTIO_BLK=y",
        "CONFIG_EXT4_FS=y", "CONFIG_VFAT_FS=y", "CONFIG_ISO9660_FS=y"]},
    "virtio": {"label": "VM optimisations (virtio, KVM guest)", "options": [
        "CONFIG_HYPERVISOR_GUEST=y", "CONFIG_KVM_GUEST=y", "CONFIG_PCI=y", "CONFIG_VIRTIO_PCI=y",
        "CONFIG_VIRTIO_CONSOLE=y"]},
    "efi": {"label": "UEFI boot (EFI stub)", "options": ["CONFIG_EFI=y", "CONFIG_EFI_STUB=y"]},
    "sound": {"label": "Sound (HDA)", "options": ["CONFIG_SOUND=y", "CONFIG_SND=y", "CONFIG_SND_HDA_INTEL=y"]},
}


def releases() -> List[Dict[str, Any]]:
    data = net.fetch_json(RELEASES_URL)
    return parse_releases(data)


def parse_releases(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in data.get("releases", []):
        if not r.get("source"):
            continue
        out.append({"version": r["version"], "moniker": r.get("moniker", ""), "eol": bool(r.get("iseol")),
                    "date": (r.get("released") or {}).get("isodate", ""), "url": r["source"],
                    "latest": r["version"] == (data.get("latest_stable") or {}).get("version")})
    return out


def download_source(version: str, progress=None, cancel=None) -> Dict[str, Any]:
    rel = next((r for r in releases() if r["version"] == version), None)
    if rel is None:
        raise KeyError(f"kernel {version} not found on kernel.org")
    return downloads.fetch_to_library("kernel", "Linux", version, rel["url"], os.path.basename(rel["url"]),
                                      None, progress, cancel, {"type": "source"})


def download_prebuilt(pid: str, progress=None, cancel=None) -> List[Dict[str, Any]]:
    entry = next((p for p in PREBUILT if p["id"] == pid), None)
    if entry is None:
        raise KeyError(f"unknown prebuilt kernel '{pid}'")
    out = []
    for f in entry["files"]:
        out.append(downloads.fetch_to_library("kernel", entry["name"], "latest", entry["base"] + f, f, None,
                                              progress, cancel, {"type": "prebuilt"}))
    return out


def download_url(url: str, progress=None, cancel=None) -> Dict[str, Any]:
    filename = os.path.basename(url.split("?")[0]) or "kernel"
    return downloads.fetch_to_library("kernel", filename, "custom", url, filename, None, progress, cancel)


# ---------------------------------------------------------------------------
# custom Linux kernels
# ---------------------------------------------------------------------------

def config_fragment(features: List[str], extra: str = "", local_version: str = "-hyperos") -> str:
    lines = [f'CONFIG_LOCALVERSION="{local_version}"', "# generated by Hyper OS Creator"]
    for f in features:
        if f in LINUX_FEATURES:
            lines.append(f"# {LINUX_FEATURES[f]['label']}")
            lines += LINUX_FEATURES[f]["options"]
    lines += [ln.strip() for ln in extra.splitlines() if ln.strip()]
    return "\n".join(lines) + "\n"


def build_dir() -> str:
    d = config.home() / "library" / "kernels"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def extract_source(tarball: str, log=print) -> str:
    dest = os.path.join(build_dir(), os.path.basename(tarball).split(".tar")[0])
    if os.path.isdir(dest):
        return dest
    log(f"extracting {os.path.basename(tarball)} ...")
    with tarfile.open(tarball) as tf:
        tf.extractall(build_dir(), filter="data")
    return dest


def build_linux(tarball: str, features: List[str], extra: str = "", base: str = "tinyconfig",
                jobs: Optional[int] = None, log=print) -> Dict[str, Any]:
    """Configure and compile a Linux kernel. Needs make, gcc, flex, bison, bc..."""
    for tool in ("make", "gcc", "flex", "bison", "bc"):
        if not shutil.which(tool):
            raise RuntimeError(f"'{tool}' is required to build Linux (install build-essential flex bison bc "
                               "libelf-dev libssl-dev)")
    src = extract_source(tarball, log)
    frag = os.path.join(src, "hyperos.config")
    with open(frag, "w") as fh:
        fh.write(config_fragment(features, extra))
    jobs = jobs or os.cpu_count() or 2
    steps = [["make", base], ["scripts/kconfig/merge_config.sh", "-m", ".config", "hyperos.config"],
             ["make", "olddefconfig"], ["make", f"-j{jobs}", "bzImage"]]
    for cmd in steps:
        log("$ " + " ".join(cmd))
        proc = subprocess.Popen(cmd, cwd=src, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log(line.rstrip())
        if proc.wait() != 0:
            raise RuntimeError(f"step failed: {' '.join(cmd)}")
    image = os.path.join(src, "arch", "x86", "boot", "bzImage")
    out = os.path.join(build_dir(), f"bzImage-{os.path.basename(src)}-hyperos")
    shutil.copy(image, out)
    log(f"kernel ready: {out}")
    return {"ok": True, "image": out}
