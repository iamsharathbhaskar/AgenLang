# Plan 3: Core Agent & Persistence

**Phase:** 1  
**Priority:** High (depends on Identity + Schema)  
**Requirements:** COR-01, COR-02, COR-03, COR-04, COR-05, COR-06, COR-07, COR-08, COR-09, CTR-01, CTR-02

---

## Description

Implements the BaseAgent abstract class with SQLite persistence, asyncio message loop, lifecycle management, event handlers, Nonce Sentry for replay protection, and task lifecycle state machine. This is the runtime engine for agents.

---

## Requirements Covered

| Requirement | Description |
|-------------|-------------|
| COR-01 | BaseAgent abstract class with identity, transport, SQLite persistence |
| COR-02 | SQLite database at ~/.agenlang/agents/<agent-id>/session.db |
| COR-03 | Asyncio message receive/send loop |
| COR-04 | Lifecycle methods: start, stop, health |
| COR-05 | Event handlers: on_message, on_request, on_propose, on_inform |
| COR-06 | Nonce Sentry checks incoming nonces against session.db |
| COR-07 | Automatic nonce pruning older than 24 hours (configurable TTL) |
| COR-08 | Async-buffered nonce writer using asyncio.Queue |
| COR-09 | Optional trusted_dids filter loaded from config |
| CTR-01 | Task lifecycle states: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED |
| CTR-02 | Contract metadata storage |

---

## Success Criteria

1. **BaseAgent can be instantiated with identity and config**
   - Accepts agent_id, loads/generates keys
   - Accepts config for transport, persistence settings

2. **SQLite persistence works correctly**
   - Database created at `~/.agenlang/agents/<agent-id>/session.db`
   - Tables: contracts, ser_records, agent_cards, message_queue, nonces, trusted_dids

3. **Message loop runs asynchronously**
   - Start method spawns receive loop task
   - Stop method cleanly shuts down
   - Health check returns status

4. **Event handlers are called appropriately**
   - `on_message` - any incoming message
   - `on_request` - REQUEST performative
   - `on_propose` - PROPOSE performative
   - `on_inform` - INFORM performative

5. **Nonce Sentry prevents replay attacks**
   - Incoming nonces checked against stored nonces
   - Duplicate nonces rejected with log
   - 24-hour TTL pruning runs automatically

6. **Async-buffered nonce writer**
   - Nonces queued via asyncio.Queue
   - Batch inserts via aiosqlite.executemany

7. **Trusted DIDs filter works**
   - Optional allow-list loaded from config
   - Messages from non-trusted DIDs dropped/refused

8. **Task lifecycle state machine functions**
   - States: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
   - Valid transitions enforced

---

## Implementation Tasks

### Task 3.1: Database Schema

```
Location: src/agenlang/core.py
```

1. Create `init_database(agent_id: str) -> aiosqlite.Connection`
   - Database path: `~/.agenlang/agents/<agent-id>/session.db`
   - Create tables:

```sql
CREATE TABLE IF NOT EXISTS nonces (
    nonce TEXT PRIMARY KEY,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_id TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    trace_id TEXT,
    parent_contract_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS ser_records (
    record_id TEXT PRIMARY KEY,
    contract_id TEXT,
    joules REAL,
    breakdown JSON,
    signature TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_cards (
    did TEXT PRIMARY KEY,
    card_data JSON,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope JSON,
    content JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trusted_dids (
    did TEXT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nonces_received ON nonces(received_at);
CREATE INDEX IF NOT EXISTS idx_contracts_state ON contracts(state);
```

### Task 3.2: BaseAgent Abstract Class

1. Create `BaseAgent` abstract class:
```python
class BaseAgent(ABC):
    def __init__(self, agent_id: str, config: AgentConfig):
        self.agent_id = agent_id
        self.config = config
        self.did: str = ...
        self.private_key: Ed25519PrivateKey = ...
        self.db: aiosqlite.Connection = ...
        self._running = False
        self._tasks: list[asyncio.Task] = []
```

2. Define abstract methods:
   - `async def start() -> None`
   - `async def stop() -> None`
   - `async def health() -> AgentHealth`

3. Define event handler hooks:
   - `async def on_message(self, envelope: MessageEnvelope, content: MessageContent)`
   - `async def on_request(self, envelope: MessageEnvelope, content: RequestContent)`
   - `async def on_propose(self, envelope: MessageEnvelope, content: ProposeContent)`
   - `async def on_inform(self, envelope: MessageEnvelope, content: InformContent)`

