"""Workspace locations and user settings."""
from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any, Dict

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Registries used by "resources search/get". The first one is the default
    # target of "resources publish --remote".
    "registries": [
        "https://raw.githubusercontent.com/noahnoahg1234/Hyper-Os-Creator/main/registry",
    ],
    "author": "",
    "show_tips": True,
    "suggestions_repo": "noahnoahg1234/Hyper-Os-Creator",
}


def home() -> pathlib.Path:
    path = pathlib.Path(os.environ.get("HYPEROS_HOME", pathlib.Path.home() / "HyperOS")).expanduser()
    for sub in ("systems", "downloads/bootloaders", "downloads/kernels", "downloads/isos", "library",
                "registry/packages", "isowork"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> pathlib.Path:
    return home() / "settings.json"


def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULT_SETTINGS)
    try:
        data.update(json.loads(settings_path().read_text()))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: Dict[str, Any]) -> None:
    settings_path().write_text(json.dumps(data, indent=2))


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def safe_join(base: pathlib.Path, rel: str) -> pathlib.Path:
    """Join ``rel`` onto ``base`` refusing anything that escapes ``base``."""
    target = (base / rel).resolve()
    if target != base.resolve() and base.resolve() not in target.parents:
        raise ValueError(f"path escapes workspace: {rel}")
    return target
