# Plan 5: Discovery

**Phase:** 1  
**Priority:** Medium (depends on Identity + Schema + Transport)  
**Requirements:** DSC-01, DSC-02, DSC-03, DSC-04, DSC-05

---

## Description

Implements the Discovery module with Agent Card schema, HTTP-based discovery, mDNS local network discovery, caching with TTL, and cryptographic signatures on Agent Cards. This enables agents to find each other on the network.

---

## Requirements Covered

| Requirement | Description |
|-------------|-------------|
| DSC-01 | Agent Card schema with did, name, description, capabilities, transports |
| DSC-02 | HTTP-based discovery via /.well-known/agent-card.json |
| DSC-03 | mDNS/Zeroconf local network discovery |
| DSC-04 | Agent Card caching with TTL |
| DSC-05 | Cryptographically signed Agent Cards |

---

## Success Criteria

1. **Agent Card contains all required fields**
   - did: DID of the agent
   - name: Human-readable name
   - description: Purpose and behavior
   - capabilities: Array of task definitions
   - transports: Array of endpoint URLs

2. **HTTP discovery works**
   - Agent Card served at /.well-known/agent-card.json
   - Can fetch remote Agent Cards via HTTP GET
   - Standard well-known URL format

3. **mDNS discovery finds local agents**
   - Broadcasts agent via mDNS on local network
   - Discovers other agents on LAN
   - Service type: _agenlang._tcp.local

4. **Agent Card caching works**
   - Fetched cards cached in database
   - TTL-based expiration (configurable, default 1 hour)
   - Proactive refresh on use if expired

5. **Agent Cards are cryptographically signed**
   - Signature over canonicalized card content
   - Verification on fetch

---

## Implementation Tasks

### Task 5.1: Agent Card Schema

```
Location: src/agenlang/discovery.py
```

1. Create `AgentCard` Pydantic model:
```python
class AgentCard(BaseModel):
    did: str
    name: str
    description: str
    capabilities: list[Capability]
    pricing: Pricing | None = None
    transports: list[TransportInfo]
    mcp_tools: list[dict] = []
    updated_at: datetime
    signature: str | None = None


class Capability(BaseModel):
    task: str
    input_schema: dict
    output_schema: dict


class Pricing(BaseModel):
    base_joules: float
    per_1k_tokens: float | None = None
    weights: PricingWeights


class PricingWeights(BaseModel):
    w1_prompt: float = 1.0
    w2_completion: float = 3.0
    w3_compute_sec: float = 10.0


class TransportInfo(BaseModel):
    type: Literal["http", "websocket"]
    url: str  # https://... or wss://...
```

2. Add validation:
   - DID must match did:key format
   - URLs must be https:// or wss://
   - pricing.weights required if pricing present

### Task 5.2: Agent Card Signing

1. Create `AgentCardSigner`:
```python
class AgentCardSigner:
    def __init__(self, private_key: Ed25519PrivateKey, did: str):
        self.private_key = private_key
        self.did = did
    
    def sign(self, card: AgentCard) -> AgentCard:
        """Create signed copy of card."""
        # Remove signature before signing
        unsigned = card.model_copy()
        unsigned.signature = None
        
        # Canonicalize
        canonical = rfc8785.canonicalize(unsigned.model_dump())
        
        # Sign
        digest = hashlib.sha256(canonical).digest()
        sig = self.private_key.sign(digest)
        
        # Add signature
        signed = unsigned.model_copy()
        signed.signature = base64.urlsafe_b64encode(sig).decode()
        return signed
    
    def verify(self, card: AgentCard) -> bool:
        """Verify card signature."""
        if not card.signature:
            return False
        
        # Extract signature
        sig = base64.urlsafe_b64decode(card.signature)
        
        # Create unsigned copy
        unsigned = card.model_copy()
        unsigned.signature = None
        
        # Canonicalize and verify
        canonical = rfc8785.canonicalize(unsigned.model_dump())
        digest = hashlib.sha256(canonical).digest()
        
        public_key = extract_public_key_from_did(card.did)
        return public_key.verify(sig, digest)
```

### Task 5.3: HTTP Discovery

1. Create `HttpDiscovery` class:
```python
class HttpDiscovery:
    def __init__(self, http_client: httpx.AsyncClient):
        self.client = http_client
    
    async def fetch_card(self, url: str) -> AgentCard | None:
        """Fetch Agent Card from remote URL."""
        # Must be https://
        if not url.startswith('https://'):
            raise ConfigurationError("HTTP discovery requires HTTPS")
        
        card_url = f"{url}/.well-known/agent-card.json"
        response = await self.client.get(card_url)
        
        if response.status_code == 200:
            data = response.json()
            return AgentCard(**data)
        
        return None
    
    async def publish_card(self, card: AgentCard) -> None:
        """Used internally - card served via transport."""
        pass
```

2. Integrate into Transport - already handled in Plan 4 (GET /.well-known/agent-card.json)

### Task 5.4: mDNS Discovery

