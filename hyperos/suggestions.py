"""Feature suggestions: collect ideas, vote on them and send them upstream."""
from __future__ import annotations

import json
import time
import urllib.parse
import uuid
from typing import Any, Dict, List

from . import config

CATEGORIES = ["bootloader", "kernel", "ui-editor", "code-editor", "iso", "resources", "cli", "other"]
STATUSES = ["new", "planned", "in-progress", "done", "declined"]


def _path():
    return config.home() / "suggestions.json"


def _load() -> List[Dict[str, Any]]:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    _path().write_text(json.dumps(items, indent=2))


def list_suggestions(sort: str = "votes", category: str = "") -> List[Dict[str, Any]]:
    items = [s for s in _load() if not category or s["category"] == category]
    key = (lambda s: (-s["votes"], -s["created"])) if sort == "votes" else (lambda s: -s["created"])
    return sorted(items, key=key)


def add(title: str, description: str = "", category: str = "other", author: str = "") -> Dict[str, Any]:
    title = title.strip()
    if len(title) < 4:
        raise ValueError("please give your suggestion a title (at least 4 characters)")
    item = {"id": uuid.uuid4().hex[:8], "title": title[:120], "description": description.strip()[:4000],
            "category": category if category in CATEGORIES else "other",
            "author": author.strip()[:60] or config.load_settings().get("author") or "anonymous",
            "votes": 1, "status": "new", "created": time.time()}
    items = _load()
    items.append(item)
    _save(items)
    return item


def _update(sid: str, fn) -> Dict[str, Any]:
    items = _load()
    for s in items:
        if s["id"] == sid:
            fn(s)
            _save(items)
            return s
    raise KeyError(f"no suggestion {sid}")


def vote(sid: str, delta: int = 1) -> Dict[str, Any]:
    return _update(sid, lambda s: s.update(votes=max(0, s["votes"] + (1 if delta > 0 else -1))))


def set_status(sid: str, status: str) -> Dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    return _update(sid, lambda s: s.update(status=status))


def delete(sid: str) -> None:
    _save([s for s in _load() if s["id"] != sid])


def issue_url(sid: str) -> str:
    """A pre-filled GitHub "new issue" link so the idea reaches the developers."""
    s = next(x for x in _load() if x["id"] == sid)
    repo = config.load_settings().get("suggestions_repo")
    body = (f"**Category:** {s['category']}\n\n{s['description'] or '(no description)'}\n\n"
            f"_Suggested from Hyper OS Creator ({s['votes']} local votes)._")
    q = urllib.parse.urlencode({"title": f"[Suggestion] {s['title']}", "body": body, "labels": "enhancement"})
    return f"https://github.com/{repo}/issues/new?{q}"
