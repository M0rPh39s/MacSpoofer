"""Command-line behaviour, exit codes and the interactive wizard."""

from __future__ import annotations

import pytest

from macspoofer import cli
from macspoofer.command import CommandResult
from tests.test_spoof import FakeHost


@pytest.fixture
def cli_host(monkeypatch):
    """A simulated Mac with root, wired into every module the CLI touches."""

    def _make(**kwargs):
        fake = FakeHost(**kwargs)
        monkeypatch.setattr("sys.platform", "darwin")
        monkeypatch.setattr("macspoofer.interfaces.run", fake.run)
        monkeypatch.setattr("macspoofer.spoof.run", fake.run)
        monkeypatch.setattr("macspoofer.spoof.is_root", lambda: True)
        return fake

    return _make


@pytest.fixture
def answers(monkeypatch):
    """Script the interactive prompts."""

    def _make(values):
        queue = list(values)

        def fake_ask(prompt, *args, **kwargs):
            if not queue:
                raise EOFError
            return queue.pop(0)

        monkeypatch.setattr("macspoofer.cli.Prompt.ask", staticmethod(fake_ask))
        return queue

    return _make


# --- parser ---------------------------------------------------------------

def test_version_and_help_exit_cleanly():
    for flag in ("--version", "--help"):
        with pytest.raises(SystemExit) as exc:
            cli.main([flag])
        assert exc.value.code == 0


def test_no_banner_accepted_on_either_side_of_the_subcommand(capsys):
    assert cli.main(["--no-banner", "devices", "-s", "nintendo"]) == cli.EXIT_OK
    before = capsys.readouterr()
    assert cli.main(["devices", "-s", "nintendo", "--no-banner"]) == cli.EXIT_OK
    after = capsys.readouterr()
    assert "Nintendo Switch" in before.out and "Nintendo Switch" in after.out
    # Suppressed either way: the banner only goes to stderr.
    assert "__  __" not in before.err and "__  __" not in after.err


def test_banner_is_printed_by_default(capsys):
    cli.main(["devices", "-s", "nintendo"])
    assert "Created by M0rPh39s" in capsys.readouterr().err


# --- devices --------------------------------------------------------------

