from __future__ import annotations

import os
import sys
from pathlib import Path


APP_CACHE_DIRNAME = "NetPlanner"


def user_cache_root() -> Path:
    override = os.environ.get("NETPLANNER_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / APP_CACHE_DIRNAME


def ensure_cache_subdir(*parts: str) -> Path:
    path = user_cache_root().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
