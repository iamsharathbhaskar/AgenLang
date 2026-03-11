"""Economy module - Joule-based metering and Signed Execution Records."""

import asyncio
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import aiosqlite
from pydantic import BaseModel, Field


DIVERGENCE_TOLERANCE = float(os.environ.get("JOULE_DIVERGENCE_TOLERANCE", "0.05"))


DEFAULT_WEIGHTS = {
    "w1_prompt": 1.0,
    "w2_completion": 3.0,
    "w3_compute_sec": 10.0,
}


class JouleMeter:
    """JouleMeter as context manager and decorator for tracking compute usage."""

    def __init__(self, weights: Optional[dict] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._prompt_tokens: int = 0
        self._completion_tokens: int = 0
        self._compute_seconds: float = 0.0
        self._start_time: Optional[float] = None
        self._prompt_text: str = ""
        self._completion_text: str = ""
        self._tokenizer_name: str = "cl100k_base"
        self._tokenizer = None

    def _get_tokenizer(self):
        """Lazy-load tiktoken tokenizer."""
        if self._tokenizer is None:
            try:
                import tiktoken

                self._tokenizer = tiktoken.get_encoding(self._tokenizer_name)
            except Exception:
                self._tokenizer = None
        return self._tokenizer

    @contextmanager
    def measure(self):
        """Context manager for measuring compute."""
        import time

        self._start_time = time.monotonic()
        try:
            yield self
        finally:
            if self._start_time is not None:
                self._compute_seconds = time.monotonic() - self._start_time
                self._start_time = None

    def __enter__(self):
        """Enter context manager."""
        import time

        self._start_time = time.monotonic()
        return self

    def __exit__(self, *args):
        """Exit context manager."""
        import time

        if self._start_time is not None:
            self._compute_seconds = time.monotonic() - self._start_time
            self._start_time = None

    def count_prompt_tokens(self, text: str, tokenizer_name: str = "cl100k_base") -> int:
        """Count prompt tokens using tiktoken."""
        self._prompt_text = text
        self._tokenizer_name = tokenizer_name

        tokenizer = self._get_tokenizer()
        if tokenizer:
            self._prompt_tokens = len(tokenizer.encode(text))
        else:
            self._prompt_tokens = len(text) // 4

        return self._prompt_tokens

    def count_completion_tokens(self, text: str, tokenizer_name: str = "cl100k_base") -> int:
        """Count completion tokens using tiktoken."""
        self._completion_text = text
        self._tokenizer_name = tokenizer_name

        tokenizer = self._get_tokenizer()
        if tokenizer:
            self._completion_tokens = len(tokenizer.encode(text))
        else:
            self._completion_tokens = len(text) // 4

        return self._completion_tokens

    def calculate_joules(self) -> float:
        """Calculate Joules using weighted formula."""
        w1 = self.weights.get("w1_prompt", 1.0)
        w2 = self.weights.get("w2_completion", 3.0)
        w3 = self.weights.get("w3_compute_sec", 10.0)
        return (
            (self._prompt_tokens * w1)
            + (self._completion_tokens * w2)
            + (self._compute_seconds * w3)
        )

    def get_breakdown(self) -> dict:
        """Get detailed breakdown of Joule calculation."""
        return {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "compute_seconds": round(self._compute_seconds, 3),
            "weights": self.weights,
            "tokenizer": self._tokenizer_name,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._compute_seconds = 0.0
        self._prompt_text = ""
        self._completion_text = ""
        self._start_time = None


def compute_hash(data: str) -> str:
    """Compute SHA256 hash of data."""
    return f"sha256:{hashlib.sha256(data.encode('utf-8')).hexdigest()}"


class SignedExecutionRecord(BaseModel):
    """Cryptographically signed execution record."""

    ser_id: str
    contract_id: str
    provider_did: str
    consumer_did: str
    joules: float
    pricing: dict
    breakdown: dict
    prompt_hash: str
    completion_hash: str
    execution_id: str
    signature: str = ""
    tokenizer: str = "cl100k_base"
    created_at: str = Field(
        default_factory=lambda: (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
    )

    @classmethod
    def create(
        cls,
        contract_id: str,
        provider_did: str,
        consumer_did: str,
        joules: float,
        pricing: dict,
        breakdown: dict,
        prompt_text: str,
        completion_text: str,
    ) -> "SignedExecutionRecord":
        """Create a new SER with hashes."""
        return cls(
            ser_id=f"ser_{uuid.uuid4().hex[:24]}",
            contract_id=contract_id,
            provider_did=provider_did,
            consumer_did=consumer_did,
            joules=joules,
            pricing=pricing,
            breakdown=breakdown,
            prompt_hash=compute_hash(prompt_text),
            completion_hash=compute_hash(completion_text),
            execution_id=f"exec_{uuid.uuid4().hex[:24]}",
        )


class JouleLedger:
    """Internal double-entry ledger for Joule settlements with atomic operations."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path.home() / ".agenlang" / "ledger.db")
        self._reservations: dict[str, float] = {}

    async def init_db(self) -> None:
        """Initialize the ledger database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS joule_reservations (
                    contract_id TEXT PRIMARY KEY,
                    joules REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS joule_settlements (
                    ser_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    joules REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def reserve(self, contract_id: str, joules: float) -> None:
        """Reserve Joules for a task (PENDING state)."""
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO joule_reservations (contract_id, joules, status, created_at, updated_at)
                VALUES (?, ?, 'PENDING', ?, ?)
                """,
                (contract_id, joules, now, now),
            )
            await db.commit()

        self._reservations[contract_id] = joules

    async def settle(self, contract_id: str, ser: SignedExecutionRecord) -> bool:
        """Atomically settle on COMPLETED state. Returns True if successful."""
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status FROM joule_reservations WHERE contract_id = ?",
                (contract_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if row is None or row[0] != "PENDING":
                return False

            await db.execute(
                """
                UPDATE joule_reservations SET status = 'SETTLED', updated_at = ?
                WHERE contract_id = ?
                """,
                (now, contract_id),
            )

            await db.execute(
                """
                INSERT INTO joule_settlements (ser_id, contract_id, joules, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (ser.ser_id, contract_id, ser.joules, now),
            )

            await db.commit()

        if contract_id in self._reservations:
            del self._reservations[contract_id]

        return True

    async def revert(self, contract_id: str) -> bool:
        """Revert a PENDING reservation. Returns True if reverted."""
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status FROM joule_reservations WHERE contract_id = ?",
                (contract_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if row is None or row[0] != "PENDING":
                return False

            await db.execute(
                """
                UPDATE joule_reservations SET status = 'REVERTED', updated_at = ?
                WHERE contract_id = ?
                """,
                (now, contract_id),
            )
            await db.commit()

        if contract_id in self._reservations:
            del self._reservations[contract_id]

        return True

    async def get_reservation(self, contract_id: str) -> Optional[dict]:
        """Get reservation details."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT contract_id, joules, status, created_at FROM joule_reservations WHERE contract_id = ?",
                (contract_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "contract_id": row[0],
                        "joules": row[1],
                        "status": row[2],
                        "created_at": row[3],
                    }
        return None


class JouleGarbageCollector:
    """Background task to revert stale PENDING reservations."""

    def __init__(self, ledger: JouleLedger, stale_timeout_minutes: int = 30):
        self.ledger = ledger
        self.stale_timeout_minutes = stale_timeout_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the GC background task."""
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the GC background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main GC loop."""
        while self._running:
            try:
                await asyncio.sleep(60)
                await self._collect()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _collect(self) -> int:
        """Revert stale PENDING reservations. Returns count of reverted."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.stale_timeout_minutes)
        cutoff_str = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        reverted_count = 0

        async with aiosqlite.connect(self.ledger.db_path) as db:
            async with db.execute(
                "SELECT contract_id FROM joule_reservations WHERE status = 'PENDING' AND created_at < ?",
                (cutoff_str,),
            ) as cursor:
                rows = await cursor.fetchall()

            for row in rows:
                contract_id = row[0]
                if await self.ledger.revert(contract_id):
                    reverted_count += 1

        return reverted_count


def validate_token_divergence(
    expected_tokens: int,
    actual_tokens: int,
    tolerance: float = DIVERGENCE_TOLERANCE,
) -> bool:
    """Validate token count divergence within tolerance."""
    if expected_tokens == 0:
        return actual_tokens == 0

    divergence = abs(actual_tokens - expected_tokens) / expected_tokens
    return divergence <= tolerance
