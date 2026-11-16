"""Generating an address from a profile."""

from __future__ import annotations

import pytest

from macspoofer import generator, oui, profiles
from macspoofer.generator import GenerationError


def test_vendor_profile_uses_one_of_its_own_ouis():
    profile = profiles.profile_by_key("raspberry-pi")
    for _ in range(30):
        gen = generator.generate(profile)
        assert gen.prefix in profile.ouis
        assert gen.mac.startswith(gen.prefix)
        assert gen.vendor == profile.vendor


def test_pinned_prefix_is_honoured():
    gen = generator.generate_for_key("apple-iphone", prefix="3C-07-54")
    assert gen.mac.startswith("3c:07:54:")
    assert gen.prefix == "3c:07:54"


def test_pinned_prefix_must_be_valid():
    with pytest.raises(oui.MacError):
        generator.generate_for_key("apple-iphone", prefix="zz:zz:zz")


def test_random_local_profile_has_no_vendor():
    gen = generator.generate_for_key(profiles.RANDOM_LOCAL_KEY)
    assert gen.prefix is None
    assert gen.vendor == "none"
    assert oui.is_local(gen.mac)
    assert "locally administered" in gen.explanation


def test_random_vendor_resolves_to_a_real_profile():
    seen = set()
    for _ in range(40):
        gen = generator.generate_for_key(profiles.RANDOM_VENDOR_KEY)
        assert gen.prefix is not None
        # It must resolve to a concrete catalogue profile and use its own prefix.
        assert gen.prefix in gen.profile.ouis
        assert oui.is_assignable(gen.mac)
        seen.add(gen.profile.key)
    # It should not keep landing on the same profile.
    assert len(seen) > 1
    assert profiles.RANDOM_VENDOR_KEY not in seen


def test_custom_profile_requires_and_validates_a_mac():
    gen = generator.generate_for_key("custom", custom_mac="AA-BB-CC-11-22-33")
    assert gen.mac == "aa:bb:cc:11:22:33"
    with pytest.raises(GenerationError):
        generator.generate_for_key("custom")
    with pytest.raises(GenerationError):
        generator.generate_for_key("custom", custom_mac="ff:ff:ff:ff:ff:ff")
    with pytest.raises(GenerationError):
        generator.generate_for_key("custom", custom_mac="01:00:5e:00:00:01")


def test_unknown_key_is_rejected():
    with pytest.raises(GenerationError):
        generator.generate_for_key("not-a-device")


def test_every_catalogue_profile_can_generate():
    """No profile in the catalogue may be a dead end in the wizard."""
    for profile in profiles.all_profiles():
        if profile.key == "custom":
            gen = generator.generate(profile, custom_mac="aa:bb:cc:dd:ee:ff")
        else:
            gen = generator.generate(profile)
        assert oui.is_assignable(gen.mac), profile.key
        assert gen.explanation
