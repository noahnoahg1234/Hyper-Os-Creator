"""Index of everything downloaded from the internet."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from . import config, net


def _index_path():
    return config.home() / "downloads" / "index.json"


def list_downloads(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        items = json.loads(_index_path().read_text())
    except (OSError, ValueError):
        items = []
    items = [i for i in items if os.path.exists(i.get("path", ""))]
    return [i for i in items if kind is None or i.get("kind") == kind]


def record(kind: str, name: str, version: str, url: str, path: str, sha256: str = "", extra: Optional[dict] = None):
    items = [i for i in list_downloads() if i["path"] != path]
    item = {"kind": kind, "name": name, "version": version, "url": url, "path": path,
            "file": os.path.basename(path), "size": os.path.getsize(path), "sha256": sha256,
            "date": time.strftime("%Y-%m-%d %H:%M"), **(extra or {})}
    items.append(item)
    _index_path().write_text(json.dumps(items, indent=2))
    return item


def fetch_to_library(kind: str, name: str, version: str, url: str, filename: str, sha256: Optional[str] = None,
                     progress=None, cancel=None, extra: Optional[dict] = None) -> Dict[str, Any]:
    folder = {"bootloader": "bootloaders", "kernel": "kernels", "iso": "isos"}.get(kind, kind)
    dest = str(config.home() / "downloads" / folder / os.path.basename(filename))
    net.download(url, dest, sha256, progress, cancel)
    return record(kind, name, version, url, dest, sha256 or net.sha256_file(dest), extra)
