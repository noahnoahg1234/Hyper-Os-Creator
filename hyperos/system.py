"""Custom systems: the project model and the build pipeline.

A system lives in ``<workspace>/systems/<slug>/`` and is described by
``system.json``. Building produces ``build/<slug>.img`` (a bootable 1.44 MB
floppy image) and ``build/<slug>.iso`` (a bootable CD image) without any
external tools. Custom NASM sources are assembled when NASM is available.
"""
from __future__ import annotations

import copy
import json
import pathlib
import shutil
import struct
import time
from typing import Any, Dict, List, Optional

from . import config, prebuilt, toolchain
from .image import BootEntry, IsoWriter, make_floppy

BOX_STYLES = {
    "single": bytes([0xDA, 0xBF, 0xC0, 0xD9, 0xC4, 0xB3]),
    "double": bytes([0xC9, 0xBB, 0xC8, 0xBC, 0xCD, 0xBA]),
    "block": bytes([0xDB] * 6),
    "ascii": b"++++-|",
    "none": b"      ",
}
COLORS = ["black", "blue", "green", "cyan", "red", "magenta", "brown", "lightgray",
          "darkgray", "lightblue", "lightgreen", "lightcyan", "lightred", "lightmagenta", "yellow", "white"]

DEFAULT_SYSTEM: Dict[str, Any] = {
    "name": "HyperOS",
    "version": "1.0",
    "description": "My first operating system made with Hyper OS Creator",
    "author": "",
    "bootloader": {"type": "hyperboot", "banner": "HyperBoot - starting HyperOS", "fg": 15, "bg": 1,
                   "wait_key": False, "source": "boot.asm"},
    "kernel": {"type": "hyperkernel", "source": "kernel.asm"},
    "shell": {"prompt": "hyper> ", "motd": "Welcome! Type 'help' to see the commands.", "fg": 7, "bg": 0},
    "ui": {"elements": [
        {"type": "fill", "fg": 15, "bg": 1},
        {"type": "box", "x": 0, "y": 0, "w": 80, "h": 3, "fg": 15, "bg": 3, "style": "double", "title": " HyperOS "},
        {"type": "text", "x": 3, "y": 1, "fg": 0, "bg": 3, "text": "Welcome to your own operating system!"},
        {"type": "box", "x": 20, "y": 7, "w": 40, "h": 9, "fg": 14, "bg": 1, "style": "single", "title": " About "},
        {"type": "text", "x": 23, "y": 9, "fg": 15, "bg": 1, "text": "Built with Hyper OS Creator"},
        {"type": "text", "x": 23, "y": 11, "fg": 11, "bg": 1, "text": "Edit me in the UI editor."},
        {"type": "text", "x": 23, "y": 13, "fg": 7, "bg": 1, "text": "Press any key for the shell"},
        {"type": "box", "x": 0, "y": 22, "w": 80, "h": 3, "fg": 0, "bg": 7, "style": "single", "title": ""},
        {"type": "text", "x": 2, "y": 23, "fg": 0, "bg": 7, "text": "[ Start ]  Shell  Files  Settings"},
    ]},
    "commands": [
        {"name": "hello", "output": "Hello from your custom OS!"},
        {"name": "about", "output": "This system was designed with Hyper OS Creator."},
    ],
    "resources": [],
    "files": {},
}


def attr(fg: int, bg: int) -> int:
    return ((int(bg) & 0x0F) << 4) | (int(fg) & 0x0F)


def _cp437(text: str) -> bytes:
    return str(text).replace("\r\n", "\n").replace("\n", "\r\n").encode("cp437", "replace").replace(b"\x00", b" ")


def systems_dir() -> pathlib.Path:
    return config.home() / "systems"


def list_systems() -> List[Dict[str, Any]]:
    out = []
    for d in sorted(systems_dir().iterdir()):
        f = d / "system.json"
        if f.is_file():
            try:
                data = json.loads(f.read_text())
            except ValueError:
                continue
            build = d / "build"
            out.append({"slug": d.name, "name": data.get("name", d.name), "version": data.get("version", ""),
                        "description": data.get("description", ""),
                        "built": (build / f"{d.name}.iso").exists(),
                        "modified": f.stat().st_mtime})
    return out


def system_path(slug: str) -> pathlib.Path:
    return config.safe_join(systems_dir(), slug)


