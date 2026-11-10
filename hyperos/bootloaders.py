"""Bootloaders: download popular ones or create your own from code."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from . import config, downloads, net, system, toolchain

# Where to find each bootloader on the internet. "resolve" turns an entry into
# a concrete download (version, url, filename, optional sha256).
CATALOG: List[Dict[str, Any]] = [
    {"id": "grub", "name": "GNU GRUB 2", "homepage": "https://www.gnu.org/software/grub/",
     "description": "The bootloader used by most Linux distributions (BIOS + UEFI). Source tarball.",
     "provider": "index", "index": "https://ftp.gnu.org/gnu/grub/", "pattern": r"grub-(\d+(?:\.\d+)+)\.tar\.xz"},
    {"id": "limine", "name": "Limine", "homepage": "https://limine-bootloader.org/",
     "description": "Modern, portable bootloader popular for hobby OS development. Ships ready-made binaries.",
     "provider": "github", "repo": "limine-bootloader/limine", "asset": r"limine-[\d.]+\.tar\.(?:xz|gz)$"},
    {"id": "syslinux", "name": "SYSLINUX / ISOLINUX", "homepage": "https://wiki.syslinux.org/",
     "description": "Lightweight bootloaders for FAT, ext and ISO 9660 media (includes prebuilt binaries).",
     "provider": "index", "index": "https://mirrors.edge.kernel.org/pub/linux/utils/boot/syslinux/",
     "pattern": r"syslinux-(\d+\.\d+)\.tar\.xz"},
    {"id": "ipxe", "name": "iPXE", "homepage": "https://ipxe.org/",
     "description": "Network bootloader. Boot operating systems over HTTP, iSCSI and more (bootable ISO).",
     "provider": "static", "version": "latest", "url": "https://boot.ipxe.org/ipxe.iso", "filename": "ipxe.iso"},
    {"id": "refind", "name": "rEFInd", "homepage": "https://www.rodsbooks.com/refind/",
     "description": "Graphical UEFI boot manager (binary zip).",
     "provider": "static", "version": "latest", "url": "https://sourceforge.net/projects/refind/files/latest/download",
     "filename": "refind-bin.zip"},
]


def catalog() -> List[Dict[str, Any]]:
    return [{k: v for k, v in c.items() if k not in ("pattern",)} for c in CATALOG]


def resolve(entry_id: str) -> Dict[str, Any]:
    entry = next((c for c in CATALOG if c["id"] == entry_id), None)
    if entry is None:
        raise KeyError(f"unknown bootloader '{entry_id}'")
    kind = entry["provider"]
    if kind == "static":
        return {"version": entry["version"], "url": entry["url"], "filename": entry["filename"], "sha256": None}
    if kind == "index":
        found = net.latest_from_index(net.fetch_text(entry["index"]), entry["pattern"])
        if not found:
            raise RuntimeError(f"could not find a release of {entry['name']} at {entry['index']}")
        version, filename = found
        return {"version": version, "url": entry["index"] + filename, "filename": filename, "sha256": None}
    if kind == "github":
        rel = net.fetch_json(f"https://api.github.com/repos/{entry['repo']}/releases/latest")
        for asset in rel.get("assets", []):
            if re.search(entry["asset"], asset["name"]):
                return {"version": rel.get("tag_name", ""), "url": asset["browser_download_url"],
                        "filename": asset["name"], "sha256": (asset.get("digest") or "").replace("sha256:", "") or None}
        raise RuntimeError(f"no matching asset in the latest {entry['name']} release")
    raise ValueError(kind)


def download(entry_id: str, progress=None, cancel=None) -> Dict[str, Any]:
    entry = next(c for c in CATALOG if c["id"] == entry_id)
    info = resolve(entry_id)
    return downloads.fetch_to_library("bootloader", entry["name"], info["version"], info["url"], info["filename"],
                                      info["sha256"], progress, cancel)


def download_url(url: str, name: Optional[str] = None, progress=None, cancel=None) -> Dict[str, Any]:
    filename = os.path.basename(url.split("?")[0]) or "bootloader.bin"
    return downloads.fetch_to_library("bootloader", name or filename, "custom", url, filename, None, progress, cancel)


# ---------------------------------------------------------------------------
# custom bootloaders
# ---------------------------------------------------------------------------

def custom_dir():
    d = config.home() / "library" / "bootloaders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_from_code(source: str, name: str) -> Dict[str, Any]:
    """Assemble a boot sector from NASM source and save it to the library."""
    res = toolchain.assemble(source)
    if not res.ok:
        return {"ok": False, "log": res.log, "errors": res.errors}
    data = res.output
    warnings = []
    if len(data) != 512:
        warnings.append(f"boot sectors must be 512 bytes, this one is {len(data)} bytes")
    if data[510:512] != b"\x55\xaa":
        warnings.append("missing boot signature 0x55AA at the end")
    slug = config.slugify(name)
    (custom_dir() / f"{slug}.asm").write_text(source)
    (custom_dir() / f"{slug}.bin").write_bytes(data)
    return {"ok": not warnings, "size": len(data), "path": str(custom_dir() / f"{slug}.bin"), "warnings": warnings,
            "log": res.log}


def build_hyperboot(banner: str, fg: int = 15, bg: int = 1, wait_key: bool = False, name: str = "hyperboot") -> Dict:
    """Generate a HyperBoot boot sector without any external tools."""
    data = system.hyperboot_sector(banner, fg, bg, wait_key)
    path = custom_dir() / f"{config.slugify(name)}.bin"
    path.write_bytes(data)
    return {"ok": True, "size": len(data), "path": str(path)}


def build_splash(lines: List[Dict[str, Any]], fg: int = 15, bg: int = 1, name: str = "splash") -> Dict:
    data = system.splash_sector(lines, fg, bg)
    path = custom_dir() / f"{config.slugify(name)}.bin"
    path.write_bytes(data)
    img = path.with_suffix(".img")
    from .image import make_floppy
    img.write_bytes(make_floppy(data))
    return {"ok": True, "size": len(data), "path": str(path), "image": str(img)}


def list_custom() -> List[Dict[str, Any]]:
    return [{"name": p.stem, "path": str(p), "size": p.stat().st_size, "has_source": p.with_suffix(".asm").exists()}
            for p in sorted(custom_dir().glob("*.bin"))]
