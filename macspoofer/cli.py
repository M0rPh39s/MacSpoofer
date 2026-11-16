"""Command-line interface: an interactive wizard plus scriptable subcommands.

Running ``macspoofer`` with no arguments starts the wizard, which asks which
interface to change and which kind of device to impersonate. Every wizard
action has a flag-driven equivalent (``macspoofer set -i en0 -d raspberry-pi``)
so the same tool can be used from a script.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from macspoofer import AUTHOR, REPO_URL, __version__
from macspoofer import interfaces as ifaces
from macspoofer import generator, oui, profiles, spoof, state
from macspoofer.banner import render_banner, render_footer
from macspoofer.generator import GenerationError
from macspoofer.interfaces import Interface
from macspoofer.profiles import CUSTOM_KEY, Category, DeviceProfile

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_ABORT = 130

NOTICE = (
    "Use only on networks and devices you own or are authorised to test."
)

_BACK = object()
_QUIT = object()

_KIND_STYLE = {
    ifaces.WIFI: "cyan",
    ifaces.ETHERNET: "green",
    ifaces.BRIDGE: "magenta",
    ifaces.TUNNEL: "dim",
    ifaces.LOOPBACK: "dim",
    ifaces.VIRTUAL: "dim",
    ifaces.OTHER: "dim",
}


# ---------------------------------------------------------------------------
# Shared rendering
# ---------------------------------------------------------------------------

def _interface_table(items: tuple[Interface, ...], *, numbered: bool = False) -> Table:
    table = Table(box=None, pad_edge=False, header_style="bold")
    if numbered:
        table.add_column("#", justify="right", style="bold cyan", width=3)
    table.add_column("Interface", style="bold")
    table.add_column("Type")
    table.add_column("Current address")
    table.add_column("Hardware address", style="dim")
    table.add_column("State")
    for index, iface in enumerate(items, start=1):
        current = Text(iface.display_mac)
        if iface.mac is None:
            current.stylize("dim italic")
        elif iface.spoofed:
            current.stylize("yellow")
        state_bits = []
        if iface.spoofed:
            state_bits.append("[yellow]spoofed[/yellow]")
        if iface.locally_administered:
            state_bits.append("[cyan]local[/cyan]")
        state_bits.append(
            f"[green]{iface.status}[/green]" if iface.status in ("active", "up")
            else f"[dim]{iface.status}[/dim]"
        )
        row = [
            iface.name,
            f"[{_KIND_STYLE.get(iface.kind, 'dim')}]{iface.kind}[/]",
            current,
            iface.permanent or "-",
            " ".join(state_bits),
        ]
        if numbered:
            row.insert(0, str(index))
        table.add_row(*row)
    return table


def _profile_table(items: tuple[DeviceProfile, ...], *, numbered: bool = False) -> Table:
    table = Table(box=None, pad_edge=False, header_style="bold")
    if numbered:
        table.add_column("#", justify="right", style="bold cyan", width=3)
    table.add_column("Device", style="bold")
    table.add_column("Vendor")
    table.add_column("Key", style="dim")
    table.add_column("OUIs", justify="right", style="dim")
    for index, profile in enumerate(items, start=1):
        count = str(len(profile.ouis)) if profile.ouis else "-"
        row = [profile.label, profile.vendor, profile.key, count]
        if numbered:
            row.insert(0, str(index))
        table.add_row(*row)
    return table


def _category_table(numbered: bool = True) -> Table:
    table = Table(box=None, pad_edge=False, header_style="bold")
    if numbered:
        table.add_column("#", justify="right", style="bold cyan", width=3)
    table.add_column("Category", style="bold")
    table.add_column("Devices", justify="right", style="dim")
    table.add_column("Description")
    for index, category in enumerate(profiles.CATEGORIES, start=1):
        row = [category.label, str(len(category.profiles)), category.description]
        if numbered:
            row.insert(0, str(index))
        table.add_row(*row)
    return table


def _restriction_hint(console: Console) -> None:
    if ifaces.reads_restricted() and not spoof.is_root():
        console.print(
            "[dim]macOS is hiding current addresses from this process; "
            "re-run under sudo to see and verify them.[/dim]\n"
        )


def _render_result(console: Console, result: spoof.SpoofResult) -> None:
    """Print the outcome of an apply or restore."""
    if result.status == "ok":
        style, heading = "green", "Address changed"
    elif result.status == "dry-run":
        style, heading = "cyan", "Dry run"
    elif result.status == "unverified":
        style, heading = "yellow", "Applied, unverified"
    else:
        style, heading = "red", "Failed"

    body = Text()
    body.append(f"Interface:  {result.interface}\n")
    body.append(f"Before:     {result.before or 'unknown'}\n")
    body.append("After:      ")
    body.append(f"{result.after or 'unknown'}\n", style="bold")
    body.append(f"Requested:  {result.requested}\n\n")
    body.append(result.message)
    console.print(Panel(body, title=heading, border_style=style, title_align="left"))

    if result.steps:
        console.print("[dim]Commands run:[/dim]")
        for step in result.steps:
            mark = "[green]ok[/green] " if step.ok else "[red]x [/red]"
            if result.dry_run:
                mark = "[cyan]> [/cyan]"
            console.print(f"  {mark} [dim]{step.display}[/dim]")
        console.print()


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def _ask(console: Console, prompt: str, count: int, *, allow_back: bool) -> object:
    """Ask for a 1..count choice. Returns an int index, _BACK or _QUIT."""
    extras = "[cyan]q[/cyan] quit"
    if allow_back:
        extras = "[cyan]b[/cyan] back, " + extras
    while True:
        try:
            raw = Prompt.ask(f"{prompt} [dim]({extras})[/dim]", console=console).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return _QUIT
        if raw in ("q", "quit", "exit"):
            return _QUIT
        if allow_back and raw in ("b", "back"):
            return _BACK
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw) - 1
        console.print(f"[red]Enter a number from 1 to {count}.[/red]")


def _choose_interface(console: Console) -> object:
    items = ifaces.list_interfaces()
    if not items:
        console.print(
            "[red]No Ethernet or Wi-Fi interface was found.[/red] "
            "Run [bold]macspoofer interfaces --all[/bold] to see everything detected.\n"
        )
        return _QUIT
    console.print("[bold]Step 1 of 3 -- choose an interface[/bold]\n")
    console.print(_interface_table(items, numbered=True))
    console.print()
    choice = _ask(console, "Interface", len(items), allow_back=False)
    return items[choice] if isinstance(choice, int) else choice


def _choose_category(console: Console) -> object:
    console.print("\n[bold]Step 2 of 3 -- what do you want to impersonate?[/bold]\n")
    console.print(_category_table())
    console.print()
    choice = _ask(console, "Category", len(profiles.CATEGORIES), allow_back=True)
    return profiles.CATEGORIES[choice] if isinstance(choice, int) else choice


def _choose_profile(console: Console, category: Category) -> object:
    console.print(f"\n[bold]Step 3 of 3 -- {category.label}[/bold]")
    console.print(f"[dim]{category.description}[/dim]\n")
    console.print(_profile_table(category.profiles, numbered=True))
    console.print()
    choice = _ask(console, "Device", len(category.profiles), allow_back=True)
    return category.profiles[choice] if isinstance(choice, int) else choice


def _ask_custom_mac(console: Console) -> str | None:
    while True:
        try:
            raw = Prompt.ask("MAC address [dim](or q to go back)[/dim]", console=console).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None
        if raw.lower() in ("q", "b", "back", ""):
            return None
        problem = oui.assignable_error(raw)
        if problem is None:
            return oui.normalise(raw)
        console.print(f"[red]{problem}[/red]")


def _preview(console: Console, iface: Interface, gen: generator.Generated) -> None:
    body = Text()
    body.append("Interface:   ")
    body.append(f"{iface.label}\n", style="bold")
    body.append(f"Current:     {iface.display_mac}\n")
    body.append("New address: ")
    body.append(f"{gen.mac}\n", style="bold green")
    body.append(f"Appears as:  {gen.profile.label}")
    if gen.vendor not in ("none", "custom"):
        body.append(f" ({gen.vendor})")
    body.append("\n")
    body.append(f"Scope:       {gen.scope}\n")
    body.append(f"\n{gen.explanation}")
    if gen.profile.notes:
        body.append(f"\n\n{gen.profile.notes}", style="dim")
    console.print()
    console.print(Panel(body, title="Proposed change", border_style="cyan", title_align="left"))


def run_wizard(console: Console, *, dry_run: bool = False) -> int:
    """The interactive flow shown when MacSpoofer is started with no arguments."""
    render_banner(console)
    console.print(f"[dim]{NOTICE}[/dim]\n")

    if not ifaces.supported_platform():
        console.print(f"[red]Unsupported platform: {sys.platform}.[/red] macOS and Linux only.\n")
        return EXIT_ERROR
    _restriction_hint(console)

    stage = "interface"
    iface: Interface | None = None
    category: Category | None = None

    while True:
        if stage == "interface":
            picked = _choose_interface(console)
            if picked is _QUIT:
                console.print("[dim]Nothing was changed.[/dim]\n")
                return EXIT_ABORT
            iface = picked  # type: ignore[assignment]
            stage = "category"
            continue

        if stage == "category":
            picked = _choose_category(console)
            if picked is _QUIT:
                console.print("[dim]Nothing was changed.[/dim]\n")
                return EXIT_ABORT
            if picked is _BACK:
                stage = "interface"
                continue
            category = picked  # type: ignore[assignment]
            stage = "profile"
            continue

        if stage == "profile":
            assert category is not None and iface is not None
            picked = _choose_profile(console, category)
            if picked is _QUIT:
                console.print("[dim]Nothing was changed.[/dim]\n")
                return EXIT_ABORT
            if picked is _BACK:
                stage = "category"
                continue
            profile: DeviceProfile = picked  # type: ignore[assignment]

            custom_mac = None
            if profile.key == CUSTOM_KEY:
                console.print(f"\n[dim]{profile.notes}[/dim]")
                custom_mac = _ask_custom_mac(console)
                if custom_mac is None:
                    continue
            try:
                gen = generator.generate(profile, custom_mac=custom_mac)
            except GenerationError as exc:
                console.print(f"[red]{exc}[/red]")
                continue

            # Preview, with the option to redraw the random part.
            while True:
                _preview(console, iface, gen)
                console.print(
                    "\n[cyan]a[/cyan] apply    "
                    "[cyan]r[/cyan] regenerate    "
                    "[cyan]b[/cyan] back    "
                    "[cyan]q[/cyan] quit"
                )
                try:
                    action = Prompt.ask("Action", console=console, default="a").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    action = "q"
                if action in ("q", "quit"):
                    console.print("[dim]Nothing was changed.[/dim]\n")
                    return EXIT_ABORT
                if action in ("b", "back"):
                    break
                if action in ("r", "regen", "regenerate"):
                    if profile.key == CUSTOM_KEY:
                        console.print("[dim]A custom address has nothing to regenerate.[/dim]")
                        continue
                    gen = generator.generate(profile, custom_mac=custom_mac)
                    continue
                if action in ("a", "apply", "y", "yes", ""):
                    return _apply_and_report(console, iface.name, gen.mac, dry_run=dry_run)
                console.print("[red]Choose a, r, b or q.[/red]")
            continue

    return EXIT_OK  # pragma: no cover - unreachable


def _apply_and_report(console: Console, name: str, mac: str, *, dry_run: bool) -> int:
    if not dry_run and not spoof.is_root():
        console.print(
            f"\n[red]Changing a hardware address requires root.[/red]\n"
            f"Re-run as: [bold]{spoof.root_hint()}[/bold]\n"
        )
        return EXIT_ERROR
    console.print()
    result = spoof.apply_mac(name, mac, dry_run=dry_run)
    _render_result(console, result)
    if result.ok and not dry_run:
        console.print(
            f"[dim]Undo with:[/dim] [bold]sudo macspoofer restore -i {name}[/bold]\n"
        )
    return EXIT_OK if result.ok else EXIT_ERROR


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_interfaces(args: argparse.Namespace, console: Console) -> int:
    items = ifaces.list_interfaces(include_all=args.all)
    if not items:
        console.print("[yellow]No interfaces found.[/yellow]")
        return EXIT_ERROR
    _restriction_hint(console)
    console.print(_interface_table(items))
    return EXIT_OK


def cmd_devices(args: argparse.Namespace, console: Console) -> int:
    if args.search:
        found = profiles.search(args.search)
        if not found:
            console.print(f"[yellow]No device matches {args.search!r}.[/yellow]")
            return EXIT_ERROR
        console.print(_profile_table(found))
        return EXIT_OK

    if args.category:
        category = profiles.category_by_key(args.category)
        if category is None:
            keys = ", ".join(c.key for c in profiles.CATEGORIES)
            console.print(f"[red]Unknown category {args.category!r}.[/red] Choose from: {keys}")
            return EXIT_USAGE
        console.print(f"[bold]{category.label}[/bold] [dim]-- {category.description}[/dim]\n")
        console.print(_profile_table(category.profiles))
        return EXIT_OK

    for category in profiles.CATEGORIES:
        console.print(f"\n[bold cyan]{category.label}[/bold cyan] [dim]({category.key})[/dim]")
        console.print(f"[dim]{category.description}[/dim]")
        console.print(_profile_table(category.profiles))
    total = len(profiles.all_profiles())
    console.print(
        f"\n[dim]{total} profiles in {len(profiles.CATEGORIES)} categories, "
        f"{len({o for o, _ in profiles.all_ouis()})} unique OUI prefixes.[/dim]"
    )
    return EXIT_OK


def cmd_set(args: argparse.Namespace, console: Console) -> int:
    chosen = [bool(args.device), bool(args.mac), bool(args.random)]
    if sum(chosen) != 1:
        console.print("[red]Choose exactly one of --device, --mac or --random.[/red]")
        return EXIT_USAGE

    try:
        if args.mac:
            gen = generator.generate_for_key(CUSTOM_KEY, custom_mac=args.mac)
        elif args.random:
            gen = generator.generate_for_key(profiles.RANDOM_LOCAL_KEY)
        else:
            gen = generator.generate_for_key(args.device, prefix=args.oui)
    except (GenerationError, oui.MacError) as exc:
        console.print(f"[red]{exc}[/red]")
        return EXIT_USAGE

    iface = ifaces.get_interface(args.interface)
    if iface is None:
        console.print(f"[red]No such interface: {args.interface}[/red]")
        return EXIT_USAGE

    _preview(console, iface, gen)
    if not args.yes and not args.dry_run:
        try:
            answer = Prompt.ask("\nApply?", choices=["y", "n"], default="n", console=console)
        except (EOFError, KeyboardInterrupt):
            console.print()
            answer = "n"
        if answer != "y":
            console.print("[dim]Nothing was changed.[/dim]")
            return EXIT_ABORT
    return _apply_and_report(console, args.interface, gen.mac, dry_run=args.dry_run)


def cmd_restore(args: argparse.Namespace, console: Console) -> int:
    if args.all:
        targets = sorted(state.load())
        if not targets:
            console.print("[yellow]No interface has a recorded original address.[/yellow]")
            return EXIT_OK
    elif args.interface:
        targets = [args.interface]
    else:
        console.print("[red]Give --interface or --all.[/red]")
        return EXIT_USAGE

    if not args.dry_run and not spoof.is_root():
        console.print(
            f"[red]Restoring a hardware address requires root.[/red]\n"
            f"Re-run as: [bold]{spoof.root_hint()}[/bold]"
        )
        return EXIT_ERROR

    failures = 0
    for name in targets:
        result = spoof.restore_mac(name, dry_run=args.dry_run)
        _render_result(console, result)
        failures += 0 if result.ok else 1
    return EXIT_OK if not failures else EXIT_ERROR


def cmd_status(args: argparse.Namespace, console: Console) -> int:
    items = ifaces.list_interfaces(include_all=args.all)
    _restriction_hint(console)
    console.print("[bold]Interfaces[/bold]\n")
    console.print(_interface_table(items))

    records = state.load()
    console.print("\n[bold]Recorded originals[/bold]\n")
    if not records:
        console.print("[dim]None. MacSpoofer has not changed any interface on this system.[/dim]")
        return EXIT_OK
    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("Interface", style="bold")
    table.add_column("Original address")
    table.add_column("Source", style="dim")
    table.add_column("Recorded", style="dim")
    for name in sorted(records):
        record = records[name]
        table.add_row(name, record.original, record.source, record.recorded_iso)
    console.print(table)
    console.print(
        "\n[dim]Restore everything with:[/dim] [bold]sudo macspoofer restore --all[/bold]"
    )
    return EXIT_OK


def cmd_verify_oui(args: argparse.Namespace, console: Console) -> int:
    """Check the bundled catalogue against the official IEEE registry."""
    from macspoofer.verify import VerifyError, load_registry, verify_catalogue

    try:
        registry = load_registry(csv_path=args.csv, download=args.download)
    except VerifyError as exc:
        console.print(f"[red]{exc}[/red]")
        return EXIT_ERROR

    report = verify_catalogue(registry)
    console.print(
        f"[bold]Checked {report.checked} prefixes[/bold] against "
        f"{len(registry)} IEEE assignments\n"
    )
    console.print(f"  [green]{report.matched} match the expected vendor[/green]")
    if report.local:
        console.print(
            f"  [cyan]{len(report.local)} locally administered, so absent from the "
            f"registry by design[/cyan]"
        )
    if report.mismatched:
        console.print(f"  [yellow]{len(report.mismatched)} registered to someone else[/yellow]")
    if report.unknown:
        console.print(f"  [red]{len(report.unknown)} not in the registry[/red]")

    if report.mismatched:
        table = Table(box=None, pad_edge=False, header_style="bold", title_justify="left")
        table.add_column("OUI")
        table.add_column("Profile", style="dim")
        table.add_column("Catalogue says")
        table.add_column("IEEE says", style="yellow")
        for item in report.mismatched:
            table.add_row(item.prefix, item.profile_key, item.expected, item.actual)
        console.print("\n[bold yellow]Vendor mismatches[/bold yellow]\n")
        console.print(table)
    if report.unknown:
        console.print("\n[bold red]Not in the IEEE registry[/bold red]\n")
        for item in report.unknown:
            console.print(f"  {item.prefix}  [dim]{item.profile_key}[/dim]")
    return EXIT_OK if not (report.mismatched or report.unknown) else EXIT_ERROR


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macspoofer",
        description="Change an interface's MAC address to impersonate a chosen class "
        "of device. Run with no arguments for the interactive wizard.",
        epilog="Run 'macspoofer <command> --help' for command-specific options.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"macspoofer {__version__}\nCreated by {AUTHOR} · {REPO_URL}",
    )
    parser.add_argument(
        "--no-banner", action="store_true", help="suppress the ASCII banner"
    )

    # Repeated on every subcommand so it is accepted either before or after it.
    # SUPPRESS keeps the subparser copy from overwriting a value already given
    # at the top level with its own default.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-banner",
        action="store_true",
        default=argparse.SUPPRESS,
        help="suppress the ASCII banner",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_if = sub.add_parser("interfaces", parents=[common], help="list network interfaces")
    p_if.add_argument("--all", action="store_true", help="include virtual and loopback interfaces")
    p_if.set_defaults(func=cmd_interfaces)

    p_dev = sub.add_parser("devices", parents=[common], help="list the device profile catalogue")
    p_dev.add_argument("--category", "-c", help="show one category only")
    p_dev.add_argument("--search", "-s", help="filter by name or vendor")
    p_dev.set_defaults(func=cmd_devices)

    p_set = sub.add_parser("set", parents=[common], help="change an interface's address")
    p_set.add_argument("--interface", "-i", required=True, help="interface to change")
    p_set.add_argument("--device", "-d", help="device profile key (see 'devices')")
    p_set.add_argument("--mac", "-m", help="an explicit MAC address")
    p_set.add_argument(
        "--random", action="store_true", help="a random locally administered address"
    )
    p_set.add_argument("--oui", help="pin the OUI prefix instead of choosing at random")
    p_set.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p_set.add_argument("--dry-run", action="store_true", help="show the commands, change nothing")
    p_set.set_defaults(func=cmd_set)

    p_res = sub.add_parser("restore", parents=[common], help="restore an interface's original address")
    p_res.add_argument("--interface", "-i", help="interface to restore")
    p_res.add_argument("--all", action="store_true", help="restore every recorded interface")
    p_res.add_argument("--dry-run", action="store_true", help="show the commands, change nothing")
    p_res.set_defaults(func=cmd_restore)

    p_st = sub.add_parser("status", parents=[common], help="show interfaces and recorded originals")
    p_st.add_argument("--all", action="store_true", help="include virtual and loopback interfaces")
    p_st.set_defaults(func=cmd_status)

    p_ver = sub.add_parser("verify-oui", parents=[common], help="check the catalogue against the IEEE registry")
    p_ver.add_argument("--csv", help="path to a local copy of the IEEE oui.csv")
    p_ver.add_argument(
        "--download", action="store_true", help="fetch oui.csv from standards-oui.ieee.org"
    )
    p_ver.set_defaults(func=cmd_verify_oui)

    p_wiz = sub.add_parser("wizard", parents=[common], help="the interactive wizard (the default)")
    p_wiz.add_argument("--dry-run", action="store_true", help="show the commands, change nothing")
    p_wiz.set_defaults(func=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if args.command in (None, "wizard"):
        try:
            return run_wizard(console, dry_run=getattr(args, "dry_run", False))
        except KeyboardInterrupt:  # pragma: no cover - interactive
            console.print("\n[dim]Interrupted. Nothing was changed.[/dim]")
            return EXIT_ABORT

    try:
        code = args.func(args, console)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        console.print("\n[dim]Interrupted.[/dim]")
        return EXIT_ABORT

    if not getattr(args, "no_banner", False):
        render_footer(Console(stderr=True))
    return code
