"""Catalogue integrity.

These tests do not check that a prefix belongs to the vendor claimed -- only
the IEEE registry can settle that, which is what ``macspoofer verify-oui``
does. They check the catalogue is internally consistent and usable.
"""

from __future__ import annotations

import pytest

from macspoofer import oui, profiles


def test_catalogue_is_populated():
    assert len(profiles.CATEGORIES) >= 10
    assert len(profiles.all_profiles()) >= 50


def test_profile_keys_are_unique():
    keys = [p.key for p in profiles.all_profiles()]
    assert len(keys) == len(set(keys))


def test_category_keys_are_unique():
    keys = [c.key for c in profiles.CATEGORIES]
    assert len(keys) == len(set(keys))


def test_every_category_has_profiles():
    for category in profiles.CATEGORIES:
        assert category.profiles, category.key
        assert category.label and category.description


def test_every_oui_is_a_valid_prefix():
    for prefix, profile in profiles.all_ouis():
        assert oui.normalise_oui(prefix) == prefix, f"{profile.key}: {prefix} is not normalised"


def test_vendor_ouis_are_unicast():
    """A multicast prefix could never be assigned to an interface."""
    for prefix, profile in profiles.all_ouis():
        first = int(prefix.split(":")[0], 16)
        assert not first & 0x01, f"{profile.key}: {prefix} is multicast"


def test_profile_ouis_have_no_duplicates_within_a_profile():
    for profile in profiles.all_profiles():
        assert len(profile.ouis) == len(set(profile.ouis)), profile.key


def test_synthetic_profiles_have_no_ouis():
    for key in (profiles.RANDOM_LOCAL_KEY, profiles.RANDOM_VENDOR_KEY, profiles.CUSTOM_KEY):
        profile = profiles.profile_by_key(key)
        assert profile is not None and profile.synthetic


def test_vendor_profiles_all_have_ouis():
    for profile in profiles.vendor_profiles():
        assert profile.ouis, profile.key


def test_no_profile_is_a_dead_end():
    """A profile with no OUIs that is not one of the synthetic keys is unusable.

    Pruning a prefix the IEEE registry disowns can empty a profile out; such a
    profile still appears in the wizard but can generate nothing, so it must be
    removed from the catalogue rather than left behind.
    """
    synthetic = {profiles.RANDOM_LOCAL_KEY, profiles.RANDOM_VENDOR_KEY, profiles.CUSTOM_KEY}
    for profile in profiles.all_profiles():
        if profile.key in synthetic:
            continue
        assert profile.ouis, f"{profile.key} has no OUIs and is not a synthetic profile"


def test_lookup_helpers():
    assert profiles.profile_by_key("raspberry-pi").vendor.startswith("Raspberry")
    assert profiles.profile_by_key("RASPBERRY-PI") is not None  # case-insensitive
    assert profiles.profile_by_key("missing") is None
    assert profiles.category_by_key("phone").label == "Smartphones"
    assert profiles.category_by_key("missing") is None
    assert profiles.profiles_in_category("missing") == ()
    assert len(profiles.profiles_in_category("phone")) >= 5


def test_category_of_round_trips():
    profile = profiles.profile_by_key("hikvision")
    assert profiles.category_of(profile).key == "camera"


@pytest.mark.parametrize("term,expected", [("nintendo", "nintendo-switch"), ("Apple", "apple-iphone")])
def test_search(term, expected):
    assert expected in {p.key for p in profiles.search(term)}


def test_search_empty_term_returns_nothing():
    assert profiles.search("") == ()
    assert profiles.search("   ") == ()
