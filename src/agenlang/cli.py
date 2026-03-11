"""CLI module - Command-line interface for AgenLang."""

import asyncio
import json
import sys
from pathlib import Path

from agenlang import Database, Identity, __version__
from agenlang.core import BaseAgent


def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_help()
        return 1

    command = sys.argv[1]

    if command == "version":
        print(f"agenlang {__version__}")
        return 0
    elif command == "start":
        return asyncio.run(cmd_start())
    elif command == "discover":
        return asyncio.run(cmd_discover())
    elif command == "inspect":
        return cmd_inspect(sys.argv[2] if len(sys.argv) > 2 else None)
    elif command in ("--help", "-h", "help"):
        print_help()
        return 0
    else:
        print(f"Unknown command: {command}")
        print_help()
        return 1


async def cmd_start() -> int:
    """Start an agent with configuration."""
    agent_id = "default"

    print(f"Starting AgenLang agent: {agent_id}")

    try:
        identity = Identity.load(agent_id)
        print(f"Agent DID: {identity.did}")

        db = Database(agent_id)
        await db.connect()
        print(f"Database: {db.db_path}")

        class SimpleAgent(BaseAgent):
            async def on_message(self, message):
                print(f"Received: {message}")

            async def on_request(self, message):
                print(f"Request: {message}")
                return {"status": "ok"}

            async def on_propose(self, message):
                print(f"Proposal: {message}")
                return {"status": "accepted"}

            async def on_inform(self, message):
                print(f"Inform: {message}")

        agent = SimpleAgent(agent_id=agent_id, db=db)
        await agent.initialize()
        await agent.start()

        print(f"Agent running at: {identity.did}")
        print("Press Ctrl+C to stop")

        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("\nStopping agent...")
            await agent.stop()

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


async def cmd_discover() -> int:
    """Discover agents on local network."""
    print("Discovering agents on local network...")

    try:
        from zeroconf import Zeroconf, ServiceBrowser
        from asyncio import Event

        found = []
        event = Event()

        def on_service_found(zeroconf, service_type, name, state_change):
            info = zeroconf.get_service_info(service_type, name)
            if info:
                addresses = []
                for addr in info.addresses:
                    addresses.append(".".join(str(b) for b in addr))
                found.append(
                    {
                        "name": name,
                        "addresses": addresses,
                        "port": info.port,
                    }
                )

        zc = Zeroconf()
        browser = ServiceBrowser(zc, "_agenlang._tcp.local.", handlers=[on_service_found])

        await asyncio.sleep(3)

        if found:
            print(json.dumps(found, indent=2))
        else:
            print("No agents found on local network")

        zc.close()
        return 0

    except ImportError:
        print("Error: zeroconf not installed")
        print("Install with: pip install zeroconf")
        return 1
    except Exception as e:
        print(f"Discovery error: {e}")
        return 1


def cmd_inspect(trace_id: str | None) -> int:
    """Inspect a contract chain by trace_id."""
    if not trace_id:
        print("Error: trace_id required")
        print("Usage: agenlang inspect <trace_id>")
        return 1

    print(f"Inspecting trace: {trace_id}")
    print("(Trace inspection requires database access)")

    agent_id = "default"
    db = Database(agent_id)

    async def do_inspect():
        await db.connect()
        contract = await db.get_contract(trace_id)
        if contract:
            print(json.dumps(contract, indent=2, default=str))
        else:
            print(f"No contract found for trace_id: {trace_id}")
        await db.close()

    asyncio.run(do_inspect())
    return 0


def print_help():
    """Print help message."""
    print(f"""AgenLang CLI - Agent-to-Agent Communication Protocol v{__version__}

Usage:
    agenlang <command> [options]

Commands:
    start              Start an agent (default: 'default')
    discover           Discover agents on local network
    inspect <trace_id> Show contract chain for trace_id
    version            Show version

Examples:
    agenlang start
    agenlang discover
    agenlang inspect trace_abc123
""")


if __name__ == "__main__":
    sys.exit(main())
