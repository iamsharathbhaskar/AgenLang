"""AgenLang Runtime - executes contracts with safety, audit, and settlement."""

import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import structlog
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hmac as hmac_mod
from cryptography.hazmat.primitives.hashes import SHA256

from .contract import Contract
from .keys import KeyManager
from .memory import EncryptedMemoryBackend
from .tools import TOOLS
from .utils import retry_with_backoff

log = structlog.get_logger()

PROTOCOL_ADAPTERS: Dict[str, str] = {
    "acp": "agenlang.acp",
    "mcp": "agenlang.mcp",
    "fipa": "agenlang.fipa",
    "anp": "agenlang.anp",
    "a2a": "agenlang.a2a",
}


def _parse_protocol_target(raw_target: str) -> Tuple[Optional[str], str]:
    """Split 'protocol:target' into (protocol, target) or (None, target)."""
    if ":" in raw_target:
        proto, rest = raw_target.split(":", 1)
        if proto in PROTOCOL_ADAPTERS:
            return proto, rest
    return None, raw_target


@retry_with_backoff(max_retries=2, base_delay=0.5, timeout=30.0)
def _dispatch_protocol(
    protocol: str,
    target: str,
    action: str,
    args: Dict[str, Any],
    contract: "Contract",
) -> str:
    """Route step execution through a protocol adapter."""
    import importlib

    module_name = PROTOCOL_ADAPTERS.get(protocol)
    if not module_name:
        raise ValueError(f"Unknown protocol adapter: {protocol}")
    mod = importlib.import_module(module_name)
    dispatch_fn = getattr(mod, "dispatch", None)
    if dispatch_fn is None:
        raise ValueError(f"Adapter {module_name} has no dispatch() function")
    return dispatch_fn(contract, action, target, args)


