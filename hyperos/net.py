"""Small HTTP helpers (stdlib only) with progress reporting and checksums."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

USER_AGENT = "HyperOSCreator/1.0 (+https://github.com/noahnoahg1234/Hyper-Os-Creator)"
Progress = Optional[Callable[[int, int], None]]


def _open(url: str, timeout: int = 30, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch(url: str, timeout: int = 30) -> bytes:
    with _open(url, timeout) as resp:
        return resp.read()


def fetch_text(url: str, timeout: int = 30) -> str:
    return fetch(url, timeout).decode("utf-8", "replace")


def fetch_json(url: str, timeout: int = 30) -> Any:
    return json.loads(fetch_text(url, timeout))


def post_json(url: str, payload: Any, timeout: int = 60) -> Any:
    body = json.dumps(payload).encode()
    with _open(url, timeout, body, {"Content-Type": "application/json"}) as resp:
        return json.loads(resp.read().decode() or "null")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: str, sha256: Optional[str] = None, progress: Progress = None,
             cancel: Optional[Callable[[], bool]] = None) -> str:
    """Download ``url`` to ``dest`` (atomically) and verify the SHA-256 if given."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = dest + ".part"
    h = hashlib.sha256()
    with _open(url, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel and cancel():
                raise RuntimeError("download cancelled")
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        os.remove(part)
        raise ValueError(f"checksum mismatch for {os.path.basename(dest)}: expected {sha256}, got {h.hexdigest()}")
    os.replace(part, dest)
    return dest


def version_key(v: str) -> Tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.\-]", v))


def latest_from_index(html: str, pattern: str) -> Optional[Tuple[str, str]]:
    """Find the newest ``(version, filename)`` in a directory listing."""
    found: Dict[str, str] = {}
    for m in re.finditer(pattern, html):
        found[m.group(1)] = m.group(0)
    if not found:
        return None
    best = max(found, key=version_key)
    return best, found[best]


def parse_sha256sums(text: str) -> List[Tuple[str, str]]:
    """Parse ``sha256sum`` output (and the BSD style ``SHA256 (f) = h``)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S+)$", line.strip())
        if m:
            out.append((m.group(2), m.group(1).lower()))
            continue
        m = re.match(r"^SHA256 \((.+)\) = ([0-9a-fA-F]{64})$", line.strip())
        if m:
            out.append((m.group(1), m.group(2).lower()))
    return out
