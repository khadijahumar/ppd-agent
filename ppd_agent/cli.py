"""``ppd`` command-line interface.

Subcommands:

    ppd init           Interactive wizard \u2014 writes ~/.ppd/.env
    ppd prepare-data   Convert xlsx \u2192 parquet (run after dropping data files)
    ppd start          Start the Telegram bot (long-polling, foreground)
    ppd doctor         Diagnose the install (paths, env, dependencies, network)
    ppd config get KEY
    ppd config set KEY VALUE
    ppd config show
    ppd version

All paths default to ``$PPD_HOME`` (defaults to ``~/.ppd`` on a fresh install,
or to the repo root when running from a clone with a ``data/`` folder).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import click

# NOTE: we import ppd_agent.config lazily inside commands. Importing it at
# module load time would trigger ``CONFIG.ensure_dirs()`` and resolve paths
# before the user has had a chance to set ``PPD_HOME``.

# ``.env`` schema (key, default, description, secret?, multi?)
ENV_SCHEMA: list[dict] = [
    {
        "key": "OPENROUTER_API_KEY",
        "prompt": "OpenRouter API key (https://openrouter.ai/keys)",
        "default": "",
        "secret": True,
        "required": True,
    },
    {
        "key": "PPD_MODEL",
        "prompt": "OpenRouter model",
        "default": "anthropic/claude-sonnet-4",
        "secret": False,
        "required": False,
        "hint": "examples: anthropic/claude-sonnet-4, openai/gpt-4o, openai/gpt-4o-mini, google/gemini-2.0-flash-001",
    },
    {
        "key": "TELEGRAM_BOT_TOKEN",
        "prompt": "Telegram bot token (from @BotFather)",
        "default": "",
        "secret": True,
        "required": True,
    },
    {
        "key": "TELEGRAM_ALLOWED_USER_IDS",
        "prompt": "Comma-separated Telegram user IDs allowed to chat the bot",
        "default": "",
        "secret": False,
        "required": False,
        "hint": "get your ID from @userinfobot, e.g. 123456789,987654321",
    },
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _home() -> Path:
    """Resolve PPD_HOME the same way ``ppd_agent.config`` does."""
    env = os.getenv("PPD_HOME")
    if env:
        return Path(env).expanduser()
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / "data").is_dir():
        return repo_root
    return Path.home() / ".ppd"


def _env_path() -> Path:
    return _home() / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a tiny KEY=VALUE .env file. No interpolation, no quoting tricks."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_env_file(path: Path, values: dict[str, str], comment_header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if comment_header:
        for line in comment_header.strip().splitlines():
            lines.append(f"# {line}")
        lines.append("")
    for k, v in values.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # On POSIX, restrict permissions; harmless no-op on Windows.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _ok(msg: str) -> None:
    click.secho(f"  OK    {msg}", fg="green")


def _warn(msg: str) -> None:
    click.secho(f"  WARN  {msg}", fg="yellow")


def _err(msg: str) -> None:
    click.secho(f"  FAIL  {msg}", fg="red")


def _info(msg: str) -> None:
    click.echo(f"  ..    {msg}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group(
    name="ppd",
    help=(
        "PPD Assistant - AI agent for steel manufacturing.\n"
        "\n"
        "Run 'ppd init' once to configure credentials, drop your xlsx files "
        "into ~/.ppd/data/raw/, run 'ppd prepare-data', then 'ppd start'."
    ),
)
@click.version_option(package_name="ppd-agent", message="%(prog)s %(version)s")
def cli() -> None:
    pass


# -- init --------------------------------------------------------------------


@cli.command()
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Don't prompt; only create the home directory and template .env if missing.",
)
def init(non_interactive: bool) -> None:
    """Interactive setup wizard. Writes ``$PPD_HOME/.env``."""
    home = _home()
    env_path = _env_path()
    home.mkdir(parents=True, exist_ok=True)
    (home / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (home / "data" / "parquet").mkdir(parents=True, exist_ok=True)
    (home / "data" / "plots").mkdir(parents=True, exist_ok=True)

    click.echo(f"PPD home : {home}")
    click.echo(f"Env file : {env_path}")
    click.echo()

    existing = _read_env_file(env_path)
    if existing and not non_interactive:
        if not click.confirm(
            f".env already exists with {len(existing)} key(s). Edit it?",
            default=True,
        ):
            click.echo("Nothing changed.")
            return

    if non_interactive:
        # Only ensure a template exists; never prompt.
        if not env_path.is_file():
            template = {entry["key"]: entry["default"] for entry in ENV_SCHEMA}
            _write_env_file(
                env_path,
                template,
                comment_header=(
                    "PPD Assistant configuration.\n"
                    "Edit values below or run 'ppd init' to use the wizard.\n"
                    "Run 'ppd doctor' to verify the setup."
                ),
            )
            click.echo(f"Wrote template to {env_path}.")
        else:
            click.echo("Existing .env left untouched (non-interactive).")
        return

    values: dict[str, str] = dict(existing)
    for entry in ENV_SCHEMA:
        key: str = entry["key"]
        prompt: str = entry["prompt"]
        default: str = values.get(key) or entry.get("default", "")
        if entry.get("hint"):
            click.echo(f"  ({entry['hint']})")
        if entry.get("secret") and default:
            shown_default = "*" * 8
        else:
            shown_default = default
        new_val = click.prompt(
            prompt,
            default=shown_default,
            show_default=True,
            hide_input=bool(entry.get("secret") and not default),
        )
        # If user just hit enter and the default was masked, keep the existing value.
        if entry.get("secret") and new_val == "*" * 8:
            new_val = default
        values[key] = new_val.strip()

    _write_env_file(
        env_path,
        values,
        comment_header=(
            "PPD Assistant configuration.\n"
            "Generated by 'ppd init'. Edit by hand or re-run 'ppd init'.\n"
            "Run 'ppd doctor' to verify the setup."
        ),
    )
    click.echo()
    click.echo(f"Saved {env_path}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Drop your 8 .xlsx files into  {home / 'data' / 'raw'}")
    click.echo("  2. Run:  ppd prepare-data")
    click.echo("  3. Run:  ppd start")


# -- prepare-data ------------------------------------------------------------


@cli.command("prepare-data")
@click.option(
    "--from-dir",
    "from_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Optionally copy xlsx files from this folder into $PPD_HOME/data/raw/ first.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-convert even if parquet output already exists (default behaviour anyway).",
)
def prepare_data(from_dir: Path | None, force: bool) -> None:
    """Convert raw .xlsx files in ``$PPD_HOME/data/raw/`` to parquet."""
    # Ensure the package config picks up our home dir.
    os.environ.setdefault("PPD_HOME", str(_home()))
    from ppd_agent.config import CONFIG  # noqa: WPS433 (deferred import on purpose)
    from scripts.prepare_data import main as run_prepare

    if from_dir is not None:
        click.echo(f"Copying *.xls* from {from_dir} -> {CONFIG.raw_dir}")
        n = 0
        for src in list(from_dir.glob("*.xls")) + list(from_dir.glob("*.xlsx")):
            dst = CONFIG.raw_dir / src.name
            shutil.copy2(src, dst)
            click.echo(f"  copied {src.name}")
            n += 1
        click.echo(f"Done. {n} file(s) staged.")
        if n == 0:
            _warn("no xlsx files found in source directory")

    click.echo(f"Raw dir    : {CONFIG.raw_dir}")
    click.echo(f"Parquet dir: {CONFIG.parquet_dir}")
    click.echo()
    rc = run_prepare()
    sys.exit(rc)


# -- start -------------------------------------------------------------------


@cli.command()
def start() -> None:
    """Start the Telegram bot (long-polling, foreground)."""
    os.environ.setdefault("PPD_HOME", str(_home()))
    # Lazy import: pulls in telegram + agent modules.
    from ppd_agent.telegram_bot import run

    run()


# -- doctor ------------------------------------------------------------------


@cli.command()
def doctor() -> None:
    """Check the installation: paths, env, deps, parquet data."""
    home = _home()
    env_path = _env_path()
    click.echo("=== PPD doctor ===")
    click.echo(f"PPD home : {home}")
    click.echo(f"Env file : {env_path}")
    click.echo()

    if home.is_dir():
        _ok(f"home dir exists: {home}")
    else:
        _err(f"home dir missing: {home}  -> run 'ppd init'")

    if env_path.is_file():
        env_data = _read_env_file(env_path)
        _ok(f".env exists ({len(env_data)} keys)")
        required = {"OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN"}
        for key in required:
            if env_data.get(key):
                _ok(f"  {key}: set")
            else:
                _err(f"  {key}: missing  -> run 'ppd config set {key} <value>' or 'ppd init'")
        if not env_data.get("TELEGRAM_ALLOWED_USER_IDS"):
            _warn("  TELEGRAM_ALLOWED_USER_IDS empty: nobody is whitelisted")
    else:
        _err(f".env missing  -> run 'ppd init'")

    raw_dir = home / "data" / "raw"
    parquet_dir = home / "data" / "parquet"

    expected_xlsx = [
        "FT_CT_Design.xlsx", "HR_Chem_Std.xlsx", "HR_Elongation_Std.xlsx",
        "HR_Mech_Std.xlsx", "HR_Thick_Toler.xlsx", "Z001.xlsx",
        "Chemical_Design.xls", "Produksi_2021_HRC.xlsx",
    ]
    missing_raw = [f for f in expected_xlsx if not (raw_dir / f).exists()]
    if not missing_raw:
        _ok(f"raw xlsx complete ({len(expected_xlsx)} files in {raw_dir})")
    else:
        _warn(f"raw xlsx incomplete: missing {len(missing_raw)} file(s) in {raw_dir}")
        for name in missing_raw:
            click.echo(f"           - {name}")

    parquet_files = sorted(parquet_dir.glob("*.parquet")) if parquet_dir.is_dir() else []
    if parquet_files:
        _ok(f"parquet files: {len(parquet_files)} in {parquet_dir}")
    else:
        _warn(f"no parquet files in {parquet_dir}  -> run 'ppd prepare-data'")

    # Dependency probes
    try:
        import openai  # noqa: F401
        _ok("dep: openai")
    except ImportError:
        _err("dep: openai missing")
    try:
        import telegram  # noqa: F401
        _ok("dep: python-telegram-bot")
    except ImportError:
        _err("dep: python-telegram-bot missing")
    try:
        import pandas  # noqa: F401
        _ok("dep: pandas")
    except ImportError:
        _err("dep: pandas missing")
    try:
        import pyarrow  # noqa: F401
        _ok("dep: pyarrow")
    except ImportError:
        _err("dep: pyarrow missing")

    click.echo()
    click.echo("Doctor finished.")


# -- config ------------------------------------------------------------------


@cli.group()
def config() -> None:
    """Get/set values in $PPD_HOME/.env."""


@config.command("show")
def config_show() -> None:
    """Print all keys in .env (secrets masked)."""
    env_path = _env_path()
    if not env_path.is_file():
        click.echo(f"(no .env at {env_path}; run 'ppd init')")
        return
    data = _read_env_file(env_path)
    secret_keys = {entry["key"] for entry in ENV_SCHEMA if entry.get("secret")}
    for k, v in data.items():
        if k in secret_keys and v:
            shown = v[:4] + "*" * (max(len(v) - 8, 0)) + v[-4:] if len(v) > 8 else "*" * len(v)
            click.echo(f"{k}={shown}")
        else:
            click.echo(f"{k}={v}")


@config.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Print the value for KEY."""
    data = _read_env_file(_env_path())
    if key not in data:
        click.echo("(unset)")
        sys.exit(1)
    click.echo(data[key])


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set KEY=VALUE in .env (creates the file if needed)."""
    env_path = _env_path()
    data = _read_env_file(env_path)
    data[key] = value
    _write_env_file(env_path, data, comment_header="PPD Assistant configuration.")
    click.echo(f"Set {key} in {env_path}")


# -- entry point -------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