### Task 3.3: Nonce Sentry

1. Create `NonceSentry` class:
```python
class NonceSentry:
    def __init__(self, db: aiosqlite.Connection, ttl_hours: int = 24):
        self.db = db
        self.ttl = timedelta(hours=ttl_hours)
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._writer_task: asyncio.Task | None = None
    
    async def check_and_store(self, nonce: str, message_id: str) -> bool:
        """Returns True if nonce is valid (not duplicate), False if duplicate."""
    
    async def start(self) -> None:
        """Start async writer task."""
    
    async def stop(self) -> None:
        """Stop writer and flush queue."""
    
    async def prune(self) -> int:
        """Delete nonces older than TTL. Returns count deleted."""
```

2. Implement check_and_store:
   - Query database for nonce
   - If exists → return False (duplicate)
   - If not → add to queue, return True

3. Implement async buffered writer:
   - Collect nonces from queue
   - Batch insert via `executemany`
   - Flush on stop

4. Implement prune:
   - Delete where `received_at < datetime.utcnow() - ttl`

### Task 3.4: Trusted DIDs Filter

1. Create `TrustedDidsFilter` class:
```python
class TrustedDidsFilter:
    def __init__(self, db: aiosqlite.Connection, enabled: bool = False):
        self.db = db
        self.enabled = enabled
        self._cache: set[str] = set()
    
    async def load_from_config(self, dids: list[str]) -> None:
        """Load trusted DIDs from config into database."""
    
    async def is_trusted(self, did: str) -> bool:
        """Check if DID is trusted (or if filter is disabled)."""
```

2. Integrate into BaseAgent:
   - Load from `config.trusted_dids` at startup
   - Check in incoming message handler

### Task 3.5: Message Loop

1. Implement `BaseAgent.run()`:
```python
async def run(self) -> None:
    """Main message processing loop."""
    while self._running:
        message = await self.receive_message()
        if message:
            await self.process_message(message)
```

2. Implement `process_message(envelope, content)`:
   - Verify signature first
   - Check Nonce Sentry
   - Check Trusted DIDs filter
   - Dispatch to appropriate handler

### Task 3.6: Lifecycle Methods

1. Implement `start()`:
   - Initialize database
   - Load/generate keys
   - Start Nonce Sentry
   - Start message loop task
   - Set `_running = True`

2. Implement `stop()`:
   - Set `_running = False`
   - Stop Nonce Sentry
   - Cancel running tasks
   - Close database connection

3. Implement `health()`:
```python
async def health() -> AgentHealth:
    return AgentHealth(
        running=self._running,
        db_connected=await self._check_db(),
        nonce_sentry_status="healthy",
        message_queue_size=...
    )
```

### Task 3.7: Task Lifecycle State Machine

```
Location: src/agenlang/contracts.py
```

1. Create `TaskState` enum:
```python
class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

2. Create `Contract` model:
```python
class Contract(BaseModel):
    contract_id: str
    state: TaskState
    trace_id: str
    parent_contract_id: str | None
    creator_did: str
    participant_did: str
    created_at: datetime
    updated_at: datetime
    metadata: dict
```

3. Create `ContractStore` class:
   - `create(contract: Contract) -> None`
   - `get(contract_id: str) -> Contract | None`
   - `update_state(contract_id: str, new_state: TaskState) -> None`
   - `list_by_state(state: TaskState) -> list[Contract]`

### Task 3.8: Integration Tests

1. Test BaseAgent instantiation
2. Test database creation and tables
3. Test Nonce Sentry duplicate detection
4. Test Nonce Sentry pruning
5. Test Trusted DIDs filter
6. Test lifecycle start/stop
7. Test task state transitions

---

## Dependencies

- `aiosqlite` - Async SQLite
- `pydantic` - Already from Schema
- `agenlang.identity` - From Plan 1
- `agenlang.schema` - From Plan 2

---

## Files to Create/Modify

- `src/agenlang/core.py` - BaseAgent implementation
- `src/agenlang/contracts.py` - Task lifecycle
- `src/agenlang/__init__.py` - Export classes
- `tests/unit/test_core.py` - Unit tests

---

## Notes

- Nonce Sentry must verify signature BEFORE checking nonce (prevent DoS)
- Pruning should run on startup and periodically (e.g., every hour)
- Trusted DIDs filter should be optional and disabled by default
- Database path must be configurable via `~/.agenlang/config.yaml`
