"""Tests for the ``ppd`` CLI."""
from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from ppd_agent import cli as cli_mod


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["--version"])
    assert result.exit_code == 0
    assert "ppd" in result.output.lower()


def test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("init", "start", "prepare-data", "doctor", "config"):
        assert cmd in result.output


def test_init_non_interactive_creates_template(tmp_path: Path,
                                               monkeypatch) -> None:
    home = tmp_path / "ppd_home"
    monkeypatch.setenv("PPD_HOME", str(home))

    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["init", "--non-interactive"])

    assert result.exit_code == 0, result.output
    env_path = home / ".env"
    assert env_path.exists()
    body = env_path.read_text()
    assert "OPENROUTER_API_KEY=" in body
    assert "TELEGRAM_BOT_TOKEN=" in body
    assert "PPD_MODEL=anthropic/claude-sonnet-4" in body
    # subdirs created
    assert (home / "data" / "raw").is_dir()
    assert (home / "data" / "parquet").is_dir()


def test_config_set_and_get(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "ppd_home"
    monkeypatch.setenv("PPD_HOME", str(home))
    runner = CliRunner()
    runner.invoke(cli_mod.cli, ["init", "--non-interactive"])

    r1 = runner.invoke(cli_mod.cli, ["config", "set", "OPENROUTER_API_KEY", "sk-test"])
    assert r1.exit_code == 0

    r2 = runner.invoke(cli_mod.cli, ["config", "get", "OPENROUTER_API_KEY"])
    assert r2.exit_code == 0
    assert "sk-test" in r2.output


def test_config_show_masks_secrets(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "ppd_home"
    monkeypatch.setenv("PPD_HOME", str(home))
    runner = CliRunner()
    runner.invoke(cli_mod.cli, ["init", "--non-interactive"])
    runner.invoke(cli_mod.cli, ["config", "set", "OPENROUTER_API_KEY", "sk-or-v1-supersecret"])
    runner.invoke(cli_mod.cli, ["config", "set", "TELEGRAM_BOT_TOKEN", "12345:ABCxyz"])

    result = runner.invoke(cli_mod.cli, ["config", "show"])
    assert result.exit_code == 0
    # Real secret values must not appear verbatim.
    assert "supersecret" not in result.output
    # But keys should
    assert "OPENROUTER_API_KEY" in result.output
    assert "TELEGRAM_BOT_TOKEN" in result.output


def test_doctor_reports_missing_env(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "ppd_home"
    monkeypatch.setenv("PPD_HOME", str(home))
    runner = CliRunner()
    result = runner.invoke(cli_mod.cli, ["doctor"])
    assert result.exit_code == 0
    # No init yet -> home missing, .env missing
    assert "home dir missing" in result.output or "FAIL" in result.output


def test_doctor_after_init(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "ppd_home"
    monkeypatch.setenv("PPD_HOME", str(home))
    runner = CliRunner()
    runner.invoke(cli_mod.cli, ["init", "--non-interactive"])
    result = runner.invoke(cli_mod.cli, ["doctor"])
    assert result.exit_code == 0
    assert "home dir exists" in result.output
    assert ".env exists" in result.output
