"""Abstract base class for registry backends.

Defines the interface that all registry backends must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AgentRecord:
    """Registered agent information."""

    did_key: str
    pubkey_pem: str
    endpoint_url: str
    name: str
    description: str
    capabilities: List[str]
    reputation_score: float
    joule_rate: float
    version: str
    created_at: str
    last_seen: str
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "did_key": self.did_key,
            "pubkey_pem": self.pubkey_pem,
            "endpoint_url": self.endpoint_url,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "reputation_score": self.reputation_score,
            "joule_rate": self.joule_rate,
            "version": self.version,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "is_active": self.is_active,
        }


@dataclass
class ExecutionRecord:
    """Contract execution history entry."""

    execution_id: str
    contract_id: str
    issuer_did: str
    receiver_did: str
    joules_used: float
    status: str  # success, failed, timeout
    created_at: str
    ser_summary: Optional[str] = None  # JSON string of key SER fields


@dataclass
class SearchQuery:
    """Query for searching agents."""

    capability: Optional[str] = None
    min_reputation: float = 0.0
    name_pattern: Optional[str] = None
    limit: int = 100
    offset: int = 0


@dataclass
class InteractionRecord:
    """Record of an agent interaction (for reputation tracking)."""

    interaction_id: str
    contract_id: str
    issuer_did: str
    receiver_did: str
    rating: float  # 0.0-1.0
    joules_used: float
    status: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class RegistryBackend(ABC):
    """Abstract base class for registry storage backends.

    All implementations must provide async methods for:
    - Schema initialization
    - Agent CRUD operations
    - Reputation tracking
    - Execution/interaction history
    - Search capabilities
    """

    @abstractmethod
    async def init_schema(self) -> None:
        """Initialize database schema (tables, indexes, etc.)."""
        ...

    @abstractmethod
    async def register_agent(
        self,
        did_key: str,
        pubkey_pem: str,
        endpoint_url: str,
        capabilities: List[str],
        name: str = "Unknown Agent",
        description: str = "",
        joule_rate: float = 1.0,
        version: str = "0.1.0",
    ) -> AgentRecord:
        """Register a new agent or update existing.

        Args:
            did_key: Agent DID:key identifier
            pubkey_pem: PEM-encoded public key
            endpoint_url: A2A endpoint URL
            capabilities: List of capability strings
            name: Human-readable name
            description: Agent description
            joule_rate: Cost per Joule for services
            version: Agent software version

        Returns:
            AgentRecord of registered agent
        """
        ...

    @abstractmethod
    async def get_agent(self, did_key: str) -> Optional[AgentRecord]:
        """Get agent by DID:key.

        Args:
            did_key: Agent identifier

        Returns:
            AgentRecord if found, None otherwise
        """
        ...

    @abstractmethod
    async def find_agents_by_capability(
        self, capability: str, min_reputation: float = 0.0
    ) -> List[AgentRecord]:
        """Find agents with a specific capability.

        Args:
            capability: Capability to search for (e.g., "net:read")
            min_reputation: Minimum reputation score (0.0-1.0)

        Returns:
            List of matching agents, sorted by reputation
        """
        ...

    @abstractmethod
    async def list_agents(self, limit: int = 100) -> List[AgentRecord]:
        """List all registered agents.

        Args:
            limit: Maximum number to return

        Returns:
            List of agents
        """
        ...

    @abstractmethod
    async def update_reputation(self, did_key: str, new_score: float) -> None:
        """Update agent reputation score.

        Args:
            did_key: Agent identifier
            new_score: New reputation score (0.0-1.0, clamped)
        """
        ...

    @abstractmethod
    async def record_execution(
        self,
        execution_id: str,
        contract_id: str,
        issuer_did: str,
        receiver_did: str,
        joules_used: float,
        status: str,
        ser_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a contract execution.

        Args:
            execution_id: Unique execution identifier
            contract_id: Contract URN
            issuer_did: Issuer agent DID
            receiver_did: Receiver/executor agent DID
            joules_used: Joules consumed
            status: Execution status (success, failed, timeout)
            ser_summary: Optional SER summary for analytics
        """
        ...

    @abstractmethod
    async def get_execution_history(
        self, did_key: str, as_issuer: bool = True, limit: int = 100
    ) -> List[ExecutionRecord]:
        """Get execution history for an agent.

        Args:
            did_key: Agent DID
            as_issuer: If True, get contracts issued by agent; else received
            limit: Maximum records

        Returns:
            List of execution records
        """
        ...

    @abstractmethod
    async def calculate_reputation_from_history(self, did_key: str) -> float:
        """Calculate reputation score from execution history.

        Reputation = (successful_executions / total_executions) * efficiency_factor

        Args:
            did_key: Agent DID

        Returns:
            Reputation score (0.0-1.0)
        """
        ...

    @abstractmethod
    async def deactivate_agent(self, did_key: str) -> None:
        """Deactivate an agent (soft delete).

        Args:
            did_key: Agent to deactivate
        """
        ...

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.

        Returns:
            Dict with counts and averages
        """
        ...

    @abstractmethod
    async def search_agents(self, query: SearchQuery) -> List[AgentRecord]:
        """Search agents by query criteria.

        Args:
            query: SearchQuery with filters

        Returns:
            List of matching agents
        """
        ...

    @abstractmethod
    async def record_interaction(self, interaction: InteractionRecord) -> None:
        """Record an interaction for reputation tracking.

        Args:
            interaction: InteractionRecord to store
        """
        ...

    @abstractmethod
    async def get_history(
        self, did_key: str, limit: int = 100
    ) -> List[InteractionRecord]:
        """Get interaction history for an agent.

        Args:
            did_key: Agent DID
            limit: Maximum records to return

        Returns:
            List of interaction records
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the backend connection and cleanup resources."""
        ...