def load(slug: str) -> Dict[str, Any]:
    p = system_path(slug) / "system.json"
    if not p.is_file():
        raise FileNotFoundError(f"no system named '{slug}'")
    data = copy.deepcopy(DEFAULT_SYSTEM)
    data.update(json.loads(p.read_text()))
    return data


def save(slug: str, data: Dict[str, Any]) -> None:
    p = system_path(slug)
    p.mkdir(parents=True, exist_ok=True)
    (p / "system.json").write_text(json.dumps(data, indent=2))


def create(name: str, template: Optional[Dict[str, Any]] = None, overwrite: bool = False) -> str:
    slug = config.slugify(name)
    p = system_path(slug)
    if (p / "system.json").exists() and not overwrite:
        raise FileExistsError(f"system '{slug}' already exists")
    data = copy.deepcopy(template or DEFAULT_SYSTEM)
    data["name"] = name
    data.setdefault("created", time.strftime("%Y-%m-%d %H:%M"))
    src = p / "src"
    src.mkdir(parents=True, exist_ok=True)
    asm = pathlib.Path(__file__).parent / "asm"
    for target, original in (("boot.asm", "hyperboot.asm"), ("kernel.asm", "hyperkernel.asm"),
                             ("splash.asm", "bootmsg.asm")):
        if not (src / target).exists():
            shutil.copy(asm / original, src / target)
    save(slug, data)
    return slug


def delete(slug: str) -> None:
    shutil.rmtree(system_path(slug))


# ---------------------------------------------------------------------------
# blob / boot sector generation
# ---------------------------------------------------------------------------

def encode_ui(elements: List[Dict[str, Any]]) -> bytes:
    out = bytearray()
    for el in elements:
        a = attr(el.get("fg", 7), el.get("bg", 0))
        kind = el.get("type")
        if kind == "fill":
            out += bytes([1, a])
        elif kind == "box":
            x = max(0, min(79, int(el.get("x", 0))))
            y = max(0, min(24, int(el.get("y", 0))))
            w = max(2, min(80 - x, int(el.get("w", 10))))
            h = max(2, min(25 - y, int(el.get("h", 5))))
            title = _cp437(el.get("title", ""))[: max(0, w - 4)]
            out += bytes([2, x, y, w, h, a]) + BOX_STYLES.get(el.get("style", "single"), BOX_STYLES["single"])
            out += title + b"\x00"
        elif kind == "text":
            x = max(0, min(79, int(el.get("x", 0))))
            y = max(0, min(24, int(el.get("y", 0))))
            text = _cp437(el.get("text", "")).replace(b"\r\n", b" ")[: 80 - x]
            out += bytes([3, x, y, a]) + text + b"\x00"
    out += b"\x00"
    return bytes(out)


def encode_blob(system: Dict[str, Any]) -> bytes:
    shell = system.get("shell", {})
    strings = [
        _cp437(system.get("name", "HyperOS"))[:40] + b"\x00",
        _cp437(system.get("version", "1.0"))[:20] + b"\x00",
        _cp437(shell.get("prompt", "> "))[:30] + b"\x00",
        _cp437(shell.get("motd", ""))[:1000] + b"\x00",
        encode_ui(system.get("ui", {}).get("elements", [])),
    ]
    cmds = [c for c in system.get("commands", []) if c.get("name")][:255]
    table = bytes([len(cmds)])
    for c in cmds:
        name = _cp437(c["name"].strip())[:63].replace(b" ", b"_")
        table += name + b"\x00" + _cp437(c.get("output", ""))[:2000] + b"\x00"
    strings.append(table)
    header_len = 4 + 2 * 6 + 1
    offsets, pos = [], header_len
    for s in strings:
        offsets.append(pos)
        pos += len(s)
    head = b"HYPR" + struct.pack("<6H", *offsets) + bytes([attr(shell.get("fg", 7), shell.get("bg", 0))])
    return head + b"".join(strings)


def hyperboot_sector(banner: str, fg: int = 15, bg: int = 1, wait_key: bool = False, sectors: int = 32) -> bytes:
    sec = bytearray(prebuilt.HYPERBOOT)
    assert sec[3:7] == b"HYPB"
    struct.pack_into("<H", sec, 7, sectors)
    sec[9] = attr(fg, bg)
    sec[10] = 1 if wait_key else 0
    msg = _cp437(banner).replace(b"\r\n", b" ")[:63]
    sec[11:75] = msg + b"\x00" * (64 - len(msg))
    return bytes(sec)


