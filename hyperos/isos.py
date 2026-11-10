"""ISO images: download distributions from the internet and modify them."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional

from . import config, downloads, net, toolchain
from .image import BootEntry, IsoReader, IsoWriter

# ---------------------------------------------------------------------------
# catalog: every resolver returns {version, url, filename, sha256}
# ---------------------------------------------------------------------------

ALPINE = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/"
DEBIAN = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
UBUNTU = "https://releases.ubuntu.com/24.04/"
ARCH_JSON = "https://archlinux.org/releng/releases/json/"
ARCH_MIRROR = "https://geo.mirror.pkgbuild.com/iso/"
TINYCORE = "http://tinycorelinux.net/16.x/x86/release/"


def parse_alpine_yaml(text: str, flavor: str) -> Dict[str, Any]:
    """Parse latest-releases.yaml (a list of mappings) without a YAML library."""
    items: List[Dict[str, str]] = []
    for line in text.splitlines():
        if line.strip() == "-":
            items.append({})
            continue
        m = re.match(r"^(-\s+|\s+)(\w+):\s*(.*)$", line)
        if not m:
            continue
        if m.group(1).startswith("-"):
            items.append({})
        if items:
            items[-1][m.group(2)] = m.group(3).strip().strip('"')
    for it in items:
        if it.get("flavor") == flavor and it.get("file", "").endswith(".iso"):
            return {"version": it.get("version", ""), "url": ALPINE + it["file"], "filename": it["file"],
                    "sha256": it.get("sha256")}
    raise RuntimeError(f"Alpine flavor {flavor} not found")


def _alpine(flavor: str) -> Callable[[], Dict[str, Any]]:
    return lambda: parse_alpine_yaml(net.fetch_text(ALPINE + "latest-releases.yaml"), flavor)


def _from_sums(base: str, sums_name: str, pattern: str) -> Callable[[], Dict[str, Any]]:
    def resolve() -> Dict[str, Any]:
        for name, digest in net.parse_sha256sums(net.fetch_text(base + sums_name)):
            m = re.fullmatch(pattern, name)
            if m:
                return {"version": m.group(1), "url": base + name, "filename": name, "sha256": digest}
        raise RuntimeError(f"no ISO matching {pattern} in {base}{sums_name}")
    return resolve


def parse_arch_json(data: Dict[str, Any]) -> Dict[str, Any]:
    rel = next(r for r in data.get("releases", []) if r.get("available", True))
    version = rel["version"]
    name = f"archlinux-{version}-x86_64.iso"
    return {"version": version, "url": f"{ARCH_MIRROR}{version}/{name}", "filename": name,
            "sha256": rel.get("sha256_sum")}


CATALOG: List[Dict[str, Any]] = [
    {"id": "alpine-virt", "name": "Alpine Linux (virt)", "size": "~65 MB",
     "description": "Tiny, security-focused Linux, optimised for virtual machines. Great for remixing.",
     "resolve": _alpine("alpine-virt")},
    {"id": "alpine-standard", "name": "Alpine Linux (standard)", "size": "~200 MB",
     "description": "Alpine for real hardware.", "resolve": _alpine("alpine-standard")},
    {"id": "debian-netinst", "name": "Debian (netinst)", "size": "~650 MB",
     "description": "The universal operating system. Small network installer.",
     "resolve": _from_sums(DEBIAN, "SHA256SUMS", r"debian-([\d.]+)-amd64-netinst\.iso")},
    {"id": "ubuntu-server", "name": "Ubuntu Server 24.04 LTS", "size": "~3 GB",
     "description": "Ubuntu long-term-support server installer.",
     "resolve": _from_sums(UBUNTU, "SHA256SUMS", r"ubuntu-([\d.]+)-live-server-amd64\.iso")},
    {"id": "ubuntu-desktop", "name": "Ubuntu Desktop 24.04 LTS", "size": "~6 GB",
     "description": "Ubuntu long-term-support desktop.",
     "resolve": _from_sums(UBUNTU, "SHA256SUMS", r"ubuntu-([\d.]+)-desktop-amd64\.iso")},
    {"id": "arch", "name": "Arch Linux", "size": "~1.2 GB",
     "description": "Rolling-release Linux for people who like to build things themselves.",
     "resolve": lambda: parse_arch_json(net.fetch_json(ARCH_JSON))},
    {"id": "tinycore", "name": "Tiny Core Linux", "size": "~25 MB",
     "description": "A complete desktop Linux in about 25 MB.",
     "resolve": lambda: {"version": "current", "url": TINYCORE + "Core-current.iso", "filename": "Core-current.iso",
                         "sha256": None}},
]


def catalog() -> List[Dict[str, Any]]:
    return [{k: v for k, v in c.items() if k != "resolve"} for c in CATALOG]


def resolve(iso_id: str) -> Dict[str, Any]:
    entry = next((c for c in CATALOG if c["id"] == iso_id), None)
    if entry is None:
        raise KeyError(f"unknown ISO '{iso_id}'")
    return entry["resolve"]()


def download(iso_id: str, progress=None, cancel=None) -> Dict[str, Any]:
    entry = next(c for c in CATALOG if c["id"] == iso_id)
    info = resolve(iso_id)
    return downloads.fetch_to_library("iso", entry["name"], info["version"], info["url"], info["filename"],
                                      info["sha256"], progress, cancel)


def download_url(url: str, sha256: Optional[str] = None, progress=None, cancel=None) -> Dict[str, Any]:
    filename = os.path.basename(url.split("?")[0]) or "image.iso"
    return downloads.fetch_to_library("iso", filename, "custom", url, filename, sha256, progress, cancel)


def local_isos() -> List[Dict[str, Any]]:
    """All ISOs we know about: downloads, built systems and remastered images."""
    out = [dict(d, source="download") for d in downloads.list_downloads("iso")]
    for p in (config.home() / "systems").glob("*/build/*.iso"):
        out.append({"name": p.stem, "file": p.name, "path": str(p), "size": p.stat().st_size, "source": "system"})
    for p in (config.home() / "isowork").glob("*/*.iso"):
        out.append({"name": p.stem, "file": p.name, "path": str(p), "size": p.stat().st_size, "source": "modified"})
    return out


# ---------------------------------------------------------------------------
# inspecting and modifying
# ---------------------------------------------------------------------------

def inspect(path: str) -> Dict[str, Any]:
    with IsoReader(path) as r:
        entries = r.entries()
        return {"volume_id": r.volume_id, "rock_ridge": r.rock_ridge, "joliet": r.joliet_root is not None,
                "boot": [b.__dict__ for b in r.boot_info()],
                "files": [{"path": e.path, "dir": e.is_dir, "size": e.size, "link": e.symlink} for e in entries],
                "file_count": sum(1 for e in entries if not e.is_dir),
                "total_size": sum(e.size for e in entries if not e.is_dir)}


def read_file(path: str, inner: str, limit: int = 1 << 20) -> bytes:
    with IsoReader(path) as r:
        return r.read_file(inner)[:limit]


def extract(path: str, dest: str, only: Optional[List[str]] = None) -> int:
    with IsoReader(path) as r:
        return r.extract(dest, only)


class Project:
    """A modification project: an original ISO + overlay files + removals."""

    def __init__(self, name: str):
        self.name = config.slugify(name)
        self.dir = config.safe_join(config.home() / "isowork", self.name)
        self.overlay = self.dir / "overlay"
        self.plan_path = self.dir / "plan.json"

    @classmethod
    def create(cls, name: str, source_iso: str) -> "Project":
        p = cls(name)
        p.overlay.mkdir(parents=True, exist_ok=True)
        with IsoReader(source_iso) as r:
            vol = r.volume_id
        p.save({"source": os.path.abspath(source_iso), "remove": [], "volume_id": vol or "HYPEROS",
                "output": f"{p.name}.iso"})
        return p

    @staticmethod
    def list_projects() -> List[Dict[str, Any]]:
        out = []
        for d in sorted((config.home() / "isowork").iterdir()):
            if (d / "plan.json").exists():
                out.append({"name": d.name, **Project(d.name).plan(), "changes": Project(d.name).changes()})
        return out

    def plan(self) -> Dict[str, Any]:
        return json.loads(self.plan_path.read_text())

    def save(self, plan: Dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(json.dumps(plan, indent=2))

    def add_file(self, iso_path: str, data: bytes) -> None:
        target = config.safe_join(self.overlay, iso_path.lstrip("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        plan = self.plan()
        plan["remove"] = [r for r in plan["remove"] if r != "/" + iso_path.strip("/")]
        self.save(plan)

    def add_local(self, iso_path: str, local: str) -> None:
        target = config.safe_join(self.overlay, iso_path.lstrip("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.isdir(local):
            shutil.copytree(local, target, dirs_exist_ok=True)
        else:
            shutil.copy(local, target)

    def remove(self, iso_path: str) -> None:
        plan = self.plan()
        path = "/" + iso_path.strip("/")
        if path not in plan["remove"]:
            plan["remove"].append(path)
        self.save(plan)
        target = config.safe_join(self.overlay, iso_path.lstrip("/"))
        if target.is_file():
            target.unlink()

    def changes(self) -> Dict[str, List[str]]:
        added = ["/" + str(p.relative_to(self.overlay)).replace(os.sep, "/")
                 for p in sorted(self.overlay.rglob("*")) if p.is_file()] if self.overlay.exists() else []
        return {"added": added, "removed": self.plan().get("remove", [])}

    def build(self, use_xorriso: Optional[bool] = None, log: Callable[[str], None] = print) -> Dict[str, Any]:
        plan = self.plan()
        out = str(self.dir / plan.get("output", f"{self.name}.iso"))
        if use_xorriso is None:
            use_xorriso = bool(toolchain.which("xorriso"))
        if use_xorriso:
            return self._build_xorriso(plan, out, log)
        return self._build_python(plan, out, log)

    def _build_xorriso(self, plan: Dict[str, Any], out: str, log) -> Dict[str, Any]:
        cmd = ["xorriso", "-indev", plan["source"], "-outdev", out, "-boot_image", "any", "replay",
               "-volid", plan.get("volume_id", "HYPEROS")[:32]]
        for r in plan.get("remove", []):
            cmd += ["-rm_r", r, "--"]
        if any(self.overlay.iterdir()):
            cmd += ["-map", str(self.overlay), "/"]
        log("$ " + " ".join(cmd))
        if os.path.exists(out):
            os.remove(out)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        log(proc.stderr[-4000:])
        if proc.returncode != 0:
            raise RuntimeError("xorriso failed (see log)")
        return {"ok": True, "iso": out, "size": os.path.getsize(out), "method": "xorriso"}

    def _build_python(self, plan: Dict[str, Any], out: str, log) -> Dict[str, Any]:
        src = plan["source"]
        removed = set(plan.get("remove", []))
        is_removed = lambda p: any(p == r or p.startswith(r + "/") for r in removed)  # noqa: E731
        warnings = []
        with IsoReader(src) as r:
            writer = IsoWriter(volume_id=plan.get("volume_id", r.volume_id or "HYPEROS"))
            n = 0
            for e in r.entries():
                if is_removed(e.path):
                    continue
                if e.is_dir:
                    writer.add_dir(e.path, e.mode)
                elif e.symlink:
                    warnings.append(f"symlink {e.path} skipped")
                else:
                    writer.add_file(e.path, (src, e.lba * 2048, e.size), e.mode)
                    n += 1
            log(f"copied {n} files from {os.path.basename(src)}")
            for p in sorted(self.overlay.rglob("*")):
                if p.is_file():
                    rel = "/" + str(p.relative_to(self.overlay)).replace(os.sep, "/")
                    writer.add_file(rel, str(p))
                    log(f"added {rel}")
            for b in r.boot_info():
                if b.file is None:
                    if b.platform == "uefi" and b.sectors:
                        data = r._sector(b.lba, (b.sectors * 512 + 2047) // 2048)[: b.sectors * 512]
                        writer.add_file("/boot/hyperos-efi.img", data)
                        writer.add_boot(BootEntry("/boot/hyperos-efi.img", "efi"))
                        log("re-created hidden UEFI boot image as /boot/hyperos-efi.img")
                    else:
                        warnings.append(f"{b.platform} boot entry has no file and was dropped")
                    continue
                if is_removed(b.file):
                    warnings.append(f"boot file {b.file} was removed - that boot method is gone")
                    continue
                emu = "efi" if b.platform == "uefi" else ("floppy" if b.emulation == "floppy" else "none")
                writer.add_boot(BootEntry(b.file, emu, b.sectors or 4, b.boot_info_table))
                log(f"boot entry: {b.platform} {b.emulation} -> {b.file}")
            if r.system_area()[510:512] == b"\x55\xaa":
                warnings.append("USB (isohybrid) boot is not preserved by the built-in builder; install xorriso "
                                "to keep it. CD/DVD and VM boot still work.")
        size = writer.write(out)
        for w in warnings:
            log("warning: " + w)
        return {"ok": True, "iso": out, "size": size, "method": "python", "warnings": warnings}
