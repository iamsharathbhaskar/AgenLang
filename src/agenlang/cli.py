"""AgenLang CLI — simple command-line interface."""

import sys
import json
from pathlib import Path
import click
from .contract import Contract
from .runtime import Runtime

@click.group()
def main():
    """AgenLang — standardized contract substrate for agents."""
    pass

@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
def run(contract_path):
    """Run an AgenLang contract."""
    try:
        contract = Contract.from_file(contract_path)
        runtime = Runtime(contract)
        result, ser = runtime.execute()

        print("✅ Execution successful!")
        print(f"Goal: {contract.goal}")
        print(f"Result: {result['output']}")
        print("\nSER (audit trail):")
        print(runtime.to_ser_json(ser))

        # Save SER
        Path(f"{contract.contract_id}.ser.json").write_text(runtime.to_ser_json(ser))
        print(f"\nSER saved to {contract.contract_id}.ser.json")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
