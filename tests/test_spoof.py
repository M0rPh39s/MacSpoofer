"""Applying and restoring addresses against a simulated host.

The fake host below models the behaviour that matters: a driver that accepts
the change, one that reports success and silently keeps the old address, one
whose command fails outright, and an OS that will not let the result be read
back. Those are the four cases the result object has to tell apart.
"""

from __future__ import annotations

import pytest

from macspoofer import interfaces as ifaces
from macspoofer import spoof, state
from macspoofer.command import CommandResult
from macspoofer.interfaces import REDACTED_MAC


class FakeHost:
    """A macOS-like host whose interface addresses can actually change."""

    def __init__(self, *, accept=True, failing_command=None, redact=False):
        self.current = {"en0": "fc:b2:14:6e:3c:ea", "en5": "a0:ce:c8:11:22:33"}
        self.permanent = {"en0": "fc:b2:14:6e:3c:ea", "en5": "a0:ce:c8:11:22:33"}
        self.kinds = {"en0": "Wi-Fi", "en5": "USB 10/100 LAN"}
        self.accept = accept
        self.failing_command = failing_command
        self.redact = redact
        self.calls: list[tuple[str, ...]] = []

    def _ifconfig(self) -> str:
        out = []
        for name, mac in self.current.items():
            shown = REDACTED_MAC if self.redact else mac
            out.append(f"{name}: flags=8863<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500")
            out.append(f"\tether {shown}")
            out.append("\tstatus: active")
        return "\n".join(out) + "\n"

    def _networksetup(self) -> str:
        out = [""]
        for name, mac in self.permanent.items():
            out += [f"Hardware Port: {self.kinds[name]}", f"Device: {name}",
                    f"Ethernet Address: {mac}", ""]
        return "\n".join(out)

    def run(self, argv, **kwargs) -> CommandResult:
        argv = tuple(argv)
        self.calls.append(argv)
        if argv[0] == "ifconfig" and len(argv) == 2:
            return CommandResult(argv, 0, self._ifconfig(), "")
        if argv[0] == "ifconfig" and argv[1] == "-a":
            return CommandResult(argv, 0, self._ifconfig(), "")
        if argv[0] == "networksetup" and argv[1] == "-listallhardwareports":
            return CommandResult(argv, 0, self._networksetup(), "")
        if self.failing_command and self.failing_command in " ".join(argv):
            return CommandResult(argv, 1, "", "operation not permitted")
        # "ifconfig <dev> ether <mac>" is the actual assignment.
        if argv[0] == "ifconfig" and len(argv) == 4 and argv[2] == "ether":
            if self.accept:
                self.current[argv[1]] = argv[3]
            return CommandResult(argv, 0, "", "")
        return CommandResult(argv, 0, "", "")


@pytest.fixture
def host(monkeypatch):
    def _make(**kwargs):
        fake = FakeHost(**kwargs)
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("macspoofer.interfaces.run", fake.run)
        monkeypatch.setattr("macspoofer.spoof.run", fake.run)
        monkeypatch.setattr("macspoofer.spoof.is_root", lambda: True)
        return fake

    return _make


def test_successful_change_is_verified(host):
    fake = host()
    result = spoof.apply_mac("en5", "B8:27:EB:11:22:33", settle=0)
    assert result.ok and result.verified
    assert result.status == "ok"
    assert result.before == "a0:ce:c8:11:22:33"
    assert result.after == "b8:27:eb:11:22:33"
    assert result.changed
    assert "verified" in result.message


def test_driver_that_silently_refuses_is_reported_as_failure(host):
    """A command exiting 0 is not proof: the read-back is."""
    fake = host(accept=False)
    result = spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    assert not result.ok
    assert result.status == "failed"
    assert result.after == "a0:ce:c8:11:22:33"
    assert not result.changed
    assert "still using" in result.message


def test_wifi_refusal_mentions_apple_silicon(host):
    host(accept=False)
    result = spoof.apply_mac("en0", "b8:27:eb:11:22:33", settle=0)
    assert not result.ok
    assert "Apple Silicon" in result.message


