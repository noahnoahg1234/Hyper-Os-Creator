"""Resources: shareable packages (themes, UI layouts, command packs, code...).

A resource is a ``.hyperpkg`` file: a zip archive containing ``manifest.json``
plus the resource files. Resources can be

* created from your systems or from files,
* published to the local registry, to a Hyper OS Creator server
  (``hyperos serve`` - share it with friends or a class) or prepared for
  submission to the public GitHub registry,
* searched and downloaded from any registry and applied to your systems.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from typing import Any, Dict, List, Optional

from . import config, net, system

TYPES = {
    "theme": "Colour theme for desktops, shell and boot banner",
    "ui-layout": "A desktop layout made in the UI editor",
    "command-pack": "Extra shell commands",
    "system-template": "A complete system to start from",
    "bootloader": "Bootloader source code or binary",
    "kernel": "Kernel source code or binary",
    "snippet": "Code snippet for the code editor",
    "iso-overlay": "Files to add to an ISO",
    "other": "Anything else",
}
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


# ---------------------------------------------------------------------------
# packages
# ---------------------------------------------------------------------------

def make_package(manifest: Dict[str, Any], files: Dict[str, bytes]) -> bytes:
    m = dict(manifest)
    m["id"] = config.slugify(m.get("id") or m.get("name", ""))
    if not _ID.match(m["id"]):
        raise ValueError("resource id must be 2-64 characters of a-z, 0-9 and '-'")
    if m.get("type") not in TYPES:
        raise ValueError(f"resource type must be one of: {', '.join(TYPES)}")
    m.setdefault("version", "1.0.0")
    m.setdefault("author", config.load_settings().get("author") or "anonymous")
    m.setdefault("description", "")
    m.setdefault("tags", [])
    m["created"] = time.strftime("%Y-%m-%d")
    m["files"] = sorted(files)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m, indent=2))
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def read_package(data: bytes) -> Dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        files = {}
        for name in z.namelist():
            if name == "manifest.json" or name.endswith("/"):
                continue
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"unsafe path in package: {name}")
            files[name] = z.read(name)
    if not _ID.match(manifest.get("id", "")) or manifest.get("type") not in TYPES:
        raise ValueError("invalid resource manifest")
    return {"manifest": manifest, "files": files}


def from_system(slug: str, rtype: str, meta: Dict[str, Any]) -> bytes:
    data = system.load(slug)
    if rtype == "ui-layout":
        files = {"ui.json": json.dumps(data["ui"], indent=2).encode()}
    elif rtype == "command-pack":
        files = {"commands.json": json.dumps(data["commands"], indent=2).encode()}
    elif rtype == "system-template":
        clean = {k: v for k, v in data.items() if k not in ("files", "resources", "created")}
        files = {"system.json": json.dumps(clean, indent=2).encode()}
        src = system.system_path(slug) / "src"
        for p in sorted(src.glob("*")):
            if p.is_file() and p.stat().st_size < 512 * 1024:
                files[f"src/{p.name}"] = p.read_bytes()
    elif rtype == "theme":
        els = data["ui"]["elements"]
        pick = lambda t: next(({"fg": e["fg"], "bg": e["bg"]} for e in els if e["type"] == t), None)  # noqa: E731
        theme = {"desktop": pick("fill") or {"fg": 15, "bg": 1}, "box": pick("box") or {"fg": 15, "bg": 1},
                 "text": pick("text") or {"fg": 15, "bg": 1},
                 "shell": {"fg": data["shell"].get("fg", 7), "bg": data["shell"].get("bg", 0)},
                 "banner": {"fg": data["bootloader"].get("fg", 15), "bg": data["bootloader"].get("bg", 1)}}
        files = {"theme.json": json.dumps(theme, indent=2).encode()}
    else:
        raise ValueError(f"cannot create a '{rtype}' resource from a system")
    return make_package({"name": meta.get("name") or f"{data['name']} {rtype}", "type": rtype, **meta}, files)


# ---------------------------------------------------------------------------
# library (installed resources)
# ---------------------------------------------------------------------------

def library_dir():
    d = config.home() / "library" / "resources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def install(data: bytes) -> Dict[str, Any]:
    pkg = read_package(data)
    rid = pkg["manifest"]["id"]
    dest = library_dir() / rid
    if dest.exists():
        shutil.rmtree(dest)
    for name, content in pkg["files"].items():
        target = config.safe_join(dest, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (dest / "manifest.json").write_text(json.dumps(pkg["manifest"], indent=2))
    (dest / "package.hyperpkg").write_bytes(data)
    return pkg["manifest"]


def installed() -> List[Dict[str, Any]]:
    out = []
    for d in sorted(library_dir().iterdir()):
        try:
            out.append(json.loads((d / "manifest.json").read_text()))
        except (OSError, ValueError):
            continue
    return out


def uninstall(rid: str) -> None:
    shutil.rmtree(config.safe_join(library_dir(), rid))


def _lib_file(rid: str, name: str) -> bytes:
    return config.safe_join(library_dir() / rid, name).read_bytes()


def apply_theme(sysdata: Dict[str, Any], theme: Dict[str, Any]) -> Dict[str, Any]:
    data = copy.deepcopy(sysdata)
    els = data["ui"]["elements"]
    boxes = [e for e in els if e["type"] == "box"]
    for e in els:
        if e["type"] == "fill" and "desktop" in theme:
            e.update(theme["desktop"])
        elif e["type"] == "box" and "box" in theme:
            e.update(theme["box"])
    for e in els:
        if e["type"] == "text" and "text" in theme:
            inside = next((b for b in reversed(boxes)
                           if b["x"] <= e["x"] < b["x"] + b["w"] and b["y"] <= e["y"] < b["y"] + b["h"]), None)
            e["fg"] = theme["text"]["fg"]
            e["bg"] = inside["bg"] if inside else theme.get("desktop", theme["text"])["bg"]
    if "shell" in theme:
        data["shell"].update(theme["shell"])
    if "banner" in theme:
        data["bootloader"].update(theme["banner"])
    return data


def apply(rid: str, slug: str) -> Dict[str, Any]:
    """Apply an installed resource to a system."""
    manifest = json.loads((library_dir() / rid / "manifest.json").read_text())
    rtype = manifest["type"]
    data = system.load(slug)
    note = ""
    if rtype == "theme":
        data = apply_theme(data, json.loads(_lib_file(rid, "theme.json")))
        note = "theme colours applied"
    elif rtype == "ui-layout":
        data["ui"] = json.loads(_lib_file(rid, "ui.json"))
        note = "desktop layout replaced"
    elif rtype == "command-pack":
        new = json.loads(_lib_file(rid, "commands.json"))
        names = {c["name"] for c in new}
        data["commands"] = [c for c in data["commands"] if c["name"] not in names] + new
        note = f"{len(new)} commands added"
    elif rtype in ("bootloader", "kernel", "snippet", "iso-overlay", "other"):
        src = system.system_path(slug) / ("src" if rtype != "iso-overlay" else "overlay")
        for name in manifest["files"]:
            target = config.safe_join(src, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_lib_file(rid, name))
        if rtype == "iso-overlay":
            data.setdefault("files", {})["/"] = "overlay"
        note = f"files copied to {src.name}/"
    elif rtype == "system-template":
        raise ValueError("system templates create a new system: use 'new system from resource'")
    data.setdefault("resources", [])
    if rid not in data["resources"]:
        data["resources"].append(rid)
    system.save(slug, data)
    return {"ok": True, "note": note}


def new_system_from(rid: str, name: str) -> str:
    template = json.loads(_lib_file(rid, "system.json"))
    slug = system.create(name, template)
    src = system.system_path(slug) / "src"
    lib_src = library_dir() / rid / "src"
    if lib_src.is_dir():
        shutil.copytree(lib_src, src, dirs_exist_ok=True)
    return slug


# ---------------------------------------------------------------------------
# registries
# ---------------------------------------------------------------------------

def local_registry_dir():
    return config.home() / "registry"


def bundled_registry_dir():
    """The starter registry that ships with Hyper OS Creator (works offline)."""
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent / "registry"


def _index_entry(data: bytes, filename: str) -> Dict[str, Any]:
    m = read_package(data)["manifest"]
    return {**m, "package": f"packages/{filename}", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def registry_index(base) -> Dict[str, Any]:
    try:
        return json.loads((base / "index.json").read_text())
    except (OSError, ValueError):
        return {"name": "Local registry", "resources": []}


def publish_local(data: bytes, base=None) -> Dict[str, Any]:
    base = base or local_registry_dir()
    m = read_package(data)["manifest"]
    filename = f"{m['id']}-{m['version']}.hyperpkg"
    (base / "packages").mkdir(parents=True, exist_ok=True)
    (base / "packages" / filename).write_bytes(data)
    index = registry_index(base)
    index["resources"] = [r for r in index["resources"] if r["id"] != m["id"]] + [_index_entry(data, filename)]
    index["resources"].sort(key=lambda r: r["id"])
    index["updated"] = time.strftime("%Y-%m-%d %H:%M")
    (base / "index.json").write_text(json.dumps(index, indent=2))
    return {"ok": True, "id": m["id"], "version": m["version"], "where": "local registry"}


def publish_remote(data: bytes, registry_url: str) -> Dict[str, Any]:
    """Publish to a Hyper OS Creator server, or prepare a GitHub submission."""
    url = registry_url.rstrip("/")
    if "raw.githubusercontent.com" in url or "github.com" in url:
        m = read_package(data)["manifest"]
        sub = config.home() / "registry" / "submissions"
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{m['id']}-{m['version']}.hyperpkg"
        path.write_bytes(data)
        return {"ok": True, "where": "github-submission", "file": str(path),
                "instructions": "GitHub registries are read-only over HTTP. Fork the repository, copy this file "
                                "into registry/packages/, run 'python tools/build_registry.py' and open a pull request."}
    api = url[: -len("/registry")] if url.endswith("/registry") else url
    res = net.post_json(api + "/api/registry/publish", {"package": base64.b64encode(data).decode()})
    return {**(res or {}), "where": api}


def search(query: str = "", rtype: str = "", include_local: bool = True) -> Dict[str, Any]:
    results, errors = [], []
    sources = []
    if include_local:
        sources.append(("local", local_registry_dir()))
        if (bundled_registry_dir() / "index.json").exists():
            sources.append(("bundled", bundled_registry_dir()))
    sources += [(u, u) for u in config.load_settings().get("registries", [])]
    q = query.lower().strip()
    for label, url in sources:
        try:
            index = registry_index(url) if not isinstance(url, str) else \
                net.fetch_json(url.rstrip("/") + "/index.json", timeout=15)
        except Exception as exc:  # noqa: BLE001 - registries can be offline
            errors.append({"registry": label, "error": str(exc)})
            continue
        for r in index.get("resources", []):
            if any(x["id"] == r.get("id") and x["registry"] in ("local", "bundled") for x in results) \
                    and label not in ("local", "bundled"):
                continue  # already available offline
            text = " ".join([r.get("id", ""), r.get("name", ""), r.get("description", ""), " ".join(r.get("tags", []))])
            if (not q or q in text.lower()) and (not rtype or r.get("type") == rtype):
                results.append({**r, "registry": label})
    return {"results": results, "errors": errors}


def get(rid: str, registry: str = "local") -> Dict[str, Any]:
    """Download a resource from a registry and install it into the library."""
    if registry in ("local", "bundled"):
        base = local_registry_dir() if registry == "local" else bundled_registry_dir()
        index = registry_index(base)
        entry = next((r for r in index["resources"] if r["id"] == rid), None)
        if entry is None:
            raise KeyError(f"'{rid}' is not in the {registry} registry")
        data = config.safe_join(base, entry["package"]).read_bytes()
    else:
        base = registry.rstrip("/")
        index = net.fetch_json(base + "/index.json")
        entry = next((r for r in index.get("resources", []) if r["id"] == rid), None)
        if entry is None:
            raise KeyError(f"'{rid}' not found in {registry}")
        data = net.fetch(base + "/" + entry["package"])
    if entry.get("sha256") and hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("checksum mismatch - the package was modified")
    return install(data)


def rebuild_index(base) -> Dict[str, Any]:
    """Regenerate index.json from the packages folder (used for the GitHub registry)."""
    index = {"name": "Hyper OS Creator community registry", "resources": []}
    for p in sorted((base / "packages").glob("*.hyperpkg")):
        index["resources"].append(_index_entry(p.read_bytes(), p.name))
    index["updated"] = time.strftime("%Y-%m-%d")
    (base / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def package_from_files(manifest: Dict[str, Any], paths: List[str]) -> bytes:
    files = {}
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for n in names:
                    full = os.path.join(root, n)
                    files[os.path.relpath(full, os.path.dirname(p.rstrip("/"))).replace(os.sep, "/")] = \
                        open(full, "rb").read()
        else:
            files[os.path.basename(p)] = open(p, "rb").read()
    return make_package(manifest, files)
