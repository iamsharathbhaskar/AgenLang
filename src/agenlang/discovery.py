"""Discovery module - Agent Card schema and discovery mechanisms."""

import asyncio
import json
from typing import Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite
import httpx
from zeroconf import Zeroconf, ServiceInfo, ServiceListener

from agenlang.schema import AgentCard as SchemaAgentCard
from agenlang.identity import canonicalize_for_signing


SERVICE_TYPE = "_agenlang._tcp.local."


class AgentDiscovery:
    """Agent discovery mechanisms with HTTP and mDNS support."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".agenlang" / "discovery.db"
        self._cache: dict[str, tuple[AgentCard, datetime]] = {}
        self._zeroconf: Optional[Zeroconf] = None

    async def init_db(self) -> None:
        """Initialize the discovery cache database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_cards (
                    did TEXT PRIMARY KEY,
                    card_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    ttl_seconds INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def discover_http(self, url: str) -> Optional[AgentCard]:
        """Discover agent via HTTP /.well-known/agent-card.json."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                card = AgentCard.model_validate(data)
                return card
        except Exception:
            return None

    async def discover_mdns(self, service_name: str = SERVICE_TYPE) -> list[AgentCard]:
        """Discover agents via mDNS/Zeroconf on local network."""
        cards = []

        def on_service_found(zeroconf: Zeroconf, service_type: str, name: str, info: ServiceInfo):
            addresses = info.addresses
            port = info.port
            for addr in addresses:
                ip = ".".join(str(b) for b in addr)
                url = f"http://{ip}:{port}/.well-known/agent-card.json"
                asyncio.create_task(self._discover_and_cache(url))

        try:
            self._zeroconf = Zeroconf()
            browser = Zeroconf.ServiceBrowser(
                self._zeroconf, service_name, listener=ServiceListener()
            )
            await asyncio.sleep(3)
        except Exception:
            pass

        return cards

    async def _discover_and_cache(self, url: str) -> None:
        """Helper to discover and cache a card."""
        card = await self.discover_http(url)
        if card:
            await self.cache_card(card, ttl_seconds=3600)

    async def cache_card(self, card: AgentCard, ttl_seconds: int = 3600) -> None:
        """Cache discovered agent card with TTL."""
        self._cache[card.did] = (card, datetime.now(timezone.utc))

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_cards (did, card_json, cached_at, ttl_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (
                    card.did,
                    card.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                    ttl_seconds,
                ),
            )
            await db.commit()

    async def get_cached(self, did: str) -> Optional[AgentCard]:
        """Get cached agent card if not expired."""
        if did in self._cache:
            card, cached_at = self._cache[did]
            ttl = 3600
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < ttl:
                return card

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT card_json, cached_at, ttl_seconds FROM agent_cards WHERE did = ?",
                (did,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    card_json, cached_at_str, ttl = row
                    cached_at = datetime.fromisoformat(cached_at_str)
                    if (datetime.now(timezone.utc) - cached_at).total_seconds() < ttl:
                        card = AgentCard.model_validate_json(card_json)
                        self._cache[did] = (card, cached_at)
                        return card
        return None

    async def refresh_cache(self) -> None:
        """Refresh all expired cached cards."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT did, card_json FROM agent_cards",
            ) as cursor:
                rows = await cursor.fetchall()

        for did, card_json in rows:
            card_data = json.loads(card_json)
            if card_data.get("transports"):
                transport_url = card_data["transports"][0].get("url", "")
                if transport_url:
                    url = transport_url.replace("/agenlang", "/.well-known/agent-card.json")
                    await self.discover_http(url)

    async def close(self) -> None:
        """Close discovery resources."""
        if self._zeroconf:
            self._zeroconf.close()


class AgentCard(SchemaAgentCard):
    """Agent Card - self-describing document for discovery."""

    pass


def sign_agent_card(card: AgentCard, private_key: "ed25519.Ed25519PrivateKey") -> AgentCard:
    """Cryptographically sign an Agent Card."""
    from cryptography.hazmat.primitives import hashes
    import base64

    card_dict = card.model_dump(exclude={"signature"})
    canonical_bytes = canonicalize_for_signing({"did": card.did}, card_dict)

    digest = hashes.Hash(hashes.SHA256())
    digest.update(canonical_bytes)
    message_hash = digest.finalize()

    signature = private_key.sign(message_hash)
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    card.signature = signature_b64
    return card


def verify_agent_card_signature(card: AgentCard) -> bool:
    """Verify Agent Card signature."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ed25519
    import base64

    try:
        from agenlang.identity import parse_did_key

        public_key = parse_did_key(card.did)

        card_dict = card.model_dump(exclude={"signature"})
        canonical_bytes = canonicalize_for_signing({"did": card.did}, card_dict)

        digest = hashes.Hash(hashes.SHA256())
        digest.update(canonical_bytes)
        message_hash = digest.finalize()

        signature = base64.urlsafe_b64decode(card.signature + "==")

        public_key.verify(signature, message_hash)
        return True
    except Exception:
        return False
