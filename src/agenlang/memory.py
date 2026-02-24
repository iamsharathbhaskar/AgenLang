"""AgenLang Memory - handoff and purge with GDPR compliance."""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timedelta
import json

class Memory:
    """Handles memory handoff and purge."""

    def __init__(self, contract_id: str, data_subject: str):
        self.contract_id = contract_id
        self.data_subject = data_subject
        self.memory_path = Path(f"{contract_id}.memory.json")

    def handoff(self, keys: list, data: Dict[str, Any]):
        """Save whitelisted memory keys."""
        whitelisted_data = {k: data.get(k) for k in keys}
        self.memory_path.write_text(json.dumps(whitelisted_data))

    def load(self) -> Dict[str, Any]:
        """Load memory."""
        if self.memory_path.exists():
            return json.loads(self.memory_path.read_text())
        return {}

    def purge(self):
        """Purge memory for GDPR compliance."""
        if self.memory_path.exists():
            self.memory_path.unlink()
            print(f"Purged memory for data_subject: {self.data_subject}")