def splash_sector(lines: List[Dict[str, Any]], fg: int = 15, bg: int = 1, reboot_on_key: bool = True,
                  hide_cursor: bool = True) -> bytes:
    """A stand-alone boot sector that shows coloured text (no kernel needed)."""
    sec = bytearray(prebuilt.HYPERSPLASH)
    assert sec[3:7] == b"HYPM"
    sec[7] = attr(fg, bg)
    sec[8] = (1 if reboot_on_key else 0) | (2 if hide_cursor else 0)
    rec_off = struct.unpack_from("<H", sec, 9)[0] - 0x7C00
    recs = bytearray()
    for ln in lines:
        x, y = max(0, min(79, int(ln.get("x", 0)))), max(0, min(24, int(ln.get("y", 0))))
        text = _cp437(ln.get("text", "")).replace(b"\r\n", b" ")[: 80 - x]
        recs += struct.pack("<H", (y * 80 + x) * 2) + bytes([attr(ln.get("fg", 15), ln.get("bg", bg))]) + text + b"\x00"
    recs += b"\xff\xff"
    if rec_off + len(recs) > 510:
        raise ValueError(f"splash text too long: {rec_off + len(recs) - 510} bytes over the 512 byte limit")
    sec[rec_off:rec_off + len(recs)] = recs
    return bytes(sec)


def kernel_with_blob(kernel: bytes, system: Dict[str, Any]) -> bytes:
    if kernel[3:7] != b"HYPK":
        return kernel  # a raw custom kernel: load it as-is
    blob_at = struct.unpack_from("<H", kernel, 7)[0]
    data = kernel.ljust(blob_at, b"\x00")[:blob_at] + encode_blob(system)
    if len(data) > 0xF000:
        raise ValueError("kernel + system data exceed 60 KB; shorten your texts or commands")
    return data


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

class BuildError(Exception):
    def __init__(self, message: str, log: str = "", errors: Optional[list] = None):
        super().__init__(message)
        self.log = log
        self.errors = errors or []


def _custom_binary(base: pathlib.Path, spec: Dict[str, Any], what: str, log: List[str]) -> bytes:
    if spec.get("type") == "binary":
        p = config.safe_join(base, spec.get("file", ""))
        log.append(f"{what}: using binary {p.name}")
        return p.read_bytes()
    src = config.safe_join(base / "src", spec.get("source", f"{what}.asm"))
    res = toolchain.assemble(src.read_text(), include_dir=str(src.parent))
    if not res.ok:
        raise BuildError(f"{what}: assembly of {src.name} failed", res.log, res.errors)
    log.append(f"{what}: assembled {src.name} ({len(res.output)} bytes)")
    return res.output