def test_devices_lists_the_whole_catalogue(capsys):
    assert cli.main(["devices", "--no-banner"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Smartphones" in out and "Raspberry Pi" in out and "profiles in" in out


def test_devices_by_category(capsys):
    assert cli.main(["devices", "-c", "camera", "--no-banner"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Hikvision" in out and "Raspberry Pi" not in out


def test_devices_unknown_category_is_a_usage_error(capsys):
    assert cli.main(["devices", "-c", "nope", "--no-banner"]) == cli.EXIT_USAGE
    assert "Unknown category" in capsys.readouterr().out


def test_devices_search_with_no_match(capsys):
    assert cli.main(["devices", "-s", "zzzz", "--no-banner"]) == cli.EXIT_ERROR
    assert "No device matches" in capsys.readouterr().out


# --- interfaces / status --------------------------------------------------

def test_interfaces_lists_the_host(cli_host, capsys):
    cli_host()
    assert cli.main(["interfaces", "--no-banner"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "en0" in out and "fc:b2:14:6e:3c:ea" in out


def test_status_reports_no_records_initially(cli_host, capsys):
    cli_host()
    assert cli.main(["status", "--no-banner"]) == cli.EXIT_OK
    assert "has not changed any interface" in capsys.readouterr().out


def test_status_lists_recorded_originals(cli_host, capsys):
    cli_host()
    cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "-y", "--no-banner"])
    capsys.readouterr()
    assert cli.main(["status", "--no-banner"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "a0:ce:c8:11:22:33" in out and "restore --all" in out


# --- set ------------------------------------------------------------------

def test_set_requires_exactly_one_source(capsys):
    assert cli.main(["set", "-i", "en0", "--no-banner"]) == cli.EXIT_USAGE
    assert cli.main(
        ["set", "-i", "en0", "-d", "raspberry-pi", "-m", "aa:bb:cc:dd:ee:ff", "--no-banner"]
    ) == cli.EXIT_USAGE
    assert "exactly one" in capsys.readouterr().out


def test_set_applies_a_device_profile(cli_host, capsys):
    fake = cli_host()
    assert cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "-y", "--no-banner"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Raspberry Pi" in out and "Address changed" in out
    assert fake.current["en5"].startswith(("b8:27:eb", "dc:a6:32", "e4:5f:01", "28:cd:c1",
                                           "2c:cf:67", "d8:3a:dd"))


def test_set_with_pinned_oui(cli_host, capsys):
    fake = cli_host()
    cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "--oui", "b8:27:eb", "-y", "--no-banner"])
    assert fake.current["en5"].startswith("b8:27:eb:")


def test_set_explicit_mac(cli_host):
    fake = cli_host()
    cli.main(["set", "-i", "en5", "-m", "AA-BB-CC-11-22-33", "-y", "--no-banner"])
    assert fake.current["en5"] == "aa:bb:cc:11:22:33"


def test_set_random_is_locally_administered(cli_host):
    from macspoofer import oui

    fake = cli_host()
    cli.main(["set", "-i", "en5", "--random", "-y", "--no-banner"])
    assert oui.is_local(fake.current["en5"])


def test_set_rejects_an_invalid_mac(capsys):
    assert cli.main(["set", "-i", "en0", "-m", "ff:ff:ff:ff:ff:ff", "--no-banner"]) == cli.EXIT_USAGE
    assert "broadcast" in capsys.readouterr().out


def test_set_unknown_interface(cli_host, capsys):
    cli_host()
    assert cli.main(
        ["set", "-i", "wlan99", "-d", "raspberry-pi", "-y", "--no-banner"]
    ) == cli.EXIT_USAGE
    assert "No such interface" in capsys.readouterr().out


def test_set_asks_before_changing_and_honours_no(cli_host, answers, capsys):
    fake = cli_host()
    answers(["n"])
    assert cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "--no-banner"]) == cli.EXIT_ABORT
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert "Nothing was changed" in capsys.readouterr().out


def test_set_dry_run_needs_no_confirmation_and_changes_nothing(cli_host, capsys):
    fake = cli_host()
    assert cli.main(
        ["set", "-i", "en5", "-d", "raspberry-pi", "--dry-run", "--no-banner"]
    ) == cli.EXIT_OK
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert "Dry run" in capsys.readouterr().out


def test_set_failure_returns_an_error_code(cli_host, capsys):
    cli_host(accept=False)
    assert cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "-y", "--no-banner"]) == cli.EXIT_ERROR
    assert "Failed" in capsys.readouterr().out


# --- restore --------------------------------------------------------------

def test_restore_needs_a_target(capsys):
    assert cli.main(["restore", "--no-banner"]) == cli.EXIT_USAGE
    assert "--interface or --all" in capsys.readouterr().out


def test_restore_one_interface(cli_host, capsys):
    fake = cli_host()
    cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "-y", "--no-banner"])
    capsys.readouterr()
    assert cli.main(["restore", "-i", "en5", "--no-banner"]) == cli.EXIT_OK
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"


def test_restore_all_with_nothing_recorded(cli_host, capsys):
    cli_host()
    assert cli.main(["restore", "--all", "--no-banner"]) == cli.EXIT_OK
    assert "No interface has a recorded original" in capsys.readouterr().out


def test_restore_all(cli_host, capsys):
    fake = cli_host()
    cli.main(["set", "-i", "en5", "-d", "raspberry-pi", "-y", "--no-banner"])
    cli.main(["set", "-i", "en0", "-d", "apple-iphone", "-y", "--no-banner"])
    capsys.readouterr()
    assert cli.main(["restore", "--all", "--no-banner"]) == cli.EXIT_OK
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"
    assert fake.current["en0"] == "fc:b2:14:6e:3c:ea"


