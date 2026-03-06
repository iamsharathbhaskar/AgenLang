"""Registry backends for AgenLang.

Provides pluggable storage backends for the agent registry:
- SQLite: Default local file-based storage
- PostgreSQL: Production-ready with connection pooling

Configuration:
    DATABASE_URL environment variable controls the backend:
    - sqlite:///path/to/db.db -> SQLiteBackend
    - postgresql://user:pass@host/db -> PostgresBackend
"""

import os
from pathlib import Path
from typing import Optional

from .base import (
    AgentRecord,
    ExecutionRecord,
    InteractionRecord,
    RegistryBackend,
    SearchQuery,
)
from .sqlite import SQLiteBackend

__all__ = [
    "AgentRecord",
    "ExecutionRecord",
    "InteractionRecord",
    "RegistryBackend",
    "SearchQuery",
    "SQLiteBackend",
    "PostgresBackend",
    "create_backend",
    "get_backend_from_env",
]

# Optional import for PostgreSQL
try:
    from .postgres import PostgresBackend
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    PostgresBackend = None  # type: ignore


def create_backend(
    database_url: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> RegistryBackend:
    """Create a registry backend based on configuration.

    Args:
        database_url: Database connection string.
            - sqlite:///path/to/db.db for SQLite
            - postgresql://user:pass@host/db for PostgreSQL
            If not provided, uses DATABASE_URL env var or defaults to SQLite.
        db_path: Deprecated. Path to SQLite database (for backward compatibility).

    Returns:
        Configured RegistryBackend instance

    Raises:
        ValueError: If database_url is invalid
        ImportError: If PostgreSQL backend requested but asyncpg not installed

    Examples:
        >>> # SQLite (default)
        >>> backend = create_backend()
        >>>
        >>> # SQLite with explicit path
        >>> backend = create_backend("sqlite:///tmp/registry.db")
        >>>
        >>> # PostgreSQL
        >>> backend = create_backend("postgresql://user:pass@localhost/agenlang")
    """
    url = database_url or os.environ.get("DATABASE_URL", "")

    # Handle backward compatibility with db_path
    if db_path is not None and not url:
        return SQLiteBackend(db_path)

    # Default to SQLite if no URL provided
    if not url:
        return SQLiteBackend()

    # Parse URL scheme
    if url.startswith("sqlite://"):
        # Extract path from sqlite:///path or sqlite://path
        path = url[9:]  # Remove "sqlite://"
        if path.startswith("/"):
            path = path[1:]
        return SQLiteBackend(Path(path) if path else None)

    elif url.startswith("postgresql://") or url.startswith("postgres://"):
        if not POSTGRES_AVAILABLE:
            raise ImportError(
                "PostgreSQL backend requires asyncpg. "
                "Install with: pip install asyncpg"
            )
        return PostgresBackend(dsn=url)

    else:
        raise ValueError(
            f"Unsupported database URL scheme: {url}. "
            "Use sqlite:///path or postgresql://user:pass@host/db"
        )


def get_backend_from_env() -> RegistryBackend:
    """Create backend from DATABASE_URL environment variable.

    Returns:
        Configured RegistryBackend based on DATABASE_URL env var,
        or SQLiteBackend with default path if not set.
    """
    return create_backend()


# Backward compatibility aliases
__all__.extend([
    "SQLiteBackend",
])
