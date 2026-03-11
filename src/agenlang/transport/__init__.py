"""Transport module - Abstract async transport interface."""

import asyncio
import base64
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta

import fastapi
import httpx
import uvicorn
import yaml
import aiosqlite
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


class Transport(ABC):
    """Abstract async transport base class."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._running = False

    @abstractmethod
    async def send(self, url: str, message: dict) -> None:
        """Send a message to the given URL."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the transport."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the transport."""
        ...


class HTTPTransport(Transport):
    """HTTP transport implementation with retry and deduplication."""

    def __init__(
        self,
        agent_id: str,
        base_url: str,
        retry_enabled: bool = True,
        max_retries: int = 3,
        message_handler: Optional[Callable[[dict], Any]] = None,
        nonce_ttl_hours: int = 24,
    ):
        super().__init__(agent_id)
        self.base_url = base_url.rstrip("/")
        self.retry_enabled = retry_enabled
        self.max_retries = max_retries
        self.message_handler = message_handler
        self.nonce_ttl_hours = nonce_ttl_hours
        self._app: Optional[FastAPI] = None
        self._server: Optional[uvicorn.Server] = None
        self._db_path = Path.home() / ".agenlang" / "agents" / agent_id / "nonce_sentry.db"
        self._nonce_queue: asyncio.Queue = asyncio.Queue()
        self._client: Optional[httpx.AsyncClient] = None

    async def init_db(self) -> None:
        """Initialize the nonce sentry database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS nonces (
                    nonce TEXT PRIMARY KEY,
                    message_id TEXT,
                    received_at TEXT NOT NULL
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_received_at ON nonces(received_at)")
            await db.commit()

    async def _is_duplicate(self, nonce: str, message_id: str) -> bool:
        """Check if nonce is duplicate in database."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT 1 FROM nonces WHERE nonce = ? OR message_id = ?",
                (nonce, message_id),
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def _add_nonce(self, nonce: str, message_id: str) -> None:
        """Add nonce to the queue for async processing."""
        await self._nonce_queue.put((nonce, message_id))

    async def _process_nonce_queue(self) -> None:
        """Background task to process nonce queue."""
        while self._running:
            try:
                nonce, message_id = await asyncio.wait_for(self._nonce_queue.get(), timeout=1.0)
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO nonces (nonce, message_id, received_at) VALUES (?, ?, ?)",
                        (nonce, message_id, datetime.now(timezone.utc).isoformat()),
                    )
                    await db.commit()
            except asyncio.TimeoutError:
                await self._prune_old_nonces()

    async def _prune_old_nonces(self) -> None:
        """Prune nonces older than TTL."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.nonce_ttl_hours)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM nonces WHERE received_at < ?",
                (cutoff.isoformat(),),
            )
            await db.commit()

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with routes."""
        app = FastAPI(title=f"AgenLang Agent {self.agent_id}")

        @app.get("/.well-known/agent-card.json")
        async def get_agent_card() -> JSONResponse:
            """Serve the agent card."""
            from agenlang.core import get_agent_card_data

            card_data = await get_agent_card_data(self.agent_id)
            return JSONResponse(content=card_data)

        @app.post("/agenlang")
        async def receive_message(request: Request) -> Response:
            """Receive a signed YAML/JSON message."""
            body = await request.body()

            try:
                content = yaml.safe_load(body)
            except yaml.YAMLError:
                return Response(content="Invalid YAML", status_code=400)

            if not isinstance(content, dict):
                return Response(content="Invalid message format", status_code=400)

            if "envelope" not in content or "content" not in content:
                return Response(content="Missing envelope or content", status_code=400)

            envelope = content.get("envelope", {})
            nonce = envelope.get("nonce")
            message_id = envelope.get("message_id")

            if not nonce or not message_id:
                return Response(content="Missing nonce or message_id", status_code=400)

            is_dup = await self._is_duplicate(nonce, message_id)
            if is_dup:
                return Response(content="Duplicate message", status_code=200)

            await self._add_nonce(nonce, message_id)

            if self.message_handler:
                await self.message_handler(content)

            return Response(content="OK", status_code=200)

        return app

    async def send(self, url: str, message: dict) -> None:
        """Send via HTTP POST with retry."""
        if not url.startswith("https://"):
            raise ValueError("HTTP transport requires HTTPS URL")

        if self._client is None:
            self._client = httpx.AsyncClient()

        yaml_content = yaml.dump(message)

        for attempt in range(self.max_retries):
            try:
                response = await self._client.post(
                    url,
                    content=yaml_content,
                    headers={"Content-Type": "application/x-yaml"},
                    timeout=30.0,
                )
                response.raise_for_status()
                return
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)

    async def start(self) -> None:
        """Start HTTP server."""
        if not self.base_url.startswith("https://"):
            raise ValueError(
                "Plaintext HTTP not allowed. Use HTTPS. "
                "Set base_url starting with https:// or configure SSL certificates."
            )

        await self.init_db()
        self._app = self._create_app()

        host = self.base_url.replace("https://", "").split(":")[0]
        port = 443

        config = uvicorn.Config(
            self._app,
            host=host,
            port=port,
            ssl_certfile=None,
            ssl_keyfile=None,
        )
        self._server = uvicorn.Server(config)
        self._running = True

        asyncio.create_task(self._server.serve())
        asyncio.create_task(self._process_nonce_queue())

    async def stop(self) -> None:
        """Stop HTTP server."""
        self._running = False
        if self._server:
            self._server.should_exit = True
        if self._client:
            await self._client.aclose()


class WebSocketTransport(Transport):
    """WebSocket transport implementation."""

    def __init__(
        self,
        agent_id: str,
        url: str,
        message_handler: Optional[Callable[[dict], Any]] = None,
    ):
        super().__init__(agent_id)
        self.url = url
        self.message_handler = message_handler
        self._connections: set[Any] = set()
        self._server = None

    async def send(self, url: str, message: dict) -> None:
        """Send via WebSocket."""
        ...

    async def receive(self) -> dict:
        """Receive via WebSocket."""
        ...

    async def start(self) -> None:
        """Start WebSocket server."""
        ...

    async def stop(self) -> None:
        """Stop WebSocket server."""
        ...


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """Retry with exponential backoff."""
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                await asyncio.sleep(delay)

    raise last_exception
