"""AgenLang CLI — simple command-line interface."""

import os
import sys
from pathlib import Path
from typing import Optional

import click
import structlog

from .contract import Contract
from .keys import KeyManager
from .runtime import Runtime
from .cli_template import template_group


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


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to listen on")
@click.option("--key-path", type=click.Path(), help="Path to key file")
@click.option("--production/--dev", default=True, help="Run in production mode with observability")
@click.option("--data-dir", type=click.Path(), help="Data directory for persistence")
@click.option("--workers", default=1, type=int, help="Number of uvicorn workers (production only)")
@click.option("--log-level", default="info", type=click.Choice(["debug", "info", "warning", "error"]), help="Log level")
@click.option("--ssl-certfile", type=click.Path(), help="Path to SSL certificate (production only)")
@click.option("--ssl-keyfile", type=click.Path(), help="Path to SSL key (production only)")
@click.option("--cors-preset", default="a2a", type=click.Choice(["permissive", "restrictive", "a2a"]), help="CORS preset")
def server(
    host: str,
    port: int,
    key_path: Optional[str],
    production: bool,
    data_dir: Optional[str],
    workers: int,
    log_level: str,
    ssl_certfile: Optional[str],
    ssl_keyfile: Optional[str],
    cors_preset: str,
) -> None:
    """Start the A2A server to receive contracts from other agents."""
    log = structlog.get_logger()
    log.info("starting_server", host=host, port=port, production=production)

    mode_str = "production" if production else "development"
    click.echo(f"Starting AgenLang A2A server ({mode_str} mode) on {host}:{port}")
    click.echo(f"Health check: http://{host}:{port}/health")
    click.echo(f"Agent discovery: http://{host}:{port}/.well-known/agent.json")
    click.echo(f"A2A endpoint: http://{host}:{port}/a2a")

    if production:
        click.echo(f"\n[Production Endpoints]")
        click.echo(f"  Metrics: http://{host}:{port}/metrics")
        click.echo(f"  Prometheus: http://{host}:{port}/metrics/prometheus")
        click.echo(f"  Circuit Breakers: http://{host}:{port}/circuit-breakers")
        click.echo(f"  Traces: http://{host}:{port}/traces")
        click.echo(f"\n[Production Features]")
        click.echo(f"  • Rate limiting: Enabled")
        click.echo(f"  • Distributed tracing: Enabled")
        click.echo(f"  • Structured logging: Enabled")
        click.echo(f"  • Circuit breakers: Enabled")

    click.echo("\nPress Ctrl+C to stop")

    try:
        if production:
            # Run production server with full observability
            from .server_production import ProductionServer, ProductionConfig

            config = ProductionConfig(
                host=host,
                port=port,
                key_path=key_path,
                data_dir=data_dir,
                workers=workers,
                log_level=log_level,
                ssl_certfile=ssl_certfile,
                ssl_keyfile=ssl_keyfile,
                cors_preset=cors_preset,
            )
            prod_server = ProductionServer(config)
            prod_server.start()
        else:
            # Run simple server
            from .server import run_server
            run_server(host=host, port=port, key_path=key_path)

    except KeyboardInterrupt:
        click.echo("\nShutting down...")
    except Exception as e:
        log.error("server_error", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def identity() -> None:
    """Show this agent's identity (DID:key and public key)."""
    log = structlog.get_logger()
    try:
        km = KeyManager()
        if not km.key_exists():
            click.echo("No key found. Generating new keypair...")
            km.generate()

        did = km.derive_did_key()
        pubkey = km.get_public_key_pem().decode("utf-8")

        click.echo("\nAgent Identity:")
        click.echo(f"DID: {did}")
        click.echo(f"\nPublic Key (PEM):")
        click.echo(pubkey)

    except Exception as e:
        log.error("identity_error", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("contract_path", type=click.Path(exists=True))
@click.option("--endpoint", default="http://localhost:8000/a2a", help="Target agent A2A endpoint")
@click.option("--sse", is_flag=True, help="Use SSE streaming for async execution")
def send(contract_path: str, endpoint: str, sse: bool) -> None:
    """Send a contract to another agent via A2A protocol.

    Args:
        contract_path: Path to the JSON contract file to send.
    """
    log = structlog.get_logger()
    try:
        contract = Contract.from_file(contract_path)

        # Sign the contract before sending
        km = KeyManager()
        if not km.key_exists():
            km.generate()
        contract.sign(km)

        log.info("sending_contract", contract_id=contract.contract_id, endpoint=endpoint)
        click.echo(f"Sending contract {contract.contract_id} to {endpoint}")

        if sse:
            from .a2a import dispatch_sse
            result = dispatch_sse(contract, endpoint_url=endpoint)
            click.echo("\nExecution complete!")
            click.echo(f"Output: {result.get('output', 'N/A')}")
        else:
            from .a2a import dispatch
            output = dispatch(contract, action="tool", target="execute", args={}, endpoint_url=endpoint)
            click.echo("\nExecution complete!")
            click.echo(f"Output: {output}")

    except Exception as e:
        log.error("send_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Registry commands
@main.group()
def registry() -> None:
    """Agent registry management commands."""
    pass


@registry.command("register")
@click.option("--did", required=True, help="Agent DID:key")
@click.option("--pubkey", required=True, help="Path to PEM public key file")
@click.option("--endpoint", required=True, help="A2A endpoint URL")
@click.option("--name", default="Unknown Agent", help="Agent name")
@click.option("--description", default="", help="Agent description")
@click.option("--capabilities", default="", help="Comma-separated capabilities (e.g., 'net:read,compute:write')")
@click.option("--rate", default=1.0, type=float, help="Joule rate (cost per Joule)")
def register_agent(
    did: str,
    pubkey: str,
    endpoint: str,
    name: str,
    description: str,
    capabilities: str,
    rate: float,
) -> None:
    """Register an agent in the local registry."""
    log = structlog.get_logger()
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()

        pubkey_pem = Path(pubkey).read_text()
        capabilities_list = [c.strip() for c in capabilities.split(",") if c.strip()]

        agent = registry_db.register_agent(
            did_key=did,
            pubkey_pem=pubkey_pem,
            endpoint_url=endpoint,
            capabilities=capabilities_list,
            name=name,
            description=description,
            joule_rate=rate,
        )

        click.echo(f"✓ Registered agent: {agent.name}")
        click.echo(f"  DID: {agent.did_key}")
        click.echo(f"  Endpoint: {agent.endpoint_url}")
        click.echo(f"  Capabilities: {', '.join(agent.capabilities)}")
        click.echo(f"  Reputation: {agent.reputation_score:.2f}")

    except Exception as e:
        log.error("register_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("list")
@click.option("--limit", default=20, help="Maximum agents to list")
def list_agents(limit: int) -> None:
    """List registered agents."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        agents = registry_db.list_agents(limit=limit)

        if not agents:
            click.echo("No agents registered.")
            return

        click.echo(f"\n{'Name':<20} {'DID':<50} {'Reputation':<12} {'Rate':<8}")
        click.echo("-" * 100)
        for agent in agents:
            name = agent.name[:18] + ".." if len(agent.name) > 20 else agent.name
            did = agent.did_key[:48] + ".." if len(agent.did_key) > 50 else agent.did_key
            click.echo(f"{name:<20} {did:<50} {agent.reputation_score:<12.2f} {agent.joule_rate:<8.2f}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("find")
@click.argument("capability")
@click.option("--min-reputation", default=0.0, type=float, help="Minimum reputation score")
def find_agents(capability: str, min_reputation: float) -> None:
    """Find agents by capability."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        agents = registry_db.find_agents_by_capability(capability, min_reputation)

        if not agents:
            click.echo(f"No agents found with capability: {capability}")
            return

        click.echo(f"\nFound {len(agents)} agent(s) with capability '{capability}':")
        click.echo(f"{'Name':<20} {'DID':<50} {'Reputation':<12} {'Endpoint':<30}")
        click.echo("-" * 120)
        for agent in agents:
            name = agent.name[:18] + ".." if len(agent.name) > 20 else agent.name
            did = agent.did_key[:48] + ".." if len(agent.did_key) > 50 else agent.did_key
            endpoint = agent.endpoint_url[:28] + ".." if len(agent.endpoint_url) > 30 else agent.endpoint_url
            click.echo(f"{name:<20} {did:<50} {agent.reputation_score:<12.2f} {endpoint:<30}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("show")
@click.argument("did")
def show_agent(did: str) -> None:
    """Show details of a specific agent."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        agent = registry_db.get_agent(did)

        if not agent:
            click.echo(f"Agent not found: {did}")
            sys.exit(1)

        click.echo(f"\nAgent: {agent.name}")
        click.echo(f"Description: {agent.description or 'N/A'}")
        click.echo(f"DID: {agent.did_key}")
        click.echo(f"Version: {agent.version}")
        click.echo(f"Endpoint: {agent.endpoint_url}")
        click.echo(f"Capabilities: {', '.join(agent.capabilities)}")
        click.echo(f"Reputation Score: {agent.reputation_score:.4f}")
        click.echo(f"Joule Rate: {agent.joule_rate}")
        click.echo(f"Registered: {agent.created_at}")
        click.echo(f"Last Seen: {agent.last_seen}")
        click.echo(f"Active: {'Yes' if agent.is_active else 'No'}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("stats")
def registry_stats() -> None:
    """Show registry statistics."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        stats = registry_db.get_stats()

        click.echo("\nRegistry Statistics:")
        click.echo(f"  Active Agents: {stats['active_agents']}")
        click.echo(f"  Total Executions: {stats['total_executions']}")
        click.echo(f"  Average Reputation: {stats['average_reputation']:.4f}")
        click.echo(f"  Total Joules Consumed: {stats['total_joules_consumed']:.4f}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("update-reputation")
@click.argument("did")
@click.argument("score", type=float)
def update_reputation(did: str, score: float) -> None:
    """Update an agent's reputation score (0.0-1.0)."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        registry_db.update_reputation(did, score)

        click.echo(f"✓ Updated reputation for {did} to {score:.4f}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@registry.command("history")
@click.argument("did")
@click.option("--as-executor", is_flag=True, help="Show as executor (receiver) instead of issuer")
@click.option("--limit", default=20, help="Maximum records")
def execution_history(did: str, as_executor: bool, limit: int) -> None:
    """Show execution history for an agent."""
    try:
        from .registry import AgentRegistry

        registry_db = AgentRegistry()
        history = registry_db.get_execution_history(did, as_issuer=not as_executor, limit=limit)

        if not history:
            role = "executor" if as_executor else "issuer"
            click.echo(f"No execution history found for {did} as {role}")
            return

        role = "Executor" if as_executor else "Issuer"
        click.echo(f"\nExecution History for {did} (as {role}):")
        click.echo(f"{'Execution ID':<40} {'Contract ID':<45} {'Status':<10} {'Joules':<10}")
        click.echo("-" * 110)
        for record in history:
            exec_id = record.execution_id[:38] + ".." if len(record.execution_id) > 40 else record.execution_id
            contract_id = record.contract_id[:43] + ".." if len(record.contract_id) > 45 else record.contract_id
            click.echo(f"{exec_id:<40} {contract_id:<45} {record.status:<10} {record.joules_used:<10.4f}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Register template commands
main.add_command(template_group)

# Configure logging when CLI module is loaded (for both script and installed entry point)
_configure_logging()

if __name__ == "__main__":
    main()