1. Create `MdnsDiscovery` class:
```python
class MdnsDiscovery:
    SERVICE_TYPE = "_agenlang._tcp.local."
    
    def __init__(self, agent: BaseAgent):
        self.agent = agent
        self.zeroconf: Zeroconf | None = None
        self.listener: MdnsListener | None = None
    
    async def start(self) -> None:
        """Start mDNS advertisement and discovery."""
        # Advertise our agent
        info = self._build_service_info()
        await self.zeroconf.register_service(info)
        
        # Start listening for other agents
        self.listener = MdnsListener(self.agent.discovery_cache)
        await self.zeroconf.add_listener(self.listener, None)
    
    async def stop(self) -> None:
        """Stop mDNS."""
        if self.zeroconf:
            await self.zeroconf.unregister_all_services()
            self.zeroconf.close()
    
    def _build_service_info(self) -> ServiceInfo:
        """Build mDNS service info for our agent."""
        return ServiceInfo(
            type_=self.SERVICE_TYPE,
            name=f"agenlang-{self.agent.agent_id}.{self.SERVICE_TYPE}",
            addresses=[socket.inet_aton(self._get_local_ip())],
            port=self.agent.transport.get_port(),
            properties={
                b"did": self.agent.did.encode(),
                b"name": self.agent.card.name.encode(),
            }
        )
```

2. Create `MdnsListener`:
```python
class MdnsListener:
    def __init__(self, cache: AgentCardCache):
        self.cache = cache
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        # Resolve service, fetch agent card, store in cache
        info = zc.get_service_info(type_, name)
        if info:
            # Extract URL from service
            url = f"https://{info.addresses[0]}:{info.port}"
            # Fetch card and cache
```

### Task 5.5: Agent Card Cache

1. Create `AgentCardCache`:
```python
class AgentCardCache:
    def __init__(self, db: aiosqlite.Connection, default_ttl: timedelta = timedelta(hours=1)):
        self.db = db
        self.default_ttl = default_ttl
    
    async def get(self, did: str) -> AgentCard | None:
        """Get card from cache if not expired."""
        cursor = await self.db.execute(
            "SELECT card_data, expires_at FROM agent_cards WHERE did = ?",
            (did,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        card_data, expires_at = row
        if datetime.fromisoformat(expires_at) < datetime.utcnow():
            # Expired
            return None
        
        return AgentCard(**json.loads(card_data))
    
    async def set(self, card: AgentCard, ttl: timedelta | None = None) -> None:
        """Store card in cache."""
        ttl = ttl or self.default_ttl
        expires_at = datetime.utcnow() + ttl
        
        await self.db.execute(
            """INSERT OR REPLACE INTO agent_cards 
               (did, card_data, fetched_at, expires_at) 
               VALUES (?, ?, ?, ?)""",
            (card.did, card.model_dump_json(), datetime.utcnow().isoformat(), expires_at.isoformat())
        )
        await self.db.commit()
    
    async def invalidate(self, did: str) -> None:
        """Remove card from cache."""
        await self.db.execute("DELETE FROM agent_cards WHERE did = ?", (did,))
        await self.db.commit()
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count deleted."""
        cursor = await self.db.execute(
            "DELETE FROM agent_cards WHERE expires_at < ?",
            (datetime.utcnow().isoformat(),)
        )
        await self.db.commit()
        return cursor.rowcount
```

### Task 5.6: Discovery Service

1. Create `DiscoveryService` that combines HTTP and mDNS:
```python
class DiscoveryService:
    def __init__(
        self,
        agent: BaseAgent,
        http_discovery: HttpDiscovery,
        mdns_discovery: MdnsDiscovery,
        cache: AgentCardCache
    ):
        self.agent = agent
        self.http = http_discovery
        self.mdns = mdns_discovery
        self.cache = cache
    
    async def find_agent(self, did: str) -> AgentCard | None:
        """Find agent by DID (check cache first, then HTTP)."""
        # Check cache
        card = await self.cache.get(did)
        if card:
            return card
        
        # Try to resolve from known transports or DHT
        # For now, return None (would need resolution service)
        return None
    
    async def discover_local(self) -> list[AgentCard]:
        """Discover agents on local network via mDNS."""
        # Return all cached cards from mDNS
        pass
    
    async def refresh_card(self, did: str) -> AgentCard | None:
        """Force refresh card from source."""
        # Implementation
```

### Task 5.7: Integration Tests

1. Test Agent Card schema validation
2. Test Agent Card signing/verification
3. Test HTTP fetch card
4. Test mDNS advertisement
5. Test mDNS discovery
6. Test cache TTL expiration
7. Test cache cleanup

---

## Dependencies

- `zeroconf` (aka `python-zeroconf`) - mDNS/Zeroconf
- `httpx` - Already from Transport
- `rfc8785` - Already from Identity
- `agenlang.identity` - From Plan 1

---

## Files to Create/Modify

- `src/agenlang/discovery.py` - Discovery module
- `src/agenlang/__init__.py` - Export discovery classes
- `tests/unit/test_discovery.py` - Unit tests

---

## Notes

- mDNS only works on local network (no router forwarding)
- HTTPS required for HTTP discovery
- Card signature verification is critical for security
- Default cache TTL: 1 hour (configurable)
- Cleanup expired entries on startup and periodically
