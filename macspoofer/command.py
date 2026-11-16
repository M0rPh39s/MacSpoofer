"""Thin, safe wrapper around external commands.

Every external call in MacSpoofer goes through :func:`run`. Commands are always
passed as argument lists -- never a shell string -- so an interface name or a
MAC can never be interpreted as shell syntax.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

__all__ = ["CommandResult", "run", "which", "have"]

DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True)
class CommandResult:
    """Outcome of one external command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    missing: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.missing

    @property
    def display(self) -> str:
        return " ".join(self.argv)

    @property
    def error_text(self) -> str:
        if self.missing:
            return f"{self.argv[0]}: command not found"
        if self.timed_out:
            return f"{self.display}: timed out"
        detail = (self.stderr or self.stdout).strip().splitlines()
        return f"{self.display}: exit {self.returncode}" + (f" -- {detail[0]}" if detail else "")


def which(name: str) -> str | None:
    """Return the resolved path of *name*, or None."""
    return shutil.which(name)


def have(name: str) -> bool:
    """Return True if *name* is on PATH."""
    return shutil.which(name) is not None


def run(argv: list[str] | tuple[str, ...], *, timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
    """Run *argv* and capture its output, never raising on failure."""
    argv = tuple(argv)
    if shutil.which(argv[0]) is None:
        return CommandResult(argv, 127, "", "", missing=True)
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, never shell
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(argv, -1, "", "", timed_out=True)
    except OSError as exc:  # pragma: no cover - defensive
        return CommandResult(argv, -1, "", str(exc))
    return CommandResult(argv, proc.returncode, proc.stdout or "", proc.stderr or "")
