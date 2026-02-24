"""AgenLang Contract - loads and validates the v1.0 schema."""

import json
from pathlib import Path
from pydantic import BaseModel, Field
from jsonschema import validate, ValidationError
from typing import Dict, Any, Optional, Literal

# Correct path from inside src/agenlang/ to the root schema folder
SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema" / "v1.0.json"

class Contract(BaseModel):
    """AgenLang v1.0 Contract - the core object agents exchange."""

    agenlang_version: Literal["1.0"] = "1.0"
    contract_id: str
    issuer: Dict[str, Any]
    goal: str
    intent_anchor: Dict[str, Any]
    constraints: Dict[str, Any]
    workflow: Dict[str, Any]
    memory_contract: Dict[str, Any]
    settlement: Dict[str, Any]
    capability_attestations: list
    ser_config: Dict[str, Any]
    ser: Optional[Dict[str, Any]] = None

    @classmethod
    def from_file(cls, path: str) -> "Contract":
        """Load a contract from JSON file and validate against schema."""
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        """Load from dict and validate."""
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        try:
            validate(instance=data, schema=schema)
        except ValidationError as e:
            raise ValueError(f"Invalid AgenLang contract: {e.message}") from e
        return cls(**data)

    def to_json(self) -> str:
        """Export as JSON string."""
        return self.model_dump_json(indent=2)
