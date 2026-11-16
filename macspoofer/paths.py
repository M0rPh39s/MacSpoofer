"""Filesystem locations used by MacSpoofer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "macspoofer"


def state_dir() -> Path:
    """Directory holding recorded original addresses.

    Honours ``MACSPOOFER_STATE_DIR`` first so tests and throwaway runs never
    touch the real state. Note this tool is normally run under ``sudo``: the
    path then resolves under root's home, which is deliberate -- the recorded
    originals must survive regardless of which user ran the restore.
    """
    override = os.environ.get("MACSPOOFER_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MacSpoofer"
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / APP_NAME


def originals_file() -> Path:
    """JSON file mapping interface name -> original hardware address."""
    return state_dir() / "originals.json"


def ensure_state_dir() -> Path:
    """Create and return the state directory."""
    path = state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
