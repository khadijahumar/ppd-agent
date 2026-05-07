"""Shared banner / framed-card output for the ``ppd`` CLI.

The visual style is meant to evoke Hermes / Gemini / Claude CLIs:

* Big ASCII word-mark for "PPD-AGENT" rendered in yellow.
* A short tagline + version line under the word-mark.
* A yellow-bordered framed card showing structural info (paths, counts,
  next steps) when the caller wants it.

We deliberately stick to plain 7-bit ASCII for the box-drawing and status
icons. The ``install.ps1`` companion has the same constraint (Windows
PowerShell 5.1 + ``iwr -useb`` mangles non-ASCII bytes), and keeping the
runtime CLI consistent means a user who installs through the ASCII
installer won't suddenly get garbled glyphs from ``ppd doctor`` if their
terminal happens to be on a legacy code page.
"""
from __future__ import annotations

from typing import Iterable

import click

try:
    from importlib.metadata import version as _pkg_version
except ImportError:  # pragma: no cover -- Python < 3.8
    _pkg_version = None  # type: ignore[assignment]


TAGLINE = "Production / Planning / Design"


def app_version() -> str:
    """Return the installed package version, or ``'?.?.?'`` if unknown."""
    if _pkg_version is None:
        return "?.?.?"
    try:
        return _pkg_version("ppd-agent")
    except Exception:  # noqa: BLE001
        return "?.?.?"


# figlet "big" font for "PPD-AGENT", split exactly at column 22 of the
# raw figlet output: left half is the "PPD" wordmark (22 cols), right
# half is "-AGENT" (41 cols). Two leading spaces of indent. Pure ASCII
# so the runtime CLI looks the same regardless of console code page.
_BANNER_LEFT = (
    "   _____  _____  _____  ",
    "  |  __ \\|  __ \\|  __ \\ ",
    "  | |__) | |__) | |  | |",
    "  |  ___/|  ___/| |  | |",
    "  | |    | |    | |__| |",
    "  |_|    |_|    |_____/ ",
)
_BANNER_RIGHT = (
    "              _____ ______ _   _ _______ ",
    "        /\\   / ____|  ____| \\ | |__   __|",
    "______ /  \\ | |  __| |__  |  \\| |  | |   ",
    "______/ /\\ \\| | |_ |  __| | . ` |  | |   ",
    "     / ____ \\ |__| | |____| |\\  |  | |   ",
    "    /_/    \\_\\_____|______|_| \\_|  |_|   ",
)


def print_banner() -> None:
    """Render the big PPD-AGENT word-mark + tagline + version."""
    click.echo()
    for left, right in zip(_BANNER_LEFT, _BANNER_RIGHT):
        click.secho(left, fg="bright_yellow", nl=False)
        click.secho(right, fg="yellow")
    click.echo()
    click.secho(
        f"  {TAGLINE}   --   v{app_version()}",
        fg="bright_black",
    )
    click.echo()


def print_card(lines: Iterable[str], width: int = 64) -> None:
    """Render a yellow-bordered framed card with the given body lines."""
    body = list(lines)
    top = "  +" + ("-" * width) + "+"
    bot = "  +" + ("-" * width) + "+"
    click.secho(top, fg="yellow")
    for line in body:
        pad = max(width - _visible_len(line), 0)
        click.secho("  |", fg="yellow", nl=False)
        click.echo(line + (" " * pad), nl=False)
        click.secho("|", fg="yellow")
    click.secho(bot, fg="yellow")


def _visible_len(s: str) -> int:
    """Length of ``s`` ignoring ANSI escape codes."""
    out = 0
    in_esc = False
    for ch in s:
        if in_esc:
            if ch == "m":
                in_esc = False
            continue
        if ch == "\x1b":
            in_esc = True
            continue
        out += 1
    return out


def print_step(msg: str) -> None:
    click.secho(f"  >> {msg}", fg="cyan")


def print_ok(msg: str) -> None:
    click.secho(f"  [+] {msg}", fg="green")


def print_warn(msg: str) -> None:
    click.secho(f"  [!] {msg}", fg="yellow")


def print_fail(msg: str) -> None:
    click.secho(f"  [x] {msg}", fg="red")


def print_info(msg: str) -> None:
    click.secho(f"      {msg}", fg="bright_black")
