"""Hermes profile directory — Windows local or Linux/Docker."""

from __future__ import annotations

import os
from pathlib import Path


def profile_dir() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        path = Path(env)
        if path.name == "offer-agent" or (path / "config.yaml").exists() or (path / "plugins").exists():
            return path
        nested = path / "profiles" / "offer-agent"
        if nested.exists() or env.endswith("offer-agent"):
            return nested
        return path
    windows = Path.home() / "AppData" / "Local" / "hermes" / "profiles" / "offer-agent"
    if windows.exists():
        return windows
    return Path.home() / ".hermes" / "profiles" / "offer-agent"
