"""Address parsing, bit semantics and generation."""

from __future__ import annotations

import pytest

from macspoofer import oui


@pytest.mark.parametrize(
    "value",
    ["aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabb.ccdd.eeff", "AABBCCDDEEFF", " aa bb cc dd ee ff "],
)
def test_normalise_accepts_common_formats(value):
    assert oui.normalise(value) == "aa:bb:cc:dd:ee:ff"


def test_normalise_options():
    assert oui.normalise("aabbccddeeff", sep="-", upper=True) == "AA-BB-CC-DD-EE-FF"


@pytest.mark.parametrize("value", ["", "zz:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee", "aa:bb:cc:dd:ee:ff:00", None])
def test_normalise_rejects_junk(value):
    with pytest.raises(oui.MacError):
        oui.normalise(value)
    assert oui.is_valid(value) is False


def test_oui_helpers():
    assert oui.normalise_oui("B8-27-EB") == "b8:27:eb"
    assert oui.oui_of("b8:27:eb:11:22:33") == "b8:27:eb"
    with pytest.raises(oui.MacError):
        oui.normalise_oui("b8:27")


def test_bit_semantics():
    # 0x02 set -> locally administered; 0x01 set -> multicast.
    assert oui.is_local("02:00:00:00:00:01")
    assert not oui.is_global("02:00:00:00:00:01")
    assert oui.is_multicast("01:00:5e:00:00:01")
    assert not oui.is_multicast("b8:27:eb:11:22:33")
    assert oui.is_global("b8:27:eb:11:22:33")


def test_assignable_rejects_unusable_addresses():
    assert oui.assignable_error("b8:27:eb:11:22:33") is None
    assert "multicast" in oui.assignable_error("01:00:5e:00:00:01")
    assert "all-zero" in oui.assignable_error("00:00:00:00:00:00")
    assert "broadcast" in oui.assignable_error("ff:ff:ff:ff:ff:ff")
    assert oui.assignable_error("nonsense") is not None


def test_random_from_oui_preserves_prefix_and_varies_suffix():
    generated = {oui.random_from_oui("dc:a6:32") for _ in range(50)}
    assert all(mac.startswith("dc:a6:32:") for mac in generated)
    assert all(oui.is_assignable(mac) for mac in generated)
    # The NIC-specific half is random, so 50 draws should not collapse to one.
    assert len(generated) > 40


def test_random_from_oui_keeps_vendor_bits_clear():
    mac = oui.random_from_oui("b8:27:eb")
    assert oui.is_global(mac) and not oui.is_multicast(mac)


def test_random_local_is_always_local_unicast():
    for _ in range(100):
        mac = oui.random_local()
        assert oui.is_local(mac), mac
        assert not oui.is_multicast(mac), mac
        assert oui.is_assignable(mac), mac


def test_describe_bits():
    assert "locally administered" in oui.describe_bits("02:11:22:33:44:55")
    assert "globally unique" in oui.describe_bits("b8:27:eb:11:22:33")
