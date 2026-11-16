"""Applying and restoring hardware addresses.

Every change ends with a **read-back**: the address is set, then re-read from
the operating system and compared to what was asked for. A command that exits
0 is not proof of anything here -- Wi-Fi drivers in particular accept the
ioctl and then quietly keep the old address, and on recent Apple Silicon
hardware a Wi-Fi MAC change frequently cannot take effect at all. The result
object therefore distinguishes three outcomes:

* ``ok`` and ``verified``  -- the address was changed and confirmed;
* ``ok`` but not ``verified`` -- commands succeeded but the result could not be
  read back (an unprivileged read on macOS);
* not ``ok``               -- a command failed, or the read-back shows the old
  address, i.e. the change silently did not take.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field

from macspoofer import interfaces as ifaces
from macspoofer import oui, state
from macspoofer.command import CommandResult, have, run
from macspoofer.interfaces import Interface

__all__ = ["Step", "SpoofResult", "is_root", "root_hint", "apply_mac", "restore_mac"]


@dataclass(frozen=True)
class Step:
    """One command in a change, recorded for display and diagnosis."""

    description: str
    argv: tuple[str, ...]
    result: CommandResult | None = None

    @property
    def ok(self) -> bool:
        return self.result is None or self.result.ok

    @property
    def display(self) -> str:
        return " ".join(self.argv)


@dataclass
class SpoofResult:
    """Outcome of an apply or restore."""

    interface: str
    requested: str
    before: str | None = None
    after: str | None = None
    ok: bool = False
    verified: bool = False
    message: str = ""
    steps: list[Step] = field(default_factory=list)
    dry_run: bool = False

    @property
    def changed(self) -> bool:
        """True only when the read-back proves the address actually moved."""
        if not (self.before and self.after):
            return False
        return oui.normalise(self.before) != oui.normalise(self.after)

    @property
    def status(self) -> str:
        if self.dry_run:
            return "dry-run"
        if not self.ok:
            return "failed"
        return "ok" if self.verified else "unverified"


def is_root() -> bool:
    """True if the process has effective root privileges."""
    return hasattr(os, "geteuid") and os.geteuid() == 0


def root_hint(argv: list[str] | None = None) -> str:
    """A ready-to-paste sudo command for the current invocation."""
    args = argv if argv is not None else sys.argv
    return "sudo " + " ".join(args)


# ---------------------------------------------------------------------------
# Platform backends
# ---------------------------------------------------------------------------

def _darwin_plans(iface: Interface, mac: str) -> list[list[tuple[str, tuple[str, ...]]]]:
    """Ordered strategies for macOS, each a list of (description, argv).

    The direct assignment is tried first because it is non-disruptive. Only if
    the read-back shows it did not take do we fall back to cycling the
    interface, which drops the link and any associated Wi-Fi network.
    """
    dev = iface.name
    direct = [("set address", ("ifconfig", dev, "ether", mac))]
    if iface.kind == ifaces.WIFI:
        cycle = [
            ("power off Wi-Fi", ("networksetup", "-setairportpower", dev, "off")),
            ("set address", ("ifconfig", dev, "ether", mac)),
            ("power on Wi-Fi", ("networksetup", "-setairportpower", dev, "on")),
        ]
    else:
        cycle = [
            ("bring interface down", ("ifconfig", dev, "down")),
            ("set address", ("ifconfig", dev, "ether", mac)),
            ("bring interface up", ("ifconfig", dev, "up")),
        ]
    return [direct, cycle]


def _linux_plans(iface: Interface, mac: str) -> list[list[tuple[str, tuple[str, ...]]]]:
    """Ordered strategies for Linux."""
    dev = iface.name
    plans: list[list[tuple[str, tuple[str, ...]]]] = []
    if have("ip"):
        plans.append(
            [
                ("bring interface down", ("ip", "link", "set", "dev", dev, "down")),
                ("set address", ("ip", "link", "set", "dev", dev, "address", mac)),
                ("bring interface up", ("ip", "link", "set", "dev", dev, "up")),
            ]
        )
    if have("ifconfig"):
        plans.append(
            [
                ("bring interface down", ("ifconfig", dev, "down")),
                ("set address", ("ifconfig", dev, "hw", "ether", mac)),
                ("bring interface up", ("ifconfig", dev, "up")),
            ]
        )
    return plans


def _plans(iface: Interface, mac: str) -> list[list[tuple[str, tuple[str, ...]]]]:
    if sys.platform == "darwin":
        return _darwin_plans(iface, mac)
    if sys.platform == "linux":
        return _linux_plans(iface, mac)
    return []


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _reread(name: str, *, settle: float = 0.4) -> tuple[str | None, bool]:
    """Re-read the live address. Returns (mac, redacted)."""
    if settle:
        time.sleep(settle)
    iface = ifaces.get_interface(name)
    if iface is None:
        return None, False
    return iface.mac, iface.mac_redacted


def _preflight(iface: Interface | None, name: str, mac: str) -> SpoofResult | None:
    """Return a failed result if the request cannot proceed, else None."""
    if iface is None:
        return SpoofResult(name, mac, message=f"no such interface: {name}")
    if not ifaces.supported_platform():
        return SpoofResult(name, mac, message=f"unsupported platform: {sys.platform}")
    problem = oui.assignable_error(mac)
    if problem:
        return SpoofResult(name, mac, before=iface.mac, message=problem)
    return None


def apply_mac(
    name: str,
    mac: str,
    *,
    dry_run: bool = False,
    settle: float = 0.4,
) -> SpoofResult:
    """Set *name*'s address to *mac* and verify it by reading it back.

    The interface's original address is recorded before the first change so
    :func:`restore_mac` has somewhere to go back to.
    """
    iface = ifaces.get_interface(name)
    failure = _preflight(iface, name, mac)
    if failure is not None:
        return failure
    assert iface is not None

    mac = oui.normalise(mac)
    before = iface.mac
    result = SpoofResult(name, mac, before=before, dry_run=dry_run)

    plans = _plans(iface, mac)
    if not plans:
        result.message = "no supported tool found to change the address (need ip or ifconfig)"
        return result

    if dry_run:
        result.steps = [Step(desc, argv) for desc, argv in plans[0]]
        result.after = before
        result.ok = True
        result.message = "dry run: no command was executed"
        if len(plans) > 1:
            fallback = " ".join(plans[1][0][1])
            result.message += (
                f"\nIf the read-back shows the change did not take, the interface is "
                f"cycled and retried, starting with: {fallback}"
            )
        return result

    if not is_root():
        result.message = "changing a hardware address requires root"
        return result

    # Record the true original once, preferring the hardware address.
    baseline = iface.permanent or before
    if baseline:
        state.record_original(
            name, baseline, source="permanent" if iface.permanent else "observed"
        )

    last_error = ""
    for index, plan in enumerate(plans):
        steps: list[Step] = []
        failed = False
        for desc, argv in plan:
            outcome = run(list(argv))
            steps.append(Step(desc, argv, outcome))
            if not outcome.ok:
                failed = True
                last_error = outcome.error_text
                break
        result.steps = steps

        after, redacted = _reread(name, settle=settle)
        result.after = after

        if after and oui.normalise(after) == mac:
            result.ok = True
            result.verified = True
            result.message = f"address changed and verified on {name}"
            return result

        if not failed and redacted:
            # Commands succeeded; the OS will not let us read the result back.
            result.ok = True
            result.verified = False
            result.message = (
                "commands succeeded but the address could not be read back "
                "to confirm it (macOS restricts MAC reads)"
            )
            return result

        if not failed and after is None:
            result.ok = True
            result.verified = False
            result.message = "commands succeeded but the interface could no longer be read"
            return result

        if index < len(plans) - 1:
            continue

        if failed:
            result.message = last_error or "the address change command failed"
        else:
            result.message = (
                f"the commands reported success but {name} is still using {after} -- "
                "the driver refused the change"
            )
            if iface.kind == ifaces.WIFI and sys.platform == "darwin":
                result.message += (
                    "; Wi-Fi MAC changes are blocked on most Apple Silicon Macs"
                )
    return result


def restore_mac(name: str, *, dry_run: bool = False, settle: float = 0.4) -> SpoofResult:
    """Restore *name* to its recorded original, or its hardware address.

    The recorded original wins over the hardware address: on macOS a Wi-Fi
    interface's "original" is often a per-network private address assigned by
    the OS, and forcing the burned-in address instead would quietly undo that
    privacy feature.
    """
    iface = ifaces.get_interface(name)
    if iface is None:
        return SpoofResult(name, "", message=f"no such interface: {name}")

    record = state.get_original(name)
    target = record.original if record else iface.permanent
    if not target:
        return SpoofResult(
            name,
            "",
            before=iface.mac,
            message=(
                f"no original address known for {name}: nothing was recorded and the "
                "hardware address is not readable"
            ),
        )

    result = apply_mac(name, target, dry_run=dry_run, settle=settle)
    if result.ok and not dry_run:
        state.forget(name)
        source = "recorded original" if record else "hardware address"
        result.message = f"restored {name} to its {source} ({target})"
    return result