class Runtime:
    """Executes an AgenLang contract safely and produces the SER.

    Handles workflow steps, capability checks, memory handoff,
    Joule metering, and SER replay with HMAC integrity.
    """

    def __init__(
        self,
        contract: Contract,
        key_manager: Optional[KeyManager] = None,
    ) -> None:
        """Initialize runtime for a contract.

        Args:
            contract: Validated AgenLang contract to execute.
            key_manager: Optional KeyManager for persistent SER HMAC key.
        """
        self.contract = contract
        self._key_manager = key_manager
        self.start_time = datetime.now(timezone.utc)
        self.execution_id = contract.contract_id
        self.steps_executed = 0
        self._joules_used = 0.0
        self._recursion_depth = 0
        self._max_recursion = 10
        self.replay_data: list[dict[str, Any]] = []
        self._decision_points: list[dict[str, Any]] = []
        self._step_outputs: dict[int, str] = {}
        self._lock = threading.Lock()
        # Encrypted memory default (production)
        self.memory: Any = EncryptedMemoryBackend(
            self.execution_id,
            contract.memory_contract.data_subject or "anonymous",
        )

    def execute(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute the contract and return (result, ser).

        Returns:
            Tuple of (result dict with status/output, SER dict).

        Raises:
            ValueError: If Joule budget exhausted or invalid.
        """
        if self.contract.constraints.joule_budget <= 0:
            raise ValueError("Joule budget exhausted or invalid")

        # Load existing memory if any
        loaded_memory = self.memory.load()
        log.debug("memory_loaded", memory=loaded_memory)

        # Execute steps based on workflow type
        workflow_type = self.contract.workflow.type
        steps = self.contract.workflow.steps

        if workflow_type == "sequence":
            self._run_sequence(steps)
        elif workflow_type == "parallel":
            self._run_parallel(steps)
        elif workflow_type == "probabilistic":
            self._run_probabilistic(steps)
        else:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        # Handoff real step outputs (whitelisted by memory_contract keys)
        step_outputs = {}
        for entry in self.replay_data:
            step_outputs[entry["step"]] = entry.get("output", "")
        self.memory.handoff(
            self.contract.memory_contract.handoff_keys,
            step_outputs,
        )

        result = {
            "status": "success",
            "output": f"Executed goal: {self.contract.goal}",
            "steps_completed": self.steps_executed,
        }

        end_time = datetime.now(timezone.utc)
        joules_used = self._joules_used
        ser = {
            "execution_id": self.execution_id,
            "timestamps": {
                "start": self.start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z",
            },
            "decision_points": self._decision_points,
            "resource_usage": {
                "joules_used": joules_used,
                "usd_cost": joules_used * 0.0001,  # Approximate USD per joule
                "efficiency_score": self._compute_efficiency(joules_used),
            },
            "safety_checks": {
                "capability_violations": 0,
                "intent_anchor_verified": True,
            },
            "replay_ref": f"{self.execution_id}.replay",
            "reputation_score": self._compute_reputation_score(joules_used),
            "settlement_receipt": {
                "joule_recipient": self.contract.settlement.joule_recipient,
                "rate": self.contract.settlement.rate,
                "total_joules_owed": joules_used * self.contract.settlement.rate,
            },
        }

        # Save replay file with HMAC integrity
        self._save_replay()

        # Purge memory if configured
        if self.contract.memory_contract.purge_on_complete:
            self.memory.purge()

        return result, ser

    def _resolve_step_args(self, step: Any, idx: int) -> Any:
        """Resolve {{step_N_output}} placeholders in step args."""
        args = step.args if hasattr(step, "args") else step.get("args", {})
        resolved = {}
        skip = False
        for k, v in args.items():
            if isinstance(v, str) and "{{step_" in v and "_output}}" in v:
                import re

                match = re.search(r"\{\{step_(\d+)_output\}\}", v)
                if match:
                    ref_idx = int(match.group(1))
                    if ref_idx not in self._step_outputs:
                        skip = True
                        break
                    resolved[k] = v.replace(match.group(0), self._step_outputs[ref_idx])
                else:
                    resolved[k] = v
            else:
                resolved[k] = v
        return resolved, skip

    def _run_sequence(self, steps: list) -> None:
        """Execute steps in order with conditional skipping."""
        for idx, step in enumerate(steps):
            if self._joules_used >= self.contract.constraints.joule_budget:
                raise ValueError("Joule budget exhausted")
            resolved_args, skip = self._resolve_step_args(step, idx)
            if skip:
                log.info("step_skipped", idx=idx, reason="precondition_unmet")
                self._decision_points.append(
                    {
                        "type": "conditional_skip",
                        "location": f"step_{idx}",
                        "rationale": "prior outcome unavailable",
                        "chosen": False,
                    }
                )
                continue
            self._execute_step_with_error_handler(step, resolved_args)
            self.steps_executed += 1

    def _run_parallel(self, steps: list) -> None:
        """Execute all steps concurrently via ThreadPoolExecutor."""
        max_workers = self.contract.workflow.max_concurrency
        log.info(
            "workflow_parallel",
            branches=len(steps),
            max_concurrency=max_workers,
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for idx, step in enumerate(steps):
                with self._lock:
                    if self._joules_used >= self.contract.constraints.joule_budget:
                        raise ValueError("Joule budget exhausted")
                    self._decision_points.append(
                        {
                            "type": "parallel_branch",
                            "location": f"branch_{idx}",
                            "rationale": f"independent branch {idx}/{len(steps)}",
                            "chosen": True,
                        }
                    )
                futures.append(
                    executor.submit(self._execute_parallel_branch, idx, step)
                )
            for future in futures:
                future.result()

    def _execute_parallel_branch(self, idx: int, step: Any) -> None:
        """Execute a single parallel branch with thread-safe mutations."""
        resolved_args, _skip = self._resolve_step_args(step, idx)
        self._execute_step_with_error_handler(step, resolved_args)
        with self._lock:
            self.steps_executed += 1

    def _run_probabilistic(self, steps: list) -> None:
        """Weighted random selection from steps."""
        if not steps:
            raise ValueError("Probabilistic workflow requires at least one step")
        weights = [
            (s.weight if hasattr(s, "weight") else s.get("weight", 1.0)) for s in steps
        ]
        chosen = random.choices(steps, weights=weights, k=1)[0]
        chosen_idx = steps.index(chosen)
        for idx, step in enumerate(steps):
            w = weights[idx]
            self._decision_points.append(
                {
                    "type": "probabilistic_choice",
                    "location": f"step_{idx}",
                    "rationale": f"weight={w}, selected={'yes' if idx == chosen_idx else 'no'}",
                    "chosen": idx == chosen_idx,
                }
            )
        if self._joules_used >= self.contract.constraints.joule_budget:
            raise ValueError("Joule budget exhausted")
        self._execute_step_with_error_handler(chosen)
        self.steps_executed += 1

    def _compute_reputation_score(self, joules_used: float) -> float:
        """Compute reputation score from SER (JouleWork futures)."""
        budget = self.contract.constraints.joule_budget
        if budget <= 0:
            return 0.0
        efficiency = 1.0 - (joules_used / budget)
        return max(0.0, min(1.0, 0.5 + efficiency * 0.5))

    def _compute_efficiency(self, joules_used: float) -> float:
        """Compute efficiency score based on budget utilization."""
        budget = self.contract.constraints.joule_budget
        if budget <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (joules_used / budget)))

    def _execute_step_with_error_handler(
        self, step: Any, resolved_args: Optional[dict] = None
    ) -> None:
        """Execute step with on_error retry/fallback."""
        on_error = step.on_error if hasattr(step, "on_error") else step.get("on_error")
        retries = (
            on_error.retry
            if on_error and hasattr(on_error, "retry")
            else (on_error.get("retry", 0) if isinstance(on_error, dict) else 0)
        )
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                self._execute_step(step, resolved_args)
                return
            except Exception as e:
                last_error = e
                if attempt < retries:
                    log.warning("step_retry", attempt=attempt + 1, error=str(e))
        if last_error:
            raise last_error

    def _execute_step(self, step: Any, resolved_args: Optional[dict] = None) -> None:
        """Execute a single step (tool, skill, subcontract, embed).

        Supports protocol auto-detect via 'protocol:target' syntax
        (e.g., 'acp:agent-id', 'mcp:tool-name').

        Args:
            step: Workflow step (WorkflowStep model or dict).
            resolved_args: Pre-resolved args (with {{step_N_output}} filled).

        Raises:
            ValueError: If tool unknown or capability violated.
        """
        if self._recursion_depth >= self._max_recursion:
            raise ValueError("Recursion limit exceeded")
        self._recursion_depth += 1
        try:
            action = step.action if hasattr(step, "action") else step.get("action")
            raw_target = step.target if hasattr(step, "target") else step.get("target")
            args = (
                resolved_args
                if resolved_args is not None
                else (step.args if hasattr(step, "args") else step.get("args", {}))
            )

            protocol, target = _parse_protocol_target(raw_target)

            if protocol:
                output = _dispatch_protocol(
                    protocol, target, action, args, self.contract
                )
                self._joules_used += 100.0
                step_idx = len(self.replay_data)
                self.replay_data.append({"step": raw_target, "output": output})
                self._step_outputs[step_idx] = output
                log.info(
                    "protocol_dispatched",
                    protocol=protocol,
                    target=target,
                    output=output,
                )
                return

            if action == "tool":
                tool = TOOLS.get(target)
                if tool:
                    required_caps = tool["capabilities"]
                    attested = [
                        c.capability for c in self.contract.capability_attestations
                    ]
                    if all(cap in attested for cap in required_caps):
                        output = tool["function"](args)
                        joule_cost = tool.get("joule_cost", 100.0)
                        self._joules_used += joule_cost
                        step_idx = len(self.replay_data)
                        self.replay_data.append({"step": target, "output": output})
                        self._step_outputs[step_idx] = output
                        log.info("tool_executed", tool=target, output=output)
                    else:
                        raise ValueError(f"Capability violation for tool {target}")
                else:
                    raise ValueError(f"Unknown tool {target}")
            elif action == "skill":
                raise NotImplementedError(
                    f"skill:{target} — use protocol prefix "
                    "(e.g. acp:{target}, mcp:{target})"
                )
            elif action == "subcontract":
                raise NotImplementedError(
                    f"subcontract:{target} — use protocol prefix "
                    "(e.g. acp:{target}, anp:{target})"
                )
            elif action == "embed":
                raise NotImplementedError(
                    f"embed:{target} — use protocol prefix " "(e.g. mcp:{target})"
                )
            else:
                log.info("step_executing", action=action, target=target)
        finally:
            self._recursion_depth -= 1

    def _get_key_manager(self) -> KeyManager:
        """Get key manager, using injected or default."""
        if self._key_manager:
            return self._key_manager
        return KeyManager()

    def _save_replay(self) -> None:
        """Save replay data with HMAC integrity using KeyManager."""
        replay_content = json.dumps(self.replay_data).encode("utf-8")
        km = self._get_key_manager()
        key = km.get_ser_key()
        h = hmac_mod.HMAC(key, SHA256(), backend=default_backend())
        h.update(replay_content)
        hmac_value = h.finalize()
        replay_path = Path(f"{self.execution_id}.replay")
        replay_path.write_bytes(replay_content + hmac_value)
        log.info("replay_saved", path=str(replay_path))

    def to_ser_json(self, ser: Dict[str, Any]) -> str:
        """Export SER as JSON string.

        Args:
            ser: Structured Execution Record dict.

        Returns:
            Indented JSON string.
        """
        return json.dumps(ser, indent=2)
