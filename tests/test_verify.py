"""Checking the catalogue against the IEEE registry."""

from __future__ import annotations

import pytest

from macspoofer import profiles, verify
from macspoofer.verify import VerifyError

HEADER = "Registry,Assignment,Organization Name,Organization Address\n"


def _registry_csv(rows):
    body = "".join(f'MA-L,{a},"{org}","somewhere"\n' for a, org in rows)
    return HEADER + body


def _complete(extra=()):
    """A registry containing every canary plus *extra* rows."""
    rows = [(p.replace(":", "").upper(), name) for p, name in verify.CANARY_PREFIXES.items()]
    rows += list(extra)
    # Pad past the plausibility floor with filler assignments.
    rows += [(f"{i:06X}", f"Filler {i}") for i in range(0xF00000, 0xF00000 + verify.MIN_PLAUSIBLE_ROWS)]
    return _registry_csv(rows)


def test_load_requires_a_source():
    with pytest.raises(VerifyError, match="--csv"):
        verify.load_registry()


def test_load_missing_file(tmp_path):
    with pytest.raises(VerifyError, match="could not read"):
        verify.load_registry(csv_path=str(tmp_path / "absent.csv"))


def test_load_rejects_a_non_registry_file(tmp_path):
    path = tmp_path / "junk.csv"
    path.write_text("hello,world\n1,2\n", encoding="utf-8")
    with pytest.raises(VerifyError, match="no usable rows"):
        verify.load_registry(csv_path=str(path))


def test_truncated_registry_is_refused(tmp_path):
    """The failure that matters: a partial download must not be reported on."""
    path = tmp_path / "partial.csv"
    path.write_text(_registry_csv([("FCB214", "Apple, Inc.")]), encoding="utf-8")
    with pytest.raises(VerifyError) as exc:
        verify.load_registry(csv_path=str(path))
    message = str(exc.value)
    assert "incomplete" in message
    assert "no comparison was made" in message


def test_registry_missing_canaries_is_refused(tmp_path):
    """Enough rows to look plausible, but long-standing assignments absent."""
    rows = [(f"{i:06X}", f"Filler {i}") for i in range(0xA00000, 0xA00000 + verify.MIN_PLAUSIBLE_ROWS + 10)]
    path = tmp_path / "wrong.csv"
    path.write_text(_registry_csv(rows), encoding="utf-8")
    with pytest.raises(VerifyError, match="absent"):
        verify.load_registry(csv_path=str(path))


def test_complete_registry_loads(tmp_path):
    path = tmp_path / "ok.csv"
    path.write_text(_complete(), encoding="utf-8")
    registry = verify.load_registry(csv_path=str(path))
    assert registry["00:03:93"] == "Apple"
    assert len(registry) > verify.MIN_PLAUSIBLE_ROWS


def test_verify_reports_matches_mismatches_and_unknowns(tmp_path):
    rows = [
        ("B827EB", "Raspberry Pi Foundation"),   # matches raspberry-pi
        ("DCA632", "Totally Different Corp"),    # mismatch for raspberry-pi
    ]
    path = tmp_path / "ok.csv"
    path.write_text(_complete(rows), encoding="utf-8")
    registry = verify.load_registry(csv_path=str(path))
    report = verify.verify_catalogue(registry)

    assert report.checked == len(profiles.all_ouis())
    assert report.matched >= 1
    mismatched = {(f.prefix, f.actual) for f in report.mismatched}
    assert ("dc:a6:32", "Totally Different Corp") in mismatched
    unknown = {f.prefix for f in report.unknown}
    assert "e4:5f:01" in unknown        # present in catalogue, absent from this registry
    assert not report.clean


def test_vendor_name_aliases_are_accepted():
    """"HP" in the catalogue and "Hewlett Packard" at IEEE are the same vendor."""
    assert verify._agrees("HP", "Hewlett Packard")
    assert verify._agrees("Apple", "Apple, Inc.")
    assert verify._agrees("TP-Link", "TP-LINK TECHNOLOGIES CO.,LTD.")
    assert verify._agrees("Raspberry Pi Foundation / Ltd", "Raspberry Pi Trading Ltd")
    assert verify._agrees("Espressif", "Espressif Inc.")
    assert not verify._agrees("Apple", "Samsung Electronics")


def test_clean_report_when_everything_agrees():
    report = verify.Report(checked=5, matched=5)
    assert report.clean
