"""Interface discovery and the macOS read restriction."""

from __future__ import annotations

from macspoofer import interfaces as ifaces


def test_darwin_parses_current_and_permanent_addresses(darwin_env):
    found = {i.name: i for i in ifaces.list_interfaces(include_all=True)}
    assert set(found) >= {"lo0", "en0", "en5", "utun0"}

    wifi = found["en0"]
    assert wifi.mac == "06:03:20:42:4f:5b"          # ifconfig: in use now
    assert wifi.permanent == "fc:b2:14:6e:3c:ea"    # networksetup: burned in
    assert wifi.kind == ifaces.WIFI
    assert wifi.friendly == "Wi-Fi"
    assert wifi.up and wifi.status == "active"


def test_darwin_detects_a_spoofed_interface(darwin_env):
    wifi = ifaces.get_interface("en0")
    assert wifi.spoofed is True
    assert wifi.locally_administered is True   # 0x06 has the U/L bit set
    assert wifi.display_mac == "06:03:20:42:4f:5b"


def test_redacted_address_is_not_treated_as_real(darwin_env):
    """02:00:00:00:00:00 is macOS hiding the address, not an address."""
    usb = ifaces.get_interface("en5")
    assert usb.mac is None
    assert usb.mac_redacted is True
    assert usb.display_mac == "unreadable (needs root)"
    # "Cannot tell" must not be reported as "spoofed".
    assert usb.spoofed is False
    assert usb.best_known_mac == "a0:ce:c8:11:22:33"
    assert ifaces.reads_restricted() is True


def test_redacted_interface_is_still_spoofable(darwin_env):
    """The change works under root even when the display does not."""
    assert ifaces.get_interface("en5").spoofable is True


def test_classification_and_filtering(darwin_env):
    assert ifaces.get_interface("lo0").kind == ifaces.LOOPBACK
    assert ifaces.get_interface("utun0").kind == ifaces.TUNNEL
    assert ifaces.get_interface("en5").kind == ifaces.ETHERNET
    # The default listing hides loopback and tunnels.
    names = {i.name for i in ifaces.list_interfaces()}
    assert names == {"en0", "en5"}


def test_missing_interface_returns_none(darwin_env):
    assert ifaces.get_interface("wlan99") is None
    assert ifaces.current_mac("wlan99") is None
    assert ifaces.permanent_mac("wlan99") is None
    assert ifaces.current_mac("en0") == "06:03:20:42:4f:5b"


def test_unsupported_platform_lists_nothing(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert ifaces.list_interfaces() == ()
    assert ifaces.supported_platform() is False
    assert ifaces.reads_restricted() is False


def test_label_prefers_the_friendly_name(darwin_env):
    assert ifaces.get_interface("en0").label == "en0 (Wi-Fi)"
    assert ifaces.Interface(name="eth0").label == "eth0"
