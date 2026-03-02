"""AgenLang CLI — simple command-line interface."""

import os
import sys
from pathlib import Path

import click
import structlog

from .contract import Contract
from .runtime import Runtime


def _configure_logging() -> None:
    """Configure structlog: JSON for prod, console for dev."""
    if os.environ.get("AGENLANG_JSON_LOGS", "").lower() in ("1", "true", "yes"):
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(),
            ]
        )


@click.group()
def main() -> None:
    """AgenLang — standardized contract substrate for agents."""
    pass


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
def run(contract_path: str) -> None:
    """Run an AgenLang contract.

    Args:
        contract_path: Path to a JSON contract file.
    """
    log = structlog.get_logger()
    try:
        contract = Contract.from_file(contract_path)
        runtime = Runtime(contract)
        result, ser = runtime.execute()

        log.info("execution_successful", goal=contract.goal, result=result["output"])
        click.echo("Execution successful!")
        click.echo(f"Goal: {contract.goal}")
        click.echo(f"Result: {result['output']}")
        click.echo("\nSER (audit trail):")
        click.echo(runtime.to_ser_json(ser))

        ser_path = f"{contract.contract_id}.ser.json"
        Path(ser_path).write_text(runtime.to_ser_json(ser))
        log.info("ser_saved", path=ser_path)
        click.echo(f"\nSER saved to {ser_path}")

    except Exception as e:
        log.error("execution_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Configure logging when CLI module is loaded (for both script and installed entry point)
_configure_logging()

if __name__ == "__main__":
    main()
