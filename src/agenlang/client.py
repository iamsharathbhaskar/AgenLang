"""AgentClient - Simple client for agent-to-agent communication using A2A."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import base58

from agenlang.identity import (
    Identity,
    generate_did_key,
    parse_did_key,
    verify_signature,
    canonicalize_for_signing,
    generate_nonce,
)
from agenlang.schema import Performative, ErrorCode


@dataclass
class AgentClient:
    """Simple client for sending messages to other agents via A2A.

    This is the main interface for agents to communicate. It wraps A2A
    transport with DID identity and FIPA-ACL semantics.

    Usage:
        client = AgentClient(did="did:key:z6Mk...")
        result = await client.request(
            to="did:key:z6Mh...",
            action="summarize",
            payload={"text": "..."}
        )
    """

    did: str
    identity: Optional[Identity] = None
    key_path: Optional[str] = None
    agent_id: Optional[str] = None

    _a2a_client: Any = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Load identity if not provided."""
        if self.identity is None:
            agent_id = self.agent_id or self.did.split(":")[-1][:8]
            self.identity = Identity.load(agent_id)

    async def request(
        self,
        to: str,
        action: str,
        payload: dict,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send a REQUEST performative (like a function call).

        Args:
            to: The DID of the receiving agent
            action: The action/task to request
            payload: The input parameters
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            The response from the agent
        """
        message = self._create_message(
            performative=Performative.REQUEST,
            to=to,
            action=action,
            payload=payload,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def propose(
        self,
        to: str,
        action: str,
        payload: dict,
        pricing: Optional[dict] = None,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send a PROPOSE performative (start negotiation).

        Args:
            to: The DID of the receiving agent
            action: The proposed action
            payload: The proposed parameters
            pricing: Optional pricing terms (base_joules, weights, etc.)
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            The response (usually another PROPOSE or ACCEPT/REJECT)
        """
        content = {
            "action": action,
            "payload": payload,
        }
        if pricing:
            content["pricing"] = pricing

        message = self._create_message(
            performative=Performative.PROPOSE,
            to=to,
            action=action,
            payload=content,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def accept(
        self,
        to: str,
        proposal_id: str,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send an ACCEPT-PROPOSAL performative.

        Args:
            to: The DID of the receiving agent
            proposal_id: The ID of the proposal to accept
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            The response from the agent
        """
        message = self._create_message(
            performative=Performative.ACCEPT_PROPOSAL,
            to=to,
            action="accept",
            payload={"proposal_id": proposal_id},
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def reject(
        self,
        to: str,
        proposal_id: str,
        reason: str = ErrorCode.ERR_CAPABILITY_MISMATCH,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send a REJECT-PROPOSAL performative.

        Args:
            to: The DID of the receiving agent
            proposal_id: The ID of the proposal to reject
            reason: Error code explaining why
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            The response from the agent
        """
        message = self._create_message(
            performative=Performative.REJECT_PROPOSAL,
            to=to,
            action="reject",
            payload={"proposal_id": proposal_id, "reason": reason},
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def inform(
        self,
        to: str,
        content: dict,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send an INFORM performative (fire-and-forget notification).

        Args:
            to: The DID of the receiving agent
            content: The information to send
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            Empty dict (no response expected)
        """
        message = self._create_message(
            performative=Performative.INFORM,
            to=to,
            action="inform",
            payload=content,
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def agree(
        self,
        to: str,
        action: str,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send an AGREE performative.

        Args:
            to: The DID of the receiving agent
            action: The action being agreed to
            conversation_id: Optional conversation threading
            trace_id: Optional trace for multi-hop

        Returns:
            The response from the agent
        """
        message = self._create_message(
            performative=Performative.AGREE,
            to=to,
            action=action,
            payload={},
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    async def cancel(
        self,
        to: str,
        conversation_id: str,
        trace_id: Optional[str] = None,
    ) -> dict:
        """Send a CANCEL performative.

        Args:
            to: The DID of the receiving agent
            conversation_id: The conversation to cancel
            trace_id: Optional trace for multi-hop

        Returns:
            The response from the agent
        """
        message = self._create_message(
            performative=Performative.CANCEL,
            to=to,
            action="cancel",
            payload={"conversation_id": conversation_id},
            conversation_id=conversation_id,
            trace_id=trace_id,
        )

        return await self._send(message, to)

    def _create_message(
        self,
        performative: Performative,
        to: str,
        action: str,
        payload: dict,
        conversation_id: Optional[str],
        trace_id: Optional[str],
    ) -> dict:
        """Create a signed message."""
        message_id = f"msg_{uuid.uuid4().hex[:24]}"
        nonce = generate_nonce()

        if conversation_id is None:
            conversation_id = f"conv_{uuid.uuid4().hex[:24]}"
        if trace_id is None:
            trace_id = f"trace_{uuid.uuid4().hex[:24]}"

        timestamp = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )

        envelope = {
            "protocol_version": "0.1.0",
            "message_id": message_id,
            "sender_did": self.identity.did,
            "receiver_did": to,
            "nonce": nonce,
            "timestamp": timestamp,
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "reply_with": None,
            "in_reply_to": None,
        }

        content = {
            "performative": performative.value,
            "payload": payload,
            "action": action,
        }

        canonical_bytes = canonicalize_for_signing(envelope, content)
        import hashlib

        digest = hashlib.sha256(canonical_bytes).digest()
        signature = self.identity.private_key.sign(digest)

        import base64

        envelope["signature"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

        return {
            "envelope": envelope,
            "content": content,
        }

    async def _send(self, message: dict, to_did: str) -> dict:
        """Send message via A2A transport.

        For now, this is a stub that would use the A2A SDK.
        In production, this would:
        1. Look up the receiver's Agent Card
        2. Get their A2A endpoint
        3. Send via JSON-RPC over HTTP
        4. Handle response
        """
        # TODO: Integrate with google-a2a SDK
        # For now, return the message we created
        return {
            "status": "sent",
            "message": message,
            "to": to_did,
        }


async def discover_agent(agent_url: str) -> Optional[dict]:
    """Discover an agent's capabilities via their Agent Card.

    Args:
        agent_url: The base URL of the agent

    Returns:
        The agent's card data or None if not found
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{agent_url}/.well-known/agent.json",
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass

    return None
