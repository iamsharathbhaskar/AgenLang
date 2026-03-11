# Plan 4: Transport Layer

**Phase:** 1  
**Priority:** High (depends on Core Agent)  
**Requirements:** TRN-01, TRN-02, TRN-03, TRN-04, TRN-05

---

## Description

Implements the HTTP transport layer with POST endpoint for messages, Agent Card serving, plaintext rejection, retry with exponential backoff, and message deduplication. This enables agents to communicate over the network.

---

## Requirements Covered

| Requirement | Description |
|-------------|-------------|
| TRN-01 | HTTP POST endpoint receives signed YAML messages at /agenlang |
| TRN-02 | Static /.well-known/agent-card.json serves signed Agent Card |
| TRN-03 | Reject plaintext HTTP at startup with ConfigurationError |
| TRN-04 | Implement retry with exponential backoff |
| TRN-05 | Message deduplication via nonce + message_id |

---

## Success Criteria

1. **HTTP POST endpoint receives signed YAML messages**
   - Route: POST /agenlang
   - Accepts YAML body with envelope + content
   - Returns acknowledgment or error

2. **Agent Card served at /.well-known/agent-card.json**
   - GET route returns signed Agent Card
   - Card includes DID, name, capabilities, transports

3. **Plaintext HTTP rejected at startup**
   - Check URL scheme in config
   - Raise ConfigurationError if http:// detected
   - Only https:// and wss:// allowed

4. **Retry with exponential backoff works**
   - Failed messages retried automatically
   - Backoff: 1s, 2s, 4s, 8s, 16s (max 5 retries)
   - Configurable max_retries

5. **Message deduplication via nonce + message_id**
   - Track sent message nonces
   - Skip retry if message_id already sent
   - Incoming: delegate to Nonce Sentry

---

## Implementation Tasks

### Task 4.1: HTTP Transport Base

```
Location: src/agenlang/transport/base.py
```

1. Create abstract `Transport` base class:
```python
class Transport(ABC):
    @abstractmethod
    async def start(self, agent: BaseAgent) -> None:
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        pass
    
    @abstractmethod
    async def send(self, envelope: MessageEnvelope, content: MessageContent) -> bool:
        pass
    
    @abstractmethod
    async def receive(self) -> tuple[MessageEnvelope, MessageContent] | None:
        pass
```

2. Create `HttpTransport` class inheriting from `Transport`:
```python
class HttpTransport(Transport):
    def __init__(self, base_url: str, max_retries: int = 5):
        self.base_url = base_url  # e.g., https://agent.example.com
        self.max_retries = max_retries
        self.app: FastAPI | None = None
        self.server: uvicorn.Server | None = None
```

### Task 4.2: Plaintext Rejection

1. Add URL validation in `HttpTransport.__init__`:
```python
def __init__(self, base_url: str, ...):
    if not base_url.startswith(('https://', 'wss://')):
        raise ConfigurationError(
            f"Plaintext transport not allowed: {base_url}. "
            "Use HTTPS or WSS only."
        )
    self.base_url = base_url
```

2. Also validate incoming message URLs in Agent Card processing

### Task 4.3: HTTP Server Setup

1. Create FastAPI app in `HttpTransport`:
```python
async def start(self, agent: BaseAgent) -> None:
    self.agent = agent
    self.app = FastAPI()
    
    # POST /agenlang - receive messages
    @self.app.post("/agenlang")
    async def receive_message(request: Request):
        body = await request.body()
        data = yaml.safe_load(body)
        envelope = MessageEnvelope(**data['envelope'])
        content = MessageContent(**data['content'])
        
        # Process via agent
        await self.agent.process_message(envelope, content)
        
        return {"status": "received"}
    
    # GET /.well-known/agent-card.json - serve agent card
    @self.app.get("/.well-known/agent-card.json")
    async def get_agent_card():
        return json.loads(agent.card.to_json())
    
    # Start uvicorn server
    config = uvicorn.Config(self.app, host="0.0.0.0", port=443, ...)
    self.server = uvicorn.Server(config)
    await self.server.serve()
```

2. Handle HTTPS certificate (self-signed for dev, let's encrypt for prod)

### Task 4.4: Send with Retry

1. Implement `HttpTransport.send()`:
```python
async def send(self, envelope: MessageEnvelope, content: MessageContent) -> bool:
    url = f"{self.base_url}/agenlang"
    body = yaml.dump({
        'envelope': envelope.model_dump(),
        'content': content.model_dump()
    })
    
    backoff = 1.0
    for attempt in range(self.max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, content=body)
                if response.status_code == 200:
                    return True
        except Exception as e:
            logger.warning(f"Send failed (attempt {attempt + 1}): {e}")
        
        if attempt < self.max_retries:
            await asyncio.sleep(backoff)
            backoff *= 2  # Exponential backoff
    
    return False
```

2. Add retry config options:
   - `max_retries`: int = 5
   - `base_backoff`: float = 1.0
   - `max_backoff`: float = 16.0

### Task 4.5: Message Deduplication (Outbound)

1. Add deduplication to `HttpTransport`:
```python
class HttpTransport:
    def __init__(self, ...):
        self._sent_messages: dict[str, datetime] = {}
    
    async def send(self, envelope, content) -> bool:
        message_id = envelope.message_id
        nonce = envelope.nonce
        
        # Check if already sent
        if await self._is_duplicate(message_id, nonce):
            logger.info(f"Skipping duplicate message: {message_id}")
            return True
        
        # Send with retry
        success = await self._send_with_retry(...)
        
        if success:
            await self._mark_sent(message_id, nonce)
        
        return success
    
    async def _is_duplicate(self, message_id: str, nonce: str) -> bool:
        # Check database or memory cache
        key = f"{message_id}:{nonce}"
        return key in self._sent_messages
    
    async def _mark_sent(self, message_id: str, nonce: str) -> None:
        key = f"{message_id}:{nonce}"
        self._sent_messages[key] = datetime.utcnow()
```

2. Cleanup old entries periodically (TTL: 24 hours)

### Task 4.6: Retry Queue

1. Create `RetryQueue` for failed messages:
```python
class RetryQueue:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
    
    async def enqueue(self, envelope: MessageEnvelope, content: MessageContent) -> None:
        await self.db.execute(
            "INSERT INTO message_queue (envelope, content) VALUES (?, ?)",
            (json.dumps(envelope.model_dump()), json.dumps(content.model_dump()))
        )
    
    async def retry_pending(self, transport: Transport) -> int:
        # Get pending messages, attempt send
        # Increment retry_count on failure
        # Remove after max retries
```

### Task 4.7: Integration Tests

1. Test plaintext URL rejection
2. Test POST /agenlang receives messages
3. Test GET /.well-known/agent-card.json returns card
4. Test retry with exponential backoff
5. Test message deduplication

---

## Dependencies

- `fastapi` - HTTP server
- `httpx` - HTTP client
- `uvicorn` - ASGI server
- `pyyaml` - Already from Schema
- `aiosqlite` - Already from Core

---

## Files to Create/Modify

- `src/agenlang/transport/__init__.py` - Package init
- `src/agenlang/transport/base.py` - Transport base class
- `src/agenlang/transport/http.py` - HTTP transport
- `src/agenlang/core.py` - Integrate transport
- `tests/unit/test_transport.py` - Unit tests

---

## Notes

- HTTP port 443 requires root; use 8443 for dev or setcap
- Self-signed certs: generate via `openssl req -x509 -newkey rsa:4096`
- Deduplication key = message_id + nonce (covers both directions)
- Inbound deduplication handled by Nonce Sentry (Plan 3)
