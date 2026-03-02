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
