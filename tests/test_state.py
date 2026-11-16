"""Recording and restoring original addresses."""

from __future__ import annotations

from macspoofer import paths, state


def test_empty_state_loads_cleanly():
    assert state.load() == {}
    assert state.get_original("en0") is None


def test_record_and_read_back():
    record = state.record_original("en0", "FC:B2:14:6E:3C:EA", source="permanent")
    assert record.original == "fc:b2:14:6e:3c:ea"
    assert record.source == "permanent"
    assert state.get_original("en0").original == "fc:b2:14:6e:3c:ea"
    assert record.recorded_iso


def test_record_never_overwrites_the_first_original():
    """The whole point: a second spoof must not clobber the true original."""
    state.record_original("en0", "fc:b2:14:6e:3c:ea")
    again = state.record_original("en0", "b8:27:eb:11:22:33")
    assert again.original == "fc:b2:14:6e:3c:ea"


def test_forget_and_clear():
    state.record_original("en0", "fc:b2:14:6e:3c:ea")
    state.record_original("en1", "a0:ce:c8:11:22:33")
    assert state.forget("en0") is True
    assert state.forget("en0") is False
    assert set(state.load()) == {"en1"}
    assert state.clear() == 1
    assert state.load() == {}


def test_state_file_is_owner_only():
    state.record_original("en0", "fc:b2:14:6e:3c:ea")
    assert paths.originals_file().stat().st_mode & 0o077 == 0


def test_corrupt_state_is_ignored_not_fatal():
    paths.ensure_state_dir()
    paths.originals_file().write_text("{ not json", encoding="utf-8")
    assert state.load() == {}


def test_invalid_addresses_in_state_are_dropped():
    paths.ensure_state_dir()
    paths.originals_file().write_text(
        '{"schema": 1, "interfaces": {"en0": {"original": "nope"}, '
        '"en1": {"original": "aa:bb:cc:dd:ee:ff"}}}',
        encoding="utf-8",
    )
    assert set(state.load()) == {"en1"}
