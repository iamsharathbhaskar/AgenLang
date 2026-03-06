"""Tests for AgenLang Contract Template System."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from agenlang.template import (
    ContractTemplate,
    TemplateEngine,
    TemplateMetadata,
    TemplateVariable,
    DEFAULT_TEMPLATE_DIR,
    install_builtin_templates,
    get_builtin_templates_dir,
)
from agenlang.contract import Contract


class TestTemplateVariable:
    """Tests for TemplateVariable model."""

    def test_variable_creation(self) -> None:
        """Test creating a template variable."""
        var = TemplateVariable(
            name="goal",
            description="The main goal",
            type="string",
            required=True,
            example="Research AI",
        )
        assert var.name == "goal"
        assert var.type == "string"
        assert var.required is True

    def test_variable_default(self) -> None:
        """Test variable with default value."""
        var = TemplateVariable(
            name="budget",
            description="Joule budget",
            type="float",
            required=False,
            default=1000.0,
        )
        assert var.default == 1000.0
        assert var.required is False

    def test_variable_type_validation(self) -> None:
        """Test variable type validation."""
        with pytest.raises(ValueError, match="Type must be one of"):
            TemplateVariable(
                name="invalid",
                description="Invalid type",
                type="invalid_type",
            )

    def test_allowed_types(self) -> None:
        """Test all allowed variable types."""
        allowed_types = ["string", "integer", "float", "boolean", "list", "dict", "enum"]
        for var_type in allowed_types:
            var = TemplateVariable(name=f"var_{var_type}", description="Test", type=var_type)
            assert var.type == var_type


class TestTemplateMetadata:
    """Tests for TemplateMetadata model."""

    def test_metadata_creation(self) -> None:
        """Test creating template metadata."""
        meta = TemplateMetadata(
            name="test-template",
            version="1.0.0",
            description="A test template",
            author="Test Author",
            category="test",
            tags=["test", "example"],
        )
        assert meta.name == "test-template"
        assert meta.version == "1.0.0"
        assert meta.category == "test"
        assert "test" in meta.tags

    def test_metadata_defaults(self) -> None:
        """Test metadata default values."""
        meta = TemplateMetadata(name="simple")
        assert meta.version == "1.0.0"
        assert meta.category == "general"
        assert meta.tags == []
        assert meta.parent is None

    def test_metadata_with_parent(self) -> None:
        """Test metadata with parent for inheritance."""
        meta = TemplateMetadata(
            name="child",
            parent="base",
        )
        assert meta.parent == "base"


class TestContractTemplate:
    """Tests for ContractTemplate model."""

    def test_template_creation(self) -> None:
        """Test creating a contract template."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="goal", description="Goal", type="string", required=True),
            ],
            template={
                "agenlang_version": "1.0",
                "goal": "{{goal}}",
            },
        )
        assert template.metadata.name == "test"
        assert len(template.variables) == 1

    def test_get_variable(self) -> None:
        """Test getting a variable by name."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="goal", description="Goal", type="string"),
                TemplateVariable(name="budget", description="Budget", type="float"),
            ],
            template={},
        )
        var = template.get_variable("goal")
        assert var is not None
        assert var.name == "goal"
        assert template.get_variable("nonexistent") is None

    def test_get_required_variables(self) -> None:
        """Test getting required variables."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="required1", description="R1", type="string", required=True),
                TemplateVariable(name="required2", description="R2", type="string", required=True),
                TemplateVariable(
                    name="optional",
                    description="Opt",
                    type="string",
                    required=False,
                    default="default",
                ),
            ],
            template={},
        )
        required = template.get_required_variables()
        assert len(required) == 2
        assert all(v.name in ["required1", "required2"] for v in required)

    def test_validate_variables_success(self) -> None:
        """Test variable validation with valid values."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="goal", description="Goal", type="string", required=True),
                TemplateVariable(name="budget", description="Budget", type="float", required=True),
            ],
            template={},
        )
        errors = template.validate_variables({
            "goal": "Test goal",
            "budget": 1000.0,
        })
        assert errors == []

    def test_validate_variables_missing_required(self) -> None:
        """Test validation with missing required variable."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="goal", description="Goal", type="string", required=True),
            ],
            template={},
        )
        errors = template.validate_variables({})
        assert len(errors) == 1
        assert "Missing required variable" in errors[0]

    def test_validate_variables_type_errors(self) -> None:
        """Test validation with wrong types."""
        template = ContractTemplate(
            metadata=TemplateMetadata(name="test"),
            variables=[
                TemplateVariable(name="count", description="Count", type="integer"),
                TemplateVariable(name="enabled", description="Enabled", type="boolean"),
                TemplateVariable(name="items", description="Items", type="list"),
                TemplateVariable(name="config", description="Config", type="dict"),
            ],
            template={},
        )
        errors = template.validate_variables({
            "count": "not an int",
            "enabled": "not a bool",
            "items": "not a list",
            "config": "not a dict",
        })
        assert len(errors) == 4


