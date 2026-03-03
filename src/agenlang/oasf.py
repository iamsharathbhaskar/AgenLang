"""OASF (Open Agent Schema Framework) adapter.

Generates OASF manifests from the AgenLang JSON schema, maps contracts
to OASF task descriptors, and converts manifests to A2A-style agent cards.
"""

import importlib.resources
import json
from typing import Any, Dict

import structlog

log = structlog.get_logger()


def generate_oasf_manifest(
    schema_path: str | None = None,
) -> Dict[str, Any]:
    """Generate an OASF manifest from the AgenLang v1.0 JSON schema.

    Args:
        schema_path: Optional path to schema file. If None, uses the
            bundled schema/v1.0.json from the package.

    Returns:
        OASF manifest dict with name, version, description,
        capabilities, inputs, and outputs.
    """
    if schema_path:
        with open(schema_path) as f:
            schema = json.load(f)
    else:
        ref = importlib.resources.files("agenlang") / "schema" / "v1.0.json"
        schema = json.loads(ref.read_text(encoding="utf-8"))

    props = schema.get("properties", {})
    workflow_props = (
        props.get("workflow", {})
        .get("properties", {})
        .get("steps", {})
        .get("items", {})
        .get("properties", {})
    )
    actions = workflow_props.get("action", {}).get("enum", []) if workflow_props else []

    capabilities = []
    for action in actions:
        capabilities.append(
            {
                "name": action,
                "description": f"Execute {action} workflow step",
            }
        )

    return {
        "schema": "oasf/1.0",
        "name": "agenlang",
        "version": schema.get("$id", "").split("/")[-1].replace(".json", ""),
        "title": schema.get("title", "AgenLang Contract"),
        "description": schema.get("description", ""),
        "capabilities": capabilities,
        "inputs": {
            "type": "object",
            "required": schema.get("required", []),
            "properties": {
                k: {"type": v.get("type", "object"), "description": k}
                for k, v in props.items()
            },
        },
        "outputs": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "description": "Execution result with status and output",
                },
                "ser": {
                    "type": "object",
                    "description": "Structured Execution Record (audit trail)",
                },
            },
        },
    }


def contract_to_oasf_task(contract: Any) -> Dict[str, Any]:
    """Map an AgenLang contract to an OASF task descriptor.

    Args:
        contract: AgenLang Contract instance.

    Returns:
        OASF task dict with id, name, description, inputs, and config.
    """
    return {
        "schema": "oasf/task/1.0",
        "id": contract.contract_id,
        "name": f"agenlang:{contract.contract_id}",
        "description": contract.goal,
        "agent": contract.issuer.agent_id,
        "inputs": {
            "goal": contract.goal,
            "constraints": {
                "joule_budget": contract.constraints.joule_budget,
                "pii_level": contract.constraints.pii_level,
            },
        },
        "workflow": {
            "type": contract.workflow.type,
            "step_count": len(contract.workflow.steps),
        },
        "settlement": {
            "recipient": contract.settlement.joule_recipient,
            "rate": contract.settlement.rate,
        },
    }


def oasf_manifest_to_agent_card(
    manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Convert an OASF manifest to an A2A-style agent card.

    Args:
        manifest: OASF manifest dict. If None, generates a fresh one.

    Returns:
        A2A agent card dict.
    """
    if manifest is None:
        manifest = generate_oasf_manifest()

    skills = []
    for cap in manifest.get("capabilities", []):
        skills.append(
            {
                "id": cap["name"],
                "name": cap["name"],
                "description": cap.get("description", ""),
            }
        )

    return {
        "name": manifest.get("name", "agenlang"),
        "description": manifest.get("description", ""),
        "url": "https://agenlang.dev",
        "version": manifest.get("version", "1.0"),
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
        },
        "skills": skills,
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
    }
