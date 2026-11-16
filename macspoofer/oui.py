"""MAC address parsing, formatting, validation and generation.

A MAC address is handled here as 6 octets. Two bits of the first octet carry
meaning and drive every rule in this module:

* bit 0 (``0x01``) -- I/G bit. Set means *multicast*; a multicast address can
  never be a station address, so generation never sets it and
  :func:`assignable_error` rejects it.
* bit 1 (``0x02``) -- U/L bit. Set means *locally administered* (not drawn from
  any IEEE registry); clear means *globally unique*, i.e. the first three
  octets are a registered OUI belonging to a real vendor.

When a vendor profile is used the registered OUI is copied verbatim, so the
U/L and I/G bits come out as the registrant assigned them (both clear) and the
result is indistinguishable in form from a genuine address from that vendor.
Only the final three octets -- the NIC-specific part -- are randomised.
"""

from __future__ import annotations

import re
import secrets

__all__ = [
    "MacError",
    "normalise",
    "is_valid",
    "normalise_oui",
    "oui_of",
    "is_multicast",
    "is_local",
    "is_global",
    "is_zero",
    "is_broadcast",
    "assignable_error",
    "is_assignable",
    "random_from_oui",
    "random_local",
    "describe_bits",
]

_SEP_RE = re.compile(r"[:\-.\s]")
_MAC_RE = re.compile(r"\A[0-9a-f]{12}\Z")
_OUI_RE = re.compile(r"\A[0-9a-f]{6}\Z")

I_G_BIT = 0x01
U_L_BIT = 0x02


class MacError(ValueError):
    """Raised when a value is not a usable MAC address or OUI."""


def _compact(value: str | None) -> str:
    return _SEP_RE.sub("", (value or "").strip()).lower()


def _group(raw: str, sep: str) -> str:
    return sep.join(raw[i : i + 2] for i in range(0, len(raw), 2))


def normalise(value: str, *, sep: str = ":", upper: bool = False) -> str:
    """Return *value* as a canonical 6-octet MAC address.

    Accepts ``aa:bb:cc:dd:ee:ff``, ``AA-BB-CC-DD-EE-FF``, ``aabb.ccdd.eeff``
    and bare hex. Raises :class:`MacError` on anything else.
    """
    raw = _compact(value)
    if not _MAC_RE.match(raw):
        raise MacError(f"not a MAC address: {value!r}")
    out = _group(raw, sep)
    return out.upper() if upper else out


def is_valid(value: str) -> bool:
    """Return True if *value* parses as a 6-octet MAC address."""
    return bool(_MAC_RE.match(_compact(value)))


def normalise_oui(value: str, *, sep: str = ":", upper: bool = False) -> str:
    """Return *value* as a canonical 3-octet OUI prefix."""
    raw = _compact(value)
    if not _OUI_RE.match(raw):
        raise MacError(f"not a 3-octet OUI prefix: {value!r}")
    out = _group(raw, sep)
    return out.upper() if upper else out


def oui_of(mac: str, *, sep: str = ":", upper: bool = False) -> str:
    """Return the 3-octet OUI prefix of *mac*."""
    return normalise_oui(_compact(normalise(mac))[:6], sep=sep, upper=upper)


def _first_octet(mac: str) -> int:
    return int(_compact(normalise(mac))[:2], 16)


def is_multicast(mac: str) -> bool:
    """Return True if the I/G bit is set (a group, not a station, address)."""
    return bool(_first_octet(mac) & I_G_BIT)


def is_local(mac: str) -> bool:
    """Return True if the U/L bit is set (locally administered)."""
    return bool(_first_octet(mac) & U_L_BIT)


def is_global(mac: str) -> bool:
    """Return True if the address claims a globally unique (registered) OUI."""
    return not is_local(mac)


def is_zero(mac: str) -> bool:
    """Return True for the all-zero address."""
    return _compact(normalise(mac)) == "0" * 12


def is_broadcast(mac: str) -> bool:
    """Return True for the broadcast address."""
    return _compact(normalise(mac)) == "f" * 12


def assignable_error(value: str) -> str | None:
    """Return a human-readable reason *value* cannot be set on an interface.

    Returns ``None`` when the address is usable. Drivers reject multicast, the
    all-zero and the broadcast address, so these are caught before any
    privileged command runs rather than surfacing as an opaque ioctl failure.
    """
    try:
        mac = normalise(value)
    except MacError as exc:
        return str(exc)
    if is_zero(mac):
        return "the all-zero address 00:00:00:00:00:00 cannot be assigned"
    if is_broadcast(mac):
        return "the broadcast address ff:ff:ff:ff:ff:ff cannot be assigned"
    if is_multicast(mac):
        return (
            f"{mac} is a multicast address (I/G bit set in the first octet); "
            "interfaces only accept unicast addresses"
        )
    return None


def is_assignable(value: str) -> bool:
    """Return True if *value* can be set as an interface address."""
    return assignable_error(value) is None


def random_from_oui(prefix: str, *, rng: object | None = None) -> str:
    """Return a random MAC inside the OUI *prefix*.

    The three OUI octets are copied verbatim -- including their U/L and I/G
    bits -- and the three NIC-specific octets are drawn from a
    cryptographically secure source.
    """
    head = _compact(normalise_oui(prefix))
    randbelow = getattr(rng, "randbelow", None) if rng is not None else secrets.randbelow
    if randbelow is None:  # pragma: no cover - defensive
        randbelow = secrets.randbelow
    tail = "".join(f"{randbelow(256):02x}" for _ in range(3))
    return _group(head + tail, ":")


def random_local(*, rng: object | None = None) -> str:
    """Return a fully random *locally administered* unicast MAC.

    The U/L bit is set and the I/G bit cleared, so the address belongs to no
    vendor at all. This is the honest choice for plain privacy on a public
    network: it impersonates nothing and cannot collide with a registered OUI.
    """
    randbelow = getattr(rng, "randbelow", None) if rng is not None else secrets.randbelow
    if randbelow is None:  # pragma: no cover - defensive
        randbelow = secrets.randbelow
    first = (randbelow(256) | U_L_BIT) & ~I_G_BIT & 0xFF
    rest = "".join(f"{randbelow(256):02x}" for _ in range(5))
    return _group(f"{first:02x}" + rest, ":")


def describe_bits(mac: str) -> str:
    """Return a short description of the address's scope bits."""
    scope = "locally administered" if is_local(mac) else "globally unique (registered OUI)"
    cast = "multicast" if is_multicast(mac) else "unicast"
    return f"{cast}, {scope}"
