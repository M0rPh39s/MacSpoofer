"""The MacSpoofer ASCII banner and credit line.

Rendered in the same FIGlet "Big" style as the author's other tools so the
suite looks consistent in a terminal.
"""

from __future__ import annotations

from rich.console import Console

from macspoofer import AUTHOR, REPO_URL, __version__

ASCII_ART = r"""
 __  __             _____                    __
|  \/  |           / ____|                  / _|
| \  / | __ _  ___| (___  _ __   ___   ___ | |_ ___ _ __
| |\/| |/ _` |/ __|\___ \| '_ \ / _ \ / _ \|  _/ _ \ '__|
| |  | | (_| | (__ ____) | |_) | (_) | (_) | ||  __/ |
|_|  |_|\__,_|\___|_____/| .__/ \___/ \___/|_| \___|_|
                         | |
                         |_|
"""

TAGLINE = "MAC address spoofing with real device profiles"


def render_banner(console: Console) -> None:
    """Print the ASCII banner, tagline and credit."""
    console.print(f"[cyan]{ASCII_ART}[/cyan]")
    console.print(f"[dim]{TAGLINE}[/dim]")
    console.print(f"[bold]Created by {AUTHOR}[/bold]  •  {REPO_URL}  •  v{__version__}\n")


def render_footer(console: Console) -> None:
    """Print the ASCII banner and credit after a command (mirrors vulnstack)."""
    console.print(f"[cyan]{ASCII_ART}[/cyan]")
    console.print(f"[bold]Created by {AUTHOR}[/bold]  •  {REPO_URL}")
