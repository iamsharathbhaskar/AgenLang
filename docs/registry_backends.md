# AgenLang Registry Backends

The AgenLang Agent Registry supports multiple storage backends for different deployment scenarios.

## Available Backends

### SQLite (Default)
Best for: Development, testing, single-node deployments

```python
from agenlang import AgentRegistry

# Default SQLite in ~/.agenlang/registry.db
registry = AgentRegistry()

# Custom SQLite path
from pathlib import Path
registry = AgentRegistry(db_path=Path("/data/registry.db"))

# Via DATABASE_URL
import os
os.environ["DATABASE_URL"] = "sqlite:///data/registry.db"
registry = AgentRegistry()
```

### PostgreSQL (Production)
Best for: Production, multi-node deployments, high availability

```python
import os
from agenlang import AgentRegistry

# Set PostgreSQL connection
os.environ["DATABASE_URL"] = "postgresql://user:password@localhost:5432/agenlang"

# Create registry
registry = AgentRegistry()
```

## Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `postgresql://user:pass@host/db` |
| `AGENLANG_KEY_DIR` | Directory for SQLite and keys | `~/.agenlang` |

### Connection String Formats

**SQLite:**
- `sqlite:///absolute/path/to/db.db`
- `sqlite://relative/path.db`

**PostgreSQL:**
- `postgresql://user:password@host:port/database`
- `postgresql://user:password@host/database?sslmode=require`

## Backend Factory

Create backends programmatically:

```python
from agenlang.backends import create_backend

# SQLite
sqlite_backend = create_backend("sqlite:///tmp/registry.db")

# PostgreSQL
postgres_backend = create_backend("postgresql://user:pass@localhost/db")

# From environment
backend = create_backend()  # Uses DATABASE_URL or defaults to SQLite
```

## PostgreSQL Schema

The PostgreSQL backend creates the following tables:

- **agents** - Agent registration records
- **executions** - Contract execution history
- **interactions** - Agent interaction records for reputation
- **reputation_history** - Historical reputation changes

Indexes are automatically created for:
- Agent capabilities (GIN index on JSONB)
- Agent reputation scores
- Execution lookup by issuer/receiver
- Interaction timestamps

## Async Usage

For async contexts, use the backend directly:

```python
from agenlang.backends import create_backend

async def main():
    backend = create_backend("postgresql://user:pass@localhost/db")
    await backend.init_schema()

    agent = await backend.register_agent(
        did_key="did:key:z123",
        pubkey_pem="...",
        endpoint_url="http://localhost:8000",
        capabilities=["net:read"],
    )

    await backend.close()
```

## Installation

**SQLite:**
No additional dependencies (included in Python standard library).

**PostgreSQL:**
```bash
pip install agenlang[postgres]
# or
pip install asyncpg
```

## Migration from SQLite to PostgreSQL

1. Export SQLite data:
```python
import json
from agenlang import AgentRegistry

sqlite_registry = AgentRegistry(db_path="old.db")
agents = sqlite_registry.list_agents()

# Save to file
with open("agents_export.json", "w") as f:
    json.dump([a.to_dict() for a in agents], f)
```

2. Import to PostgreSQL:
```python
import json
import os
from agenlang import AgentRegistry

os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
registry = AgentRegistry()

with open("agents_export.json") as f:
    for agent_data in json.load(f):
        registry.register_agent(**{k: v for k, v in agent_data.items()
                                    if k not in ["reputation_score", "created_at", "last_seen"]})
```

## Testing

Run backend tests:
```bash
# All backend tests
pytest tests/test_backends.py -v

# With PostgreSQL (requires running PG instance)
DATABASE_URL="postgresql://test:test@localhost/testdb" pytest tests/test_backends.py -v
```
