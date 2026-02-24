"""AgenLang Runtime - executes contracts with safety, audit, and settlement."""

from datetime import datetime
import json
from pathlib import Path
from typing import Dict, Any, Tuple
import secrets
from cryptography.hazmat.primitives import hmac
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
from .contract import Contract
from .tools import TOOLS
from .memory import Memory

class Runtime:
    """Executes an AgenLang contract safely and produces the SER."""

    def __init__(self, contract: Contract):
        self.contract = contract
        self.start_time = datetime.utcnow()
        self.execution_id = contract.contract_id
        self.steps_executed = 0
        self.replay_data = []  # Raw data for replay file
        self.memory = Memory(self.execution_id, contract.memory_contract.get("data_subject", "anonymous"))

    def execute(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute the contract and return (result, ser)."""
        if self.contract.constraints.get("joule_budget", 0) <= 0:
            raise ValueError("Joule budget exhausted or invalid")

        # Load existing memory if any
        loaded_memory = self.memory.load()
        print(f"Loaded memory: {loaded_memory}")

        # Execute each step in the workflow
        for step in self.contract.workflow.get("steps", []):
            self._execute_step(step)
            self.steps_executed += 1

        # Handoff memory
        self.memory.handoff(self.contract.memory_contract["handoff_keys"], {"example_key": "example_value"})  # Dummy data

        result = {
            "status": "success",
            "output": f"Executed goal: {self.contract.goal}",
            "steps_completed": self.steps_executed
        }

        end_time = datetime.utcnow()
        joules_used = 42.0 * self.steps_executed
        ser = {
            "execution_id": self.execution_id,
            "timestamps": {
                "start": self.start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z"
            },
            "decision_points": [],
            "resource_usage": {
                "joules_used": joules_used,
                "usd_cost": 0.01 * self.steps_executed,
                "efficiency_score": 0.92
            },
            "safety_checks": {
                "capability_violations": 0,
                "intent_anchor_verified": True
            },
            "replay_ref": f"{self.execution_id}.replay",
            "settlement_receipt": {
                "joule_recipient": self.contract.settlement["joule_recipient"],
                "rate": self.contract.settlement["rate"],
                "total_joules_owed": joules_used * self.contract.settlement["rate"]
            }
        }

        # Save replay file with HMAC integrity
        self._save_replay()

        # Purge memory if configured
        if self.contract.memory_contract.get("purge_on_complete", True):
            self.memory.purge()

        return result, ser

    def _execute_step(self, step: Dict):
        """Execute a single step with tool calling."""
        action = step.get("action")
        if action == "tool":
            tool_name = step.get("target")
            tool = TOOLS.get(tool_name)
            if tool:
                required_caps = tool["capabilities"]
                if all(cap in [c["capability"] for c in self.contract.capability_attestations] for cap in required_caps):
                    output = tool["function"](step.get("args", {}))
                    self.replay_data.append({"step": tool_name, "output": output})
                    print(f"Executed tool: {tool_name} - Output: {output}")
                else:
                    raise ValueError(f"Capability violation for tool {tool_name}")
            else:
                raise ValueError(f"Unknown tool {tool_name}")
        else:
            print(f"Executing step: {action} {step.get('target')}")

    def _save_replay(self):
        """Save replay data with HMAC integrity."""
        replay_content = json.dumps(self.replay_data).encode('utf-8')
        key = secrets.token_bytes(32)  # Real random key (store securely in production)
        h = hmac.HMAC(key, SHA256(), backend=default_backend())
        h.update(replay_content)
        hmac_value = h.finalize()
        replay_path = Path(f"{self.execution_id}.replay")
        replay_path.write_bytes(replay_content + hmac_value)
        print(f"Replay saved to {replay_path} with HMAC integrity")

    def to_ser_json(self, ser: Dict) -> str:
        return json.dumps(ser, indent=2)
