"""CLI module - Command-line interface for AgenLang."""

import asyncio
import json
import sys
from pathlib import Path

from agenlang import Identity, AgentClient, discover_agent, __version__


def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_help()
        return 1

    command = sys.argv[1]

    if command == "version":
        print(f"agenlang {__version__}")
        return 0
    elif command == "identity":
        return cmd_identity()
    elif command == "call":
        return asyncio.run(cmd_call())
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


def cmd_identity() -> int:
    """Show or create identity."""
    agent_id = sys.argv[2] if len(sys.argv) > 2 else "default"

    print(f"Loading identity for agent: {agent_id}")

    try:
        identity = Identity.load(agent_id)
        print(f"DID: {identity.did}")
        print(f"Key path: {identity._key_path}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


async def cmd_call() -> int:
    """Call another agent."""
    if len(sys.argv) < 4:
        print("Usage: agenlang call <to-did> <action> [payload]")
        return 1

    to_did = sys.argv[2]
    action = sys.argv[3]
    payload = {}

    if len(sys.argv) > 4:
        import json

        try:
            payload = json.loads(sys.argv[4])
        except json.JSONDecodeError:
            payload = {"text": sys.argv[4]}

    try:
        identity = Identity.load("default")
        client = AgentClient(did=identity.did, identity=identity)

        print(f"Calling {to_did} with action '{action}'...")

        result = await client.request(to=to_did, action=action, payload=payload)

        print(json.dumps(result, indent=2, default=str))
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


async def cmd_discover() -> int:
    """Discover agents on network."""
    if len(sys.argv) < 3:
        print("Usage: agenlang discover <agent-url>")
        return 1

    agent_url = sys.argv[2]

    print(f"Discovering agent at {agent_url}...")

    try:
        card = await discover_agent(agent_url)
        if card:
            print(json.dumps(card, indent=2))
        else:
            print("No agent card found")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_inspect(trace_id: str | None) -> int:
    """Inspect a trace."""
    if not trace_id:
        print("Usage: agenlang inspect <trace-id>")
        return 1

    print(f"Trace ID: {trace_id}")
    print("(Requires database access - not implemented in this version)")
    return 0


def print_help():
    """Print help message."""
    print(f"""AgenLang CLI - A semantics layer on top of A2A v{__version__}

Usage:
    agenlang <command> [options]

Commands:
    identity [agent-id]  Show or create agent identity
    call <to-did> <action> [payload]  Call another agent
    discover <url>       Discover agent by URL
    inspect <trace-id>  Inspect a trace
    version              Show version

Examples:
    agenlang identity
    agenlang call did:key:z6Mk... summarize '{{"text": "hello"}}'
    agenlang discover https://agent.example.com
""")


if __name__ == "__main__":
    sys.exit(main())
