"""Network interface discovery for macOS and Linux.

Two addresses matter per interface and they are not the same thing:

* the **current** address -- what the interface is using now, which is what a
  switch, DHCP server or sniffer sees;
* the **permanent** address -- the one burned into the hardware.

Where the permanent address is discoverable (``networksetup`` on macOS,
``ethtool -P`` or ``addr_assign_type`` on Linux) the two can be compared, so
MacSpoofer can tell you an interface is already spoofed and can restore it
even with no saved state.

Recent macOS versions gate reading the *current* address behind an
entitlement: an unprivileged process sees the placeholder
``02:00:00:00:00:00`` instead of the truth (``networksetup`` is exempt, which
is why the permanent address still reads correctly). That placeholder is
recognised here and reported as "unreadable" rather than passed off as a real
address -- silently believing it would make every interface look spoofed and
would make verification after a change meaningless. Running under ``sudo``,
as changing an address requires anyway, lifts the restriction.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from macspoofer import oui
from macspoofer.command import run

__all__ = [
    "Interface",
    "list_interfaces",
    "get_interface",
    "current_mac",
    "permanent_mac",
    "REDACTED_MAC",
    "reads_restricted",
]

#: Placeholder macOS hands to processes not entitled to read MAC addresses.
REDACTED_MAC = "02:00:00:00:00:00"

WIFI = "wifi"
ETHERNET = "ethernet"
BRIDGE = "bridge"
TUNNEL = "tunnel"
LOOPBACK = "loopback"
VIRTUAL = "virtual"
OTHER = "other"

#: Interface kinds a MAC change is meaningful on.
SPOOFABLE_KINDS = frozenset({WIFI, ETHERNET})

# Apple internal / link-layer helper interfaces that must never be touched:
# awdl/llw carry AirDrop and low-latency traffic, anpi are internal NICs,
# ap1 is the hotspot interface and nan0 is Neighbor Awareness Networking.
_DARWIN_RESERVED = re.compile(r"\A(lo|gif|stf|utun|awdl|llw|nan|ap|anpi|pktap|vmenet|bridge)\d*\Z")
_LINUX_RESERVED = re.compile(r"\A(lo|docker|veth|virbr|br-|tun|tap|wg|vmnet|sit|dummy)")

_DARWIN_IFACE_RE = re.compile(r"\A(?P<name>[A-Za-z][\w.\-]*):\s+flags=(?P<flags>\d+)<(?P<names>[^>]*)>")
_DARWIN_ETHER_RE = re.compile(r"\A\s+ether\s+([0-9a-fA-F:]{17})")
_DARWIN_STATUS_RE = re.compile(r"\A\s+status:\s+(\w+)")


@dataclass(frozen=True)
class Interface:
    """One network interface."""

    name: str
    mac: str | None = None
    permanent: str | None = None
    kind: str = OTHER
    up: bool = False
    status: str = "unknown"
    friendly: str = ""
    driver: str = ""
    mac_redacted: bool = False

    @property
    def label(self) -> str:
        return f"{self.name} ({self.friendly})" if self.friendly else self.name

    @property
    def spoofable(self) -> bool:
        """True if a MAC change on this interface is meaningful.

        An interface whose current address is merely unreadable still counts:
        the change itself works under root, only the display does not.
        """
        return self.kind in SPOOFABLE_KINDS and (
            self.mac is not None or self.permanent is not None
        )

    @property
    def spoofed(self) -> bool:
        """True if the current address demonstrably differs from the hardware one.

        False when either address is unknown -- "cannot tell" is not "clean",
        and callers that need the distinction check :attr:`mac_redacted`.
        """
        if not self.mac or not self.permanent:
            return False
        return oui.normalise(self.mac) != oui.normalise(self.permanent)

    @property
    def display_mac(self) -> str:
        """The current address for display, or why it is missing."""
        if self.mac:
            return self.mac
        if self.mac_redacted:
            return "unreadable (needs root)"
        return "unknown"

    @property
    def locally_administered(self) -> bool:
        """True if the current address has the U/L bit set."""
        return bool(self.mac) and oui.is_local(self.mac)

    @property
    def best_known_mac(self) -> str | None:
        """Current address if readable, else the hardware address."""
        return self.mac or self.permanent


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _darwin_hardware_ports() -> dict[str, tuple[str, str | None]]:
    """Map device -> (hardware port name, permanent MAC) via ``networksetup``.

    ``networksetup`` reports the address burned into the hardware, while
    ``ifconfig`` reports the address currently in use -- which is how a spoof
    is detected on macOS.
    """
    result = run(["networksetup", "-listallhardwareports"])
    if not result.ok:
        return {}
    ports: dict[str, tuple[str, str | None]] = {}
    port = device = mac = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            port, device, mac = line.split(":", 1)[1].strip(), None, None
        elif line.startswith("Device:"):
            device = line.split(":", 1)[1].strip()
        elif line.startswith("Ethernet Address:"):
            candidate = line.split(":", 1)[1].strip()
            mac = oui.normalise(candidate) if oui.is_valid(candidate) else None
            if device:
                ports[device] = (port or "", mac)
    return ports


def _darwin_kind(name: str, friendly: str) -> str:
    low = friendly.lower()
    if "wi-fi" in low or "airport" in low or "wireless" in low:
        return WIFI
    if "bridge" in low or name.startswith("bridge"):
        return BRIDGE
    if "ethernet" in low or "thunderbolt" in low or "lan" in low or "usb" in low:
        return ETHERNET
    if name.startswith("lo"):
        return LOOPBACK
    if name.startswith(("utun", "gif", "stf")):
        return TUNNEL
    if _DARWIN_RESERVED.match(name):
        return VIRTUAL
    if name.startswith("en"):
        return ETHERNET
    return OTHER


def _darwin_interfaces() -> list[Interface]:
    result = run(["ifconfig", "-a"])
    if not result.ok:
        return []
    ports = _darwin_hardware_ports()
    found: list[Interface] = []
    name = flags_up = mac = status = None

    def flush() -> None:
        if not name:
            return
        friendly, permanent = ports.get(name, ("", None))
        redacted = mac == REDACTED_MAC
        found.append(
            Interface(
                name=name,
                mac=None if redacted else mac,
                permanent=permanent,
                kind=_darwin_kind(name, friendly),
                up=bool(flags_up),
                status=status or "unknown",
                friendly=friendly,
                mac_redacted=redacted,
            )
        )

    for line in result.stdout.splitlines():
        header = _DARWIN_IFACE_RE.match(line)
        if header:
            flush()
            name = header.group("name")
            flags_up = "UP" in header.group("names").split(",")
            mac = status = None
            continue
        if name is None:
            continue
        ether = _DARWIN_ETHER_RE.match(line)
        if ether:
            mac = oui.normalise(ether.group(1))
            continue
        state = _DARWIN_STATUS_RE.match(line)
        if state:
            status = state.group(1)
    flush()
    return found


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------

_SYS_NET = Path("/sys/class/net")

# /sys/class/net/<if>/addr_assign_type
_ASSIGN_TYPES = {"0": "permanent", "1": "random", "2": "stolen", "3": "set"}


def _read_sys(name: str, attr: str) -> str:
    try:
        return (_SYS_NET / name / attr).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _linux_kind(name: str) -> str:
    if name == "lo":
        return LOOPBACK
    if (_SYS_NET / name / "wireless").exists() or (_SYS_NET / name / "phy80211").exists():
        return WIFI
    if (_SYS_NET / name / "bridge").exists():
        return BRIDGE
    if name.startswith(("tun", "tap", "wg")):
        return TUNNEL
    if _LINUX_RESERVED.match(name):
        return VIRTUAL
    if _read_sys(name, "type") == "1":
        return ETHERNET
    return OTHER


def _linux_permanent(name: str, current: str | None) -> str | None:
    """Best-effort permanent address.

    ``ethtool -P`` is authoritative; failing that ``addr_assign_type`` at least
    says whether the current address *is* the permanent one.
    """
    result = run(["ethtool", "-P", name])
    if result.ok:
        match = re.search(r"([0-9a-fA-F:]{17})", result.stdout)
        if match:
            mac = match.group(1)
            if oui.is_valid(mac) and not oui.is_zero(mac):
                return oui.normalise(mac)
    if _ASSIGN_TYPES.get(_read_sys(name, "addr_assign_type")) == "permanent" and current:
        return current
    return None


def _linux_interfaces() -> list[Interface]:
    if not _SYS_NET.is_dir():
        return []
    found: list[Interface] = []
    for entry in sorted(_SYS_NET.iterdir()):
        name = entry.name
        raw = _read_sys(name, "address")
        mac = oui.normalise(raw) if oui.is_valid(raw) else None
        operstate = _read_sys(name, "operstate") or "unknown"
        driver = ""
        try:
            driver = (entry / "device" / "driver").resolve().name
        except OSError:
            pass
        found.append(
            Interface(
                name=name,
                mac=mac,
                permanent=_linux_permanent(name, mac),
                kind=_linux_kind(name),
                up=operstate == "up",
                status=operstate,
                friendly=driver,
                driver=driver,
            )
        )
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reads_restricted() -> bool:
    """True if this process is being denied real MAC addresses by the OS.

    Only ever true on macOS. When it is, current addresses cannot be shown and
    a change cannot be verified by reading it back -- re-run under ``sudo``.
    """
    if sys.platform != "darwin":
        return False
    return any(i.mac_redacted for i in list_interfaces(include_all=True))


def supported_platform() -> bool:
    """True if this platform has an implemented backend."""
    return sys.platform in ("darwin", "linux")


def list_interfaces(*, include_all: bool = False) -> tuple[Interface, ...]:
    """Return the machine's interfaces.

    By default only interfaces a MAC change is meaningful on are returned
    (physical Ethernet and Wi-Fi with a readable address). ``include_all``
    returns loopback, tunnels and virtual interfaces too.
    """
    if sys.platform == "darwin":
        found = _darwin_interfaces()
    elif sys.platform == "linux":
        found = _linux_interfaces()
    else:
        return ()
    if include_all:
        return tuple(found)
    return tuple(i for i in found if i.spoofable)


def get_interface(name: str) -> Interface | None:
    """Return the interface called *name*, or None."""
    for iface in list_interfaces(include_all=True):
        if iface.name == name:
            return iface
    return None


def current_mac(name: str) -> str | None:
    """Re-read the live address of *name* straight from the OS."""
    iface = get_interface(name)
    return iface.mac if iface else None


def permanent_mac(name: str) -> str | None:
    """Return the hardware address of *name* if discoverable."""
    iface = get_interface(name)
    return iface.permanent if iface else None