def build(slug: str) -> Dict[str, Any]:
    base = system_path(slug)
    system = load(slug)
    out_dir = base / "build"
    out_dir.mkdir(exist_ok=True)
    log: List[str] = [f"Building {system['name']} {system.get('version', '')}"]

    kspec = system.get("kernel", {})
    bspec = system.get("bootloader", {})
    if bspec.get("type") == "splash":
        kernel = b""
        log.append("kernel: none (splash boot sector)")
    elif kspec.get("type", "hyperkernel") == "hyperkernel":
        kernel = kernel_with_blob(prebuilt.HYPERKERNEL, system)
        log.append(f"kernel: HyperKernel + system data ({len(kernel)} bytes)")
    else:
        kernel = kernel_with_blob(_custom_binary(base, kspec, "kernel", log), system)

    sectors = max(1, (len(kernel) + 511) // 512)
    btype = bspec.get("type", "hyperboot")
    if btype == "hyperboot":
        boot = hyperboot_sector(bspec.get("banner", system["name"]), bspec.get("fg", 15), bspec.get("bg", 1),
                                bspec.get("wait_key", False), sectors)
        log.append(f"bootloader: HyperBoot (loads {sectors} sectors)")
    elif btype == "splash":
        boot = splash_sector(bspec.get("lines", [{"x": 2, "y": 2, "text": system["name"]}]), bspec.get("fg", 15),
                             bspec.get("bg", 1), bspec.get("reboot_on_key", True))
        log.append("bootloader: HyperSplash boot sector")
    else:
        boot = _custom_binary(base, bspec, "bootloader", log)
        if len(boot) != 512 or boot[510:] != b"\x55\xaa":
            raise BuildError("bootloader must be exactly 512 bytes and end with 0x55AA", "\n".join(log))
        if boot[3:7] == b"HYPB":  # an edited HyperBoot: keep the config patchable
            struct.pack_into("<H", (boot := bytearray(boot)), 7, sectors)
            boot = bytes(boot)

    img = make_floppy(boot, kernel)
    img_path = out_dir / f"{slug}.img"
    img_path.write_bytes(img)
    (out_dir / "boot.bin").write_bytes(boot)
    if kernel:
        (out_dir / "kernel.bin").write_bytes(kernel)
    log.append(f"floppy image: {img_path.name} ({len(img)} bytes)")

    iso = IsoWriter(volume_id=config.slugify(system["name"]).replace("-", "_")[:32] or "HYPEROS",
                    publisher=system.get("author", ""))
    iso.add_file("/boot/hyperos.img", bytes(img))
    iso.add_boot(BootEntry("/boot/hyperos.img", "floppy"))
    iso.add_file("/README.TXT", (
        f"{system['name']} {system.get('version', '')}\n\n{system.get('description', '')}\n\n"
        "This disc boots on BIOS PCs and virtual machines (QEMU, VirtualBox, VMware).\n"
        "Made with Hyper OS Creator.\n").encode())
    iso.add_file("/system.json", json.dumps(system, indent=2).encode())
    for iso_path, rel in (system.get("files") or {}).items():
        local = config.safe_join(base, rel)
        if local.is_dir():
            iso.add_tree(str(local), iso_path)
        elif local.is_file():
            iso.add_file(iso_path, str(local))
    iso_path = out_dir / f"{slug}.iso"
    size = iso.write(str(iso_path))
    log.append(f"ISO image: {iso_path.name} ({size} bytes)")
    log.append("Done! Boot the .iso or .img in QEMU, VirtualBox or on real hardware.")
    return {"ok": True, "log": "\n".join(log), "image": str(img_path), "iso": str(iso_path),
            "kernel_bytes": len(kernel), "sectors": sectors}


def render_desktop(system_data: Dict[str, Any]) -> List[List[tuple]]:
    """Render the desktop exactly like HyperKernel does: 25 rows of (char, attr)."""
    screen = [[(" ", 0x07) for _ in range(80)] for _ in range(25)]
    blob = encode_ui(system_data.get("ui", {}).get("elements", []))
    i = 0

    def put(x: int, y: int, ch: int, a: int) -> None:
        if 0 <= x < 80 and 0 <= y < 25:
            screen[y][x] = (bytes([ch]).decode("cp437"), a)
    while i < len(blob) and blob[i]:
        kind = blob[i]
        if kind == 1:
            a = blob[i + 1]
            screen = [[(" ", a) for _ in range(80)] for _ in range(25)]
            i += 2
        elif kind == 2:
            x, y, w, h, a = blob[i + 1:i + 6]
            tl, tr, bl, br, hz, vt = blob[i + 6:i + 12]
            end = blob.index(0, i + 12)
            title = blob[i + 12:end]
            for r in range(h):
                for c in range(w):
                    if r == 0:
                        ch = tl if c == 0 else tr if c == w - 1 else hz
                    elif r == h - 1:
                        ch = bl if c == 0 else br if c == w - 1 else hz
                    else:
                        ch = vt if c in (0, w - 1) else 32
                    put(x + c, y + r, ch, a)
            for k, ch in enumerate(title):
                put(x + 2 + k, y, ch, a)
            i = end + 1
        elif kind == 3:
            x, y, a = blob[i + 1:i + 4]
            end = blob.index(0, i + 4)
            for k, ch in enumerate(blob[i + 4:end]):
                put(x + k, y, ch, a)
            i = end + 1
        else:
            break
    return screen


_ANSI_FG = [30, 34, 32, 36, 31, 35, 33, 37, 90, 94, 92, 96, 91, 95, 93, 97]
_ANSI_BG = [40, 44, 42, 46, 41, 45, 43, 47, 100, 104, 102, 106, 101, 105, 103, 107]


def render_ansi(system_data: Dict[str, Any]) -> str:
    lines = []
    for row in render_desktop(system_data):
        out, last = "", None
        for ch, a in row:
            if a != last:
                out += f"\x1b[{_ANSI_FG[a & 15]};{_ANSI_BG[a >> 4]}m"
                last = a
            out += ch
        lines.append(out + "\x1b[0m")
    return "\n".join(lines)
