# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI."""

from pathlib import Path

from click.testing import CliRunner

from agenlang.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_cli_run_success(tmp_path: Path) -> None:
    """CLI run executes contract with mock tools."""
    from agenlang.keys import KeyManager

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    runner = CliRunner()
    env = {"AGENLANG_KEY_DIR": str(tmp_path)}
    contract_path = str(EXAMPLES / "amazo-flight-booking.json")
    result = runner.invoke(main, ["run", contract_path], env=env)
    assert result.exit_code == 0
    assert "Execution successful" in result.output


def test_cli_run_invalid_file(tmp_path: Path) -> None:
    """CLI run with invalid contract file errors out."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('{"invalid": true}')
    runner = CliRunner()
    result = runner.invoke(main, ["run", str(bad_file)])
    assert result.exit_code != 0


def test_cli_help() -> None:
    """CLI --help runs."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "AgenLang" in result.output


def test_cli_run_help() -> None:
    """CLI run --help."""
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "contract_path" in result.output.lower()