def test_wifi_falls_back_to_cycling_the_interface(host):
    """The direct attempt is tried first; cycling is the fallback."""
    fake = host(accept=False)
    spoof.apply_mac("en0", "b8:27:eb:11:22:33", settle=0)
    joined = [" ".join(c) for c in fake.calls]
    assert any("setairportpower en0 off" in c for c in joined)
    assert any("setairportpower en0 on" in c for c in joined)


def test_failing_command_is_surfaced(host):
    host(failing_command="ether")
    result = spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    assert not result.ok
    assert "not permitted" in result.message


def test_unreadable_result_is_unverified_not_failed(host):
    """macOS hiding the address must not be reported as a failed change."""
    host(redact=True)
    result = spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    assert result.ok and not result.verified
    assert result.status == "unverified"
    assert "could not be read back" in result.message


def test_non_root_is_refused_before_running_anything(host):
    fake = host()
    fake.calls.clear()
    import macspoofer.spoof as spoof_mod

    spoof_mod.is_root = lambda: False
    try:
        result = spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    finally:
        spoof_mod.is_root = lambda: True
    assert not result.ok
    assert "requires root" in result.message
    assert not any(c[2:3] == ("ether",) for c in fake.calls)


def test_unassignable_address_is_rejected(host):
    host()
    for bad in ("01:00:5e:00:00:01", "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", "garbage"):
        result = spoof.apply_mac("en5", bad, settle=0)
        assert not result.ok, bad


def test_unknown_interface_is_rejected(host):
    host()
    assert "no such interface" in spoof.apply_mac("wlan99", "b8:27:eb:11:22:33").message


def test_dry_run_changes_nothing(host):
    fake = host()
    result = spoof.apply_mac("en5", "b8:27:eb:11:22:33", dry_run=True, settle=0)
    assert result.ok and result.status == "dry-run"
    assert result.steps
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert not any(len(c) == 4 and c[2] == "ether" for c in fake.calls)


def test_apply_records_the_original_once(host):
    host()
    spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    record = state.get_original("en5")
    assert record.original == "a0:ce:c8:11:22:33"
    assert record.source == "permanent"
    # A second spoof must not overwrite the recorded original.
    spoof.apply_mac("en5", "dc:a6:32:44:55:66", settle=0)
    assert state.get_original("en5").original == "a0:ce:c8:11:22:33"


def test_restore_returns_to_the_recorded_original(host):
    fake = host()
    spoof.apply_mac("en5", "b8:27:eb:11:22:33", settle=0)
    assert fake.current["en5"] == "b8:27:eb:11:22:33"
    result = spoof.restore_mac("en5", settle=0)
    assert result.ok and result.verified
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert "recorded original" in result.message
    # The record is cleared once restored.
    assert state.get_original("en5") is None


def test_restore_without_a_record_uses_the_hardware_address(host):
    fake = host()
    fake.current["en5"] = "b8:27:eb:11:22:33"
    result = spoof.restore_mac("en5", settle=0)
    assert result.ok
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert "hardware address" in result.message


def test_restore_with_nothing_to_go_back_to_fails_clearly(host):
    fake = host(redact=True)
    fake.permanent.clear()
    result = spoof.restore_mac("en5", settle=0)
    assert not result.ok
    assert "no original address known" in result.message


def test_restore_unknown_interface(host):
    host()
    assert "no such interface" in spoof.restore_mac("wlan99").message


def test_root_hint_quotes_the_invocation():
    assert spoof.root_hint(["macspoofer", "set", "-i", "en0"]).startswith("sudo macspoofer")


def test_unsupported_platform_is_refused(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(
        "macspoofer.interfaces.get_interface",
        lambda name: ifaces.Interface(name=name, mac="aa:bb:cc:dd:ee:ff", kind=ifaces.ETHERNET),
    )
    result = spoof.apply_mac("eth0", "b8:27:eb:11:22:33")
    assert not result.ok
    assert "unsupported platform" in result.message
