"""Turning a device profile into a concrete MAC address."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from macspoofer import oui, profiles
from macspoofer.profiles import CUSTOM_KEY, RANDOM_LOCAL_KEY, RANDOM_VENDOR_KEY, DeviceProfile

__all__ = ["Generated", "GenerationError", "generate", "generate_for_key"]


class GenerationError(ValueError):
    """Raised when a profile cannot produce an address from the given inputs."""


@dataclass(frozen=True)
class Generated:
    """A generated address and the reasoning behind it."""

    mac: str
    profile: DeviceProfile
    prefix: str | None
    vendor: str

    @property
    def scope(self) -> str:
        return oui.describe_bits(self.mac)

    @property
    def explanation(self) -> str:
        if self.prefix:
            return (
                f"{self.prefix} is registered to {self.vendor}; the remaining three "
                "octets are random"
            )
        if self.profile.key == RANDOM_LOCAL_KEY:
            return "no vendor identity: the U/L bit marks this as locally administered"
        return "address supplied directly"


def _pick_prefix(profile: DeviceProfile, pin: str | None) -> str:
    if pin:
        prefix = oui.normalise_oui(pin)
        return prefix
    if not profile.ouis:  # pragma: no cover - callers guard this
        raise GenerationError(f"profile {profile.key} has no OUI prefixes")
    return profile.ouis[secrets.randbelow(len(profile.ouis))]


def generate(
    profile: DeviceProfile,
    *,
    prefix: str | None = None,
    custom_mac: str | None = None,
) -> Generated:
    """Produce an address for *profile*.

    ``prefix`` pins the OUI instead of drawing one at random. ``custom_mac`` is
    required by -- and only used by -- the "custom" profile.
    """
    if profile.key == CUSTOM_KEY:
        if not custom_mac:
            raise GenerationError("the custom profile needs an explicit MAC address")
        problem = oui.assignable_error(custom_mac)
        if problem:
            raise GenerationError(problem)
        mac = oui.normalise(custom_mac)
        return Generated(mac, profile, oui.oui_of(mac), "custom")

    if profile.key == RANDOM_LOCAL_KEY:
        return Generated(oui.random_local(), profile, None, "none")

    if profile.key == RANDOM_VENDOR_KEY:
        pool = profiles.vendor_profiles()
        chosen = pool[secrets.randbelow(len(pool))]
        return generate(chosen, prefix=prefix)

    chosen_prefix = _pick_prefix(profile, prefix)
    mac = oui.random_from_oui(chosen_prefix)
    return Generated(mac, profile, oui.normalise_oui(chosen_prefix), profile.vendor)


def generate_for_key(
    key: str,
    *,
    prefix: str | None = None,
    custom_mac: str | None = None,
) -> Generated:
    """Look up *key* in the catalogue and generate an address for it."""
    profile = profiles.profile_by_key(key)
    if profile is None:
        raise GenerationError(f"unknown device profile: {key}")
    return generate(profile, prefix=prefix, custom_mac=custom_mac)
