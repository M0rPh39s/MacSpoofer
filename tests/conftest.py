"""Shared fixtures.

Every test runs against a throwaway state directory so a test run can never
read or clobber the real recorded originals on the developer's machine.
"""

from __future__ import annotations

import pytest

from macspoofer.command import CommandResult


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point MacSpoofer's state directory at a temporary path."""
    monkeypatch.setenv("MACSPOOFER_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


@pytest.fixture
def ok_result():
    """Build a successful CommandResult for an arbitrary argv."""

    def _make(argv, stdout=""):
        return CommandResult(tuple(argv), 0, stdout, "")

    return _make


@pytest.fixture
def fail_result():
    """Build a failing CommandResult."""

    def _make(argv, stderr="boom"):
        return CommandResult(tuple(argv), 1, "", stderr)

    return _make


IFCONFIG_DARWIN = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\toptions=6460<TSO4,TSO6,CHANNEL_IO>
\tether 06:03:20:42:4f:5b
\tinet 192.168.1.20 netmask 0xffffff00 broadcast 192.168.1.255
\tmedia: autoselect
\tstatus: active
en5: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tether 02:00:00:00:00:00
\tstatus: inactive
utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
"""

NETWORKSETUP_DARWIN = """\

Hardware Port: Wi-Fi
Device: en0
Ethernet Address: fc:b2:14:6e:3c:ea

Hardware Port: USB 10/100 LAN
Device: en5
Ethernet Address: a0:ce:c8:11:22:33

VLAN Configurations
===================
"""


@pytest.fixture
def darwin_env(monkeypatch):
    """Make interface discovery look like a Mac with two interfaces."""
    monkeypatch.setattr("sys.platform", "darwin")

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv[0] == "ifconfig":
            return CommandResult(tuple(argv), 0, IFCONFIG_DARWIN, "")
        if argv[0] == "networksetup":
            return CommandResult(tuple(argv), 0, NETWORKSETUP_DARWIN, "")
        return CommandResult(tuple(argv), 127, "", "", missing=True)

    monkeypatch.setattr("macspoofer.interfaces.run", fake_run)
    return fake_run
