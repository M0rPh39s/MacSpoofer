"""Persistence of each interface's original hardware address.

The original address is recorded once -- the first time MacSpoofer changes an
interface -- and never overwritten while a spoof is active. Without this,
``restore`` after a reboot-free session would have nothing to restore to:
once the address is changed, the operating system reports the spoofed value
and the true one is only recoverable from the driver (Linux ``ethtool -P``)
or not at all (most macOS interfaces).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

from macspoofer import oui, paths

__all__ = ["OriginalRecord", "load", "save", "record_original", "get_original", "forget", "clear"]

_SCHEMA = 1


@dataclass(frozen=True)
class OriginalRecord:
    """The address an interface had before MacSpoofer first touched it."""

    interface: str
    original: str
    recorded_at: float
    source: str = "observed"  # "observed" (read from the live interface) or "permanent" (driver)

    @property
    def recorded_iso(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.recorded_at))


def _read_raw() -> dict:
    path = paths.originals_file()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"schema": _SCHEMA, "interfaces": {}}
    if not isinstance(data, dict) or not isinstance(data.get("interfaces"), dict):
        return {"schema": _SCHEMA, "interfaces": {}}
    return data


def load() -> dict[str, OriginalRecord]:
    """Return every recorded original, keyed by interface name."""
    out: dict[str, OriginalRecord] = {}
    for name, entry in _read_raw().get("interfaces", {}).items():
        if not isinstance(entry, dict):
            continue
        mac = entry.get("original")
        if not isinstance(mac, str) or not oui.is_valid(mac):
            continue
        out[name] = OriginalRecord(
            interface=name,
            original=oui.normalise(mac),
            recorded_at=float(entry.get("recorded_at") or 0.0),
            source=str(entry.get("source") or "observed"),
        )
    return out


def save(records: dict[str, OriginalRecord]) -> None:
    """Write *records* atomically, readable only by the owner."""
    paths.ensure_state_dir()
    path = paths.originals_file()
    payload = {
        "schema": _SCHEMA,
        "interfaces": {
            name: {k: v for k, v in asdict(rec).items() if k != "interface"}
            for name, rec in sorted(records.items())
        },
    }
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def record_original(interface: str, mac: str, *, source: str = "observed") -> OriginalRecord:
    """Record *mac* as the original for *interface* unless one is already known.

    Returns the record in force afterwards -- the pre-existing one if there was
    one, so a second spoof never clobbers the true original with a spoofed value.
    """
    records = load()
    existing = records.get(interface)
    if existing is not None:
        return existing
    record = OriginalRecord(
        interface=interface,
        original=oui.normalise(mac),
        recorded_at=time.time(),
        source=source,
    )
    records[interface] = record
    save(records)
    return record


def get_original(interface: str) -> OriginalRecord | None:
    """Return the recorded original for *interface*, or None."""
    return load().get(interface)


def forget(interface: str) -> bool:
    """Drop the record for *interface*. Returns True if one was removed."""
    records = load()
    if interface not in records:
        return False
    del records[interface]
    save(records)
    return True


def clear() -> int:
    """Drop every record. Returns how many were removed."""
    records = load()
    count = len(records)
    save({})
    return count
