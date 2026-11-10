"""Code templates for custom bootloaders and kernels."""
from __future__ import annotations

import pathlib
import re
import shutil
from typing import Any, Dict, List

from . import config, system

ROOT = pathlib.Path(__file__).parent / "templates"
_META = re.compile(r"@(name|description|difficulty):\s*(.+)")


def _meta(path: pathlib.Path) -> Dict[str, str]:
    head = path.read_text(errors="replace")[:1200]
    return {k: v.strip() for k, v in _META.findall(head)}


def list_templates(kind: str) -> List[Dict[str, Any]]:
    """kind is 'bootloaders' or 'kernels'."""
    out = []
    for p in sorted((ROOT / kind).iterdir()):
        main = p / "kernel.c" if p.is_dir() else p
        if not main.is_file():
            continue
        meta = _meta(main)
        out.append({"id": p.stem if p.is_file() else p.name, "file": p.name, "folder": p.is_dir(),
                    "name": meta.get("name", p.stem), "description": meta.get("description", ""),
                    "difficulty": meta.get("difficulty", ""),
                    "files": sorted(f.name for f in p.iterdir()) if p.is_dir() else [p.name]})
    return out


def template_path(kind: str, tid: str) -> pathlib.Path:
    for t in list_templates(kind):
        if t["id"] == tid:
            return ROOT / kind / t["file"]
    raise KeyError(f"unknown {kind[:-1]} template '{tid}'")


def read_template(kind: str, tid: str) -> Dict[str, str]:
    p = template_path(kind, tid)
    if p.is_dir():
        return {f.name: f.read_text() for f in sorted(p.iterdir()) if f.is_file()}
    return {p.name: p.read_text()}


def use_in_system(kind: str, tid: str, slug: str) -> Dict[str, Any]:
    """Copy a template into a system's src/ folder and make the system use it."""
    p = template_path(kind, tid)
    data = system.load(slug)
    src = system.system_path(slug) / "src"
    if p.is_dir():
        dest = config.safe_join(src, p.name)
        shutil.copytree(p, dest, dirs_exist_ok=True)
        return {"copied": str(dest), "note": "Folder templates are built with their own Makefile."}
    name = ("boot-" if kind == "bootloaders" else "kernel-") + p.name
    shutil.copy(p, src / name)
    key = "bootloader" if kind == "bootloaders" else "kernel"
    if tid in ("hyperboot", "hyperkernel"):
        data[key]["type"] = tid
    else:
        data[key] = {**data.get(key, {}), "type": "custom-asm", "source": name}
    system.save(slug, data)
    return {"copied": name, "system": slug, key: data[key]}