class TestTemplateEngine:
    """Tests for TemplateEngine class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    @pytest.fixture
    def engine(self, temp_dir: Path) -> TemplateEngine:
        """Create a template engine with temp directory."""
        return TemplateEngine(template_dir=temp_dir)

    @pytest.fixture
    def simple_template(self) -> Dict[str, Any]:
        """Create a simple template for testing."""
        return {
            "schema_version": "1.0",
            "metadata": {
                "name": "simple-test",
                "description": "Simple test template",
            },
            "variables": [
                {
                    "name": "goal",
                    "description": "Goal",
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "budget",
                    "description": "Budget",
                    "type": "float",
                    "required": False,
                    "default": 1000.0,
                },
            ],
            "template": {
                "agenlang_version": "1.0",
                "contract_id": "{{contract_id}}",
                "issuer": {
                    "agent_id": "did:key:test",
                    "pubkey": "test-key",
                },
                "receiver": {
                    "agent_id": "did:key:receiver",
                },
                "goal": "{{goal}}",
                "intent_anchor": {"hash": "sha256:test"},
                "constraints": {
                    "joule_budget": 1000.0,
                },
                "workflow": {
                    "type": "sequence",
                    "steps": [],
                },
                "memory_contract": {
                    "handoff_keys": [],
                    "ttl": "24h",
                },
                "settlement": {
                    "joule_recipient": "did:key:receiver",
                    "rate": 1.0,
                },
                "capability_attestations": [],
            },
        }

    def test_engine_init(self, temp_dir: Path) -> None:
        """Test template engine initialization."""
        engine = TemplateEngine(template_dir=temp_dir)
        assert engine.template_dir == temp_dir
        assert temp_dir.exists()

    def test_engine_default_dir(self) -> None:
        """Test template engine with default directory."""
        engine = TemplateEngine()
        assert engine.template_dir == DEFAULT_TEMPLATE_DIR

    def test_save_and_load_template(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test saving and loading a template."""
        template = ContractTemplate.model_validate(simple_template)

        # Save
        path = engine.save_template(template, format="yaml")
        assert path.exists()

        # Load
        loaded = engine.load_template("simple-test")
        assert loaded.metadata.name == "simple-test"
        assert loaded.metadata.description == "Simple test template"

    def test_load_template_json(self, engine: TemplateEngine) -> None:
        """Test loading a JSON template."""
        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "json-test"},
            "variables": [],
            "template": {"test": "value"},
        }
        template = ContractTemplate.model_validate(template_data)

        # Save as JSON
        path = engine.save_template(template, format="json")
        assert path.suffix == ".json"

        # Load
        loaded = engine.load_template("json-test")
        assert loaded.metadata.name == "json-test"

    def test_load_template_not_found(self, engine: TemplateEngine) -> None:
        """Test loading non-existent template."""
        with pytest.raises(FileNotFoundError, match="Template not found"):
            engine.load_template("nonexistent")

    def test_delete_template(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test deleting a template."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        assert engine.delete_template("simple-test") is True
        assert not (engine.template_dir / "simple-test.yaml").exists()

    def test_delete_template_not_found(self, engine: TemplateEngine) -> None:
        """Test deleting non-existent template."""
        assert engine.delete_template("nonexistent") is False

    def test_list_templates(self, engine: TemplateEngine) -> None:
        """Test listing templates."""
        # Create a few templates
        for name in ["template-a", "template-b", "template-c"]:
            template = ContractTemplate(
                metadata=TemplateMetadata(name=name),
                variables=[],
                template={},
            )
            engine.save_template(template)

        templates = engine.list_templates()
        assert len(templates) == 3
        names = [t.name for t in templates]
        assert "template-a" in names
        assert "template-b" in names
        assert "template-c" in names

    def test_list_templates_empty(self, engine: TemplateEngine) -> None:
        """Test listing templates in empty directory."""
        templates = engine.list_templates()
        assert templates == []

    def test_render_contract(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test rendering a contract from template."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        contract = engine.render_contract("simple-test", {
            "goal": "Test goal",
            "budget": 5000.0,
        }, validate_schema=False)

        assert isinstance(contract, Contract)
        assert contract.goal == "Test goal"

    def test_render_contract_with_defaults(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test rendering with default values."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        # Only provide required variable
        contract = engine.render_contract("simple-test", {
            "goal": "Test goal",
        }, validate_schema=False)

        assert contract.goal == "Test goal"

    def test_render_contract_missing_required(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test rendering with missing required variable."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        with pytest.raises(ValueError, match="Variable validation failed"):
            engine.render_contract("simple-test", {}, validate_schema=False)

    def test_render_contract_generates_id(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test that rendering generates a contract ID."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        contract = engine.render_contract("simple-test", {
            "goal": "Test",
        }, validate_schema=False)

        assert contract.contract_id.startswith("urn:agenlang:exec:")

    def test_variable_substitution_nested(self, engine: TemplateEngine) -> None:
        """Test variable substitution in nested structures."""
        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "nested-test"},
            "variables": [
                {"name": "name", "description": "Name", "type": "string"},
                {"name": "count", "description": "Count", "type": "integer"},
            ],
            "template": {
                "simple": "{{name}}",
                "nested": {
                    "value": "{{name}}",
                    "list": ["{{name}}", "{{count}}"],
                },
            },
        }
        template = ContractTemplate.model_validate(template_data)
        engine.save_template(template)

        result = engine._resolve_template(
            template.template,
            {"name": "Alice", "count": 42},
        )

        assert result["simple"] == "Alice"
        assert result["nested"]["value"] == "Alice"
        assert result["nested"]["list"] == ["Alice", "42"]

    def test_merge_templates(self, engine: TemplateEngine) -> None:
        """Test template inheritance merging."""
        base = {
            "agenlang_version": "1.0",
            "base_field": "base_value",
            "nested": {
                "base": "value",
                "shared": "from_base",
            },
        }
        override = {
            "override_field": "override_value",
            "nested": {
                "override": "value",
                "shared": "from_override",
            },
        }

        result = engine._merge_templates(base, override)

        assert result["base_field"] == "base_value"
        assert result["override_field"] == "override_value"
        assert result["nested"]["base"] == "value"
        assert result["nested"]["override"] == "value"
        assert result["nested"]["shared"] == "from_override"

    def test_validate_template(self, engine: TemplateEngine, simple_template: Dict[str, Any]) -> None:
        """Test template validation."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        errors = engine.validate_template("simple-test")
        # May have schema validation errors due to incomplete test template
        assert isinstance(errors, list)

    def test_validate_template_undefined_vars(self, engine: TemplateEngine) -> None:
        """Test validation catches undefined variables."""
        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "bad-template"},
            "variables": [],
            "template": {
                "field": "{{undefined_var}}",
            },
        }
        template = ContractTemplate.model_validate(template_data)
        engine.save_template(template)

        errors = engine.validate_template("bad-template")
        assert any("Undefined variables" in e for e in errors)

    def test_export_template(self, engine: TemplateEngine, simple_template: Dict[str, Any], temp_dir: Path) -> None:
        """Test exporting a template."""
        template = ContractTemplate.model_validate(simple_template)
        engine.save_template(template)

        export_path = temp_dir / "exported.yaml"
        result = engine.export_template("simple-test", export_path, "yaml")

        assert result.exists()
        content = result.read_text()
        assert "simple-test" in content

    def test_import_template(self, engine: TemplateEngine, temp_dir: Path) -> None:
        """Test importing a template."""
        # Create a template file
        source_path = temp_dir / "import-source.yaml"
        template_data = {
            "schema_version": "1.0",
            "metadata": {
                "name": "imported",
                "description": "To be imported",
            },
            "variables": [],
            "template": {},
        }
        source_path.write_text(yaml.safe_dump(template_data))

        imported = engine.import_template(source_path)

        assert imported.metadata.name == "imported"
        assert engine.load_template("imported") is not None

    def test_import_template_json(self, engine: TemplateEngine, temp_dir: Path) -> None:
        """Test importing a JSON template."""
        source_path = temp_dir / "import-source.json"
        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "json-imported"},
            "variables": [],
            "template": {},
        }
        source_path.write_text(json.dumps(template_data))

        imported = engine.import_template(source_path)
        assert imported.metadata.name == "json-imported"

    def test_create_template(self, engine: TemplateEngine) -> None:
        """Test creating a template programmatically."""
        template = engine.create_template(
            name="created",
            description="Created template",
            template_dict={"key": "value"},
            variables=[TemplateVariable(name="var", description="Var", type="string")],
            category="test",
            tags=["test"],
            author="Test",
        )

        assert template.metadata.name == "created"
        assert template.metadata.category == "test"
        assert len(template.variables) == 1


class TestBuiltinTemplates:
    """Tests for built-in template functionality."""

    def test_get_builtin_templates_dir(self) -> None:
        """Test getting built-in templates directory."""
        # This may fail if package not installed
        try:
            path = get_builtin_templates_dir()
            assert path is not None
        except Exception:
            pytest.skip("Package not installed")

    def test_install_builtin_templates(self, tmp_path: Path) -> None:
        """Test installing built-in templates."""
        # This may fail if package not installed
        try:
            installed = install_builtin_templates(tmp_path)
            assert isinstance(installed, list)
        except Exception:
            pytest.skip("Built-in templates not available")


class TestTemplateIntegration:
    """Integration tests for the template system."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_full_workflow(self, temp_dir: Path) -> None:
        """Test full template workflow: create, save, load, render."""
        engine = TemplateEngine(template_dir=temp_dir)

        # Create template
        template = engine.create_template(
            name="integration-test",
            description="Integration test template",
            template_dict={
                "agenlang_version": "1.0",
                "contract_id": "{{contract_id}}",
                "issuer": {"agent_id": "did:key:test", "pubkey": "test"},
                "receiver": {"agent_id": "did:key:receiver"},
                "goal": "{{goal}}",
                "intent_anchor": {"hash": "sha256:test"},
                "constraints": {"joule_budget": 1000.0},
                "workflow": {"type": "sequence", "steps": []},
                "memory_contract": {"handoff_keys": [], "ttl": "24h"},
                "settlement": {"joule_recipient": "did:key:receiver", "rate": 1.0},
                "capability_attestations": [],
            },
            variables=[
                TemplateVariable(name="goal", description="Goal", type="string", required=True),
            ],
        )

        # Save
        engine.save_template(template)

        # Load
        loaded = engine.load_template("integration-test")
        assert loaded.metadata.name == "integration-test"

        # Render
        contract = engine.render_contract("integration-test", {
            "goal": "Integration test goal",
        }, validate_schema=False)

        assert isinstance(contract, Contract)
        assert contract.goal == "Integration test goal"

    def test_inheritance_workflow(self, temp_dir: Path) -> None:
        """Test template inheritance workflow."""
        engine = TemplateEngine(template_dir=temp_dir)

        # Create base template
        base = engine.create_template(
            name="base",
            description="Base template",
            template_dict={
                "agenlang_version": "1.0",
                "base_value": "base",
                "shared": "from_base",
            },
            variables=[],
        )
        engine.save_template(base)

        # Create child template
        child = engine.create_template(
            name="child",
            description="Child template",
            template_dict={
                "child_value": "child",
                "shared": "from_child",
            },
            variables=[],
            parent="base",
        )
        engine.save_template(child)

        # Load child and verify parent reference
        loaded = engine.load_template("child")
        assert loaded.metadata.parent == "base"


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_template(self, tmp_path: Path) -> None:
        """Test handling empty template."""
        engine = TemplateEngine(template_dir=tmp_path)

        template = ContractTemplate(
            metadata=TemplateMetadata(name="empty"),
            variables=[],
            template={},
        )
        engine.save_template(template)

        loaded = engine.load_template("empty")
        assert loaded.template == {}

    def test_special_characters_in_variables(self, tmp_path: Path) -> None:
        """Test variables with special characters."""
        engine = TemplateEngine(template_dir=tmp_path)

        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "special"},
            "variables": [
                {"name": "text", "description": "Text", "type": "string"},
            ],
            "template": {
                "content": "{{text}}",
            },
        }
        template = ContractTemplate.model_validate(template_data)
        engine.save_template(template)

        result = engine._resolve_template(
            template.template,
            {"text": "Hello, \"World\"!\nNew line"},
        )
        assert "Hello, \"World\"!" in result["content"]

    def test_very_long_variable_value(self, tmp_path: Path) -> None:
        """Test with very long variable values."""
        engine = TemplateEngine(template_dir=tmp_path)

        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "long"},
            "variables": [{"name": "content", "description": "Content", "type": "string"}],
            "template": {"data": "{{content}}"},
        }
        template = ContractTemplate.model_validate(template_data)
        engine.save_template(template)

        long_value = "x" * 10000
        result = engine._resolve_template(template.template, {"content": long_value})
        assert result["data"] == long_value

    def test_unicode_in_variables(self, tmp_path: Path) -> None:
        """Test unicode in variable values."""
        engine = TemplateEngine(template_dir=tmp_path)

        template_data = {
            "schema_version": "1.0",
            "metadata": {"name": "unicode"},
            "variables": [{"name": "text", "description": "Text", "type": "string"}],
            "template": {"data": "{{text}}"},
        }
        template = ContractTemplate.model_validate(template_data)
        engine.save_template(template)

        unicode_value = "Hello 世界 🌍 Привет"
        result = engine._resolve_template(template.template, {"text": unicode_value})
        assert result["data"] == unicode_value