# --- wizard ---------------------------------------------------------------

def test_wizard_quits_without_changing_anything(cli_host, answers, capsys):
    fake = cli_host()
    answers(["q"])
    assert cli.main([]) == cli.EXIT_ABORT
    out = capsys.readouterr().out
    assert "Created by M0rPh39s" in out      # the banner greets on start
    assert "Step 1 of 3" in out
    assert fake.current["en5"] == "a0:ce:c8:11:22:33"


def test_wizard_full_path_applies_the_choice(cli_host, answers, capsys):
    fake = cli_host()
    # interface 2 (en5) -> category "sbc" -> Raspberry Pi -> apply
    categories = [c.key for c in __import__("macspoofer.profiles", fromlist=["x"]).CATEGORIES]
    sbc = str(categories.index("sbc") + 1)
    answers(["2", sbc, "1", "a"])
    assert cli.main([]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Proposed change" in out and "Address changed" in out
    assert fake.current["en5"].startswith(("b8:27:eb", "dc:a6:32", "e4:5f:01", "28:cd:c1",
                                           "2c:cf:67", "d8:3a:dd"))


def test_wizard_back_navigation(cli_host, answers, capsys):
    cli_host()
    # Go forward, step back twice, then quit -- the interface prompt must return.
    answers(["2", "1", "b", "b", "q"])
    assert cli.main([]) == cli.EXIT_ABORT
    assert capsys.readouterr().out.count("Step 1 of 3") == 2


def test_wizard_regenerate_gives_a_different_address(cli_host, answers, capsys):
    cli_host()
    categories = [c.key for c in __import__("macspoofer.profiles", fromlist=["x"]).CATEGORIES]
    answers(["2", str(categories.index("sbc") + 1), "5", "r", "r", "q"])
    assert cli.main([]) == cli.EXIT_ABORT
    out = capsys.readouterr().out
    assert out.count("Proposed change") == 3


def test_wizard_rejects_out_of_range_then_accepts(cli_host, answers, capsys):
    cli_host()
    answers(["99", "0", "abc", "q"])
    assert cli.main([]) == cli.EXIT_ABORT
    assert "Enter a number from 1 to" in capsys.readouterr().out


def test_wizard_custom_mac(cli_host, answers, capsys):
    fake = cli_host()
    categories = [c.key for c in __import__("macspoofer.profiles", fromlist=["x"]).CATEGORIES]
    generic = str(categories.index("generic") + 1)
    # generic -> "Enter a specific MAC" is the 3rd entry -> bad input, then good
    answers([ "2", generic, "3", "ff:ff:ff:ff:ff:ff", "AA-BB-CC-11-22-33", "a"])
    assert cli.main([]) == cli.EXIT_OK
    assert fake.current["en5"] == "aa:bb:cc:11:22:33"
    assert "broadcast" in capsys.readouterr().out


def test_wizard_reports_no_interfaces(monkeypatch, capsys):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        "macspoofer.interfaces.run",
        lambda argv, **kw: CommandResult(tuple(argv), 0, "", ""),
    )
    assert cli.main([]) == cli.EXIT_ABORT
    assert "No Ethernet or Wi-Fi interface was found" in capsys.readouterr().out


def test_wizard_refuses_unsupported_platform(monkeypatch, capsys):
    monkeypatch.setattr("sys.platform", "win32")
    assert cli.main([]) == cli.EXIT_ERROR
    assert "Unsupported platform" in capsys.readouterr().out


def test_wizard_without_root_explains_how_to_rerun(cli_host, answers, capsys, monkeypatch):
    cli_host()
    monkeypatch.setattr("macspoofer.spoof.is_root", lambda: False)
    categories = [c.key for c in __import__("macspoofer.profiles", fromlist=["x"]).CATEGORIES]
    answers(["2", str(categories.index("sbc") + 1), "1", "a"])
    assert cli.main([]) == cli.EXIT_ERROR
    out = capsys.readouterr().out
    assert "requires root" in out and "sudo" in out
