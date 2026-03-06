"""AgenLang Contract Template System.

This module provides a complete template system for AgenLang contracts including:
- Template schema definition with JSON/YAML support
- Variable substitution using Jinja2-style {{variable}} syntax
- Template inheritance with base templates and overrides
- Schema validation before contract generation
- Local file storage in ~/.agenlang/templates/

Example:
    >>> from agenlang.template import TemplateEngine
    >>> engine = TemplateEngine()
    >>> contract = engine.render_contract("simple-agent", {
    ...     "goal": "Research quantum computing",
    ...     "joule_budget": 1000
    ... })
"""

import json
import re
import secrets
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

import structlog
import yaml
from jinja2 import Environment, BaseLoader, TemplateError as JinjaTemplateError
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field, field_validator

from .contract import Contract, _load_schema

logger = structlog.get_logger()

# Default template storage location
DEFAULT_TEMPLATE_DIR = Path.home() / ".agenlang" / "templates"

# Variable pattern: {{variable}} or {{ variable }}
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Template schema version
TEMPLATE_SCHEMA_VERSION = "1.0"


class TemplateVariable(BaseModel):
    """Definition of a template variable.
    
    Attributes:
        name: Variable name (used in {{name}} syntax)
        description: Human-readable description
        type: Data type (string, integer, float, boolean, list, dict)
        required: Whether this variable must be provided
        default: Default value if not provided
        example: Example value for documentation
    """
    name: str
    description: str
    type: str = "string"
    required: bool = True
    default: Optional[Any] = None
    example: Optional[Any] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"string", "integer", "float", "boolean", "list", "dict", "enum"}
        if v not in allowed:
            raise ValueError(f"Type must be one of: {allowed}")
        return v


class TemplateMetadata(BaseModel):
    """Template metadata and documentation.
    
    Attributes:
        name: Template name (unique identifier)
        version: Template version (semver)
        description: Short description
        author: Template author
        created: Creation timestamp
        updated: Last update timestamp
        tags: List of searchable tags
        category: Template category
        parent: Parent template name (for inheritance)
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    created: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: List[str] = Field(default_factory=list)
    category: str = "general"
    parent: Optional[str] = None


class ContractTemplate(BaseModel):
    """AgenLang contract template definition.
    
    Attributes:
        schema_version: Template schema version
        metadata: Template metadata
        variables: Template variable definitions
        template: The contract template with {{variables}}
    """
    schema_version: str = TEMPLATE_SCHEMA_VERSION
    metadata: TemplateMetadata
    variables: List[TemplateVariable] = Field(default_factory=list)
    template: Dict[str, Any]

    def get_variable(self, name: str) -> Optional[TemplateVariable]:
        """Get variable definition by name."""
        for var in self.variables:
            if var.name == name:
                return var
        return None

    def get_required_variables(self) -> List[TemplateVariable]:
        """Get list of required variables."""
        return [v for v in self.variables if v.required and v.default is None]

    def validate_variables(self, values: Dict[str, Any]) -> List[str]:
        """Validate provided variable values.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for var in self.variables:
            if var.name not in values:
                if var.required and var.default is None:
                    errors.append(f"Missing required variable: {var.name}")
                continue
            
            value = values[var.name]
            
            # Type validation
            if var.type == "string" and not isinstance(value, str):
                errors.append(f"Variable {var.name} must be a string")
            elif var.type == "integer" and not isinstance(value, int):
                errors.append(f"Variable {var.name} must be an integer")
            elif var.type == "float" and not isinstance(value, (int, float)):
                errors.append(f"Variable {var.name} must be a number")
            elif var.type == "boolean" and not isinstance(value, bool):
                errors.append(f"Variable {var.name} must be a boolean")
            elif var.type == "list" and not isinstance(value, list):
                errors.append(f"Variable {var.name} must be a list")
            elif var.type == "dict" and not isinstance(value, dict):
                errors.append(f"Variable {var.name} must be a dict")
        
        return errors


class TemplateEngine:
    """Core template engine for AgenLang contracts.
    
    Provides template loading, rendering, validation, and storage operations.
    Supports Jinja2-style variable substitution and template inheritance.
    
    Attributes:
        template_dir: Directory where templates are stored
        jinja_env: Jinja2 environment for rendering
    """

    def __init__(self, template_dir: Optional[Union[str, Path]] = None):
        """Initialize the template engine.
        
        Args:
            template_dir: Custom template directory (default: ~/.agenlang/templates)
        """
        self.template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.jinja_env = Environment(loader=BaseLoader(), trim_blocks=True, lstrip_blocks=True)
        self._schema = _load_schema()
        logger.info("template_engine_initialized", template_dir=str(self.template_dir))

    def _generate_contract_id(self) -> str:
        """Generate a unique contract ID."""
        return f"urn:agenlang:exec:{secrets.token_hex(16)}"

    def _resolve_template(self, template_data: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolve template variables in a nested structure.
        
        Args:
            template_data: Template data structure (dict, list, or primitive)
            variables: Variable values to substitute
            
        Returns:
            Resolved data structure with variables replaced
        """
        if isinstance(template_data, dict):
            return {k: self._resolve_template(v, variables) for k, v in template_data.items()}
        elif isinstance(template_data, list):
            return [self._resolve_template(item, variables) for item in template_data]
        elif isinstance(template_data, str):
            return self._render_string(template_data, variables)
        else:
            return template_data

    def _render_string(self, template_str: str, variables: Dict[str, Any]) -> str:
        """Render a string template with Jinja2 variable substitution.
        
        Args:
            template_str: String containing {{variable}} placeholders
            variables: Variable values to substitute
            
        Returns:
            Rendered string with variables replaced
        """
        try:
            template = self.jinja_env.from_string(template_str)
            return template.render(**variables)
        except JinjaTemplateError as e:
            logger.error("template_render_error", error=str(e), template=template_str[:100])
            raise ValueError(f"Template rendering failed: {e}") from e

    def _merge_templates(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two template dictionaries (deep merge).
        
        Override values take precedence over base values.
        
        Args:
            base: Base template dictionary
            override: Override template dictionary
            
        Returns:
            Merged template dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_templates(result[key], value)
            else:
                result[key] = value
        return result

    def load_template(self, name: str) -> ContractTemplate:
        """Load a template by name from storage.
        
        Args:
            name: Template name (filename without extension)
            
        Returns:
            Loaded ContractTemplate instance
            
        Raises:
            FileNotFoundError: If template doesn't exist
            ValueError: If template format is invalid
        """
        # Try YAML first, then JSON
        yaml_path = self.template_dir / f"{name}.yaml"
        json_path = self.template_dir / f"{name}.json"
        
        if yaml_path.exists():
            try:
                data = yaml.safe_load(yaml_path.read_text())
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML template '{name}': {e}") from e
        elif json_path.exists():
            try:
                data = json.loads(json_path.read_text())
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON template '{name}': {e}") from e
        else:
            raise FileNotFoundError(f"Template not found: {name}")
        
        return ContractTemplate.model_validate(data)

    def save_template(self, template: ContractTemplate, format: str = "yaml") -> Path:
        """Save a template to storage.
        
        Args:
            template: Template to save
            format: Output format ('yaml' or 'json')
            
        Returns:
            Path to saved template file
        """
        filename = f"{template.metadata.name}.{format}"
        path = self.template_dir / filename
        
        if format == "yaml":
            content = yaml.safe_dump(template.model_dump(), default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(template.model_dump(), indent=2)
        
        path.write_text(content)
        logger.info("template_saved", name=template.metadata.name, path=str(path))
        return path

    def delete_template(self, name: str) -> bool:
        """Delete a template from storage.
        
        Args:
            name: Template name to delete
            
        Returns:
            True if deleted, False if not found
        """
        yaml_path = self.template_dir / f"{name}.yaml"
        json_path = self.template_dir / f"{name}.json"
        
        deleted = False
        if yaml_path.exists():
            yaml_path.unlink()
            deleted = True
        if json_path.exists():
            json_path.unlink()
            deleted = True
        
        if deleted:
            logger.info("template_deleted", name=name)
        return deleted

    def list_templates(self) -> List[TemplateMetadata]:
        """List all available templates with metadata.
        
        Returns:
            List of template metadata
        """
        templates = []
        seen = set()
        
        for path in self.template_dir.iterdir():
            if path.suffix not in (".yaml", ".yml", ".json"):
                continue
            
            name = path.stem
            if name in seen:
                continue
            seen.add(name)
            
            try:
                template = self.load_template(name)
                templates.append(template.metadata)
            except Exception as e:
                logger.warning("template_load_failed", name=name, error=str(e))
        
        return sorted(templates, key=lambda m: m.name)

    def validate_template(self, name: str) -> List[str]:
        """Validate a template for correctness.
        
        Checks:
        - Template can be loaded
        - All variables are properly defined
        - Template can be rendered with example values
        - Generated contract passes schema validation
        
        Args:
            name: Template name to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        try:
            template = self.load_template(name)
        except Exception as e:
            return [f"Failed to load template: {e}"]
        
        # Check for undefined variables in template
        template_str = json.dumps(template.template)
        referenced_vars = set(VARIABLE_PATTERN.findall(template_str))
        defined_vars = {v.name for v in template.variables}
        
        undefined = referenced_vars - defined_vars
        if undefined:
            errors.append(f"Undefined variables: {', '.join(undefined)}")
        
        # Try to render with example/default values
        test_values = {}
        for var in template.variables:
            if var.example is not None:
                test_values[var.name] = var.example
            elif var.default is not None:
                test_values[var.name] = var.default
            elif var.type == "string":
                test_values[var.name] = f"test_{var.name}"
            elif var.type == "integer":
                test_values[var.name] = 42
            elif var.type == "float":
                test_values[var.name] = 3.14
            elif var.type == "boolean":
                test_values[var.name] = True
            elif var.type == "list":
                test_values[var.name] = []
            elif var.type == "dict":
                test_values[var.name] = {}
        
        try:
            rendered = self.render_contract(name, test_values, validate_schema=False)
        except Exception as e:
            errors.append(f"Render test failed: {e}")
            return errors
        
        # Validate against contract schema
        try:
            contract_dict = json.loads(rendered.to_json())
            validate(instance=contract_dict, schema=self._schema)
        except ValidationError as e:
            errors.append(f"Schema validation failed: {e.message}")
        except Exception as e:
            errors.append(f"Schema validation error: {e}")
        
        return errors

    def render_contract(
        self, 
        template_name: str, 
        variables: Dict[str, Any],
        validate_schema: bool = True
    ) -> Contract:
        """Render a template into a Contract.
        
        Supports template inheritance - if the template has a parent,
        the parent's template is loaded and merged with the child's.
        
        Args:
            template_name: Name of template to render
            variables: Variable values to substitute
            validate_schema: Whether to validate against contract schema
            
        Returns:
            Rendered Contract instance
            
        Raises:
            FileNotFoundError: If template doesn't exist
            ValueError: If variable validation fails or rendering errors occur
        """
        logger.info("rendering_contract", template=template_name, variables=list(variables.keys()))
        
        # Load template with inheritance resolution
        template = self.load_template(template_name)
        template_data = template.template.copy()
        
        # Handle inheritance
        if template.metadata.parent:
            parent = self.load_template(template.metadata.parent)
            template_data = self._merge_templates(parent.template, template_data)
            logger.debug("template_inheritance_applied", parent=template.metadata.parent)
        
        # Validate variables
        validation_errors = template.validate_variables(variables)
        if validation_errors:
            raise ValueError(f"Variable validation failed: {'; '.join(validation_errors)}")
        
        # Apply defaults for missing variables
        for var in template.variables:
            if var.name not in variables and var.default is not None:
                variables[var.name] = var.default
        
        # Resolve variables in template
        resolved = self._resolve_template(template_data, variables)
        
        # Ensure contract_id is present
        if "contract_id" not in resolved or resolved["contract_id"] == "":
            resolved["contract_id"] = self._generate_contract_id()
        
        # Validate against schema if requested
        if validate_schema:
            try:
                validate(instance=resolved, schema=self._schema)
            except ValidationError as e:
                raise ValueError(f"Generated contract failed schema validation: {e.message}") from e
        
        # Create Contract instance
        contract = Contract.from_dict(resolved)
        
        logger.info("contract_rendered", 
                   template=template_name, 
                   contract_id=contract.contract_id)
        
        return contract

    def create_template(
        self,
        name: str,
        description: str,
        template_dict: Dict[str, Any],
        variables: Optional[List[TemplateVariable]] = None,
        parent: Optional[str] = None,
        category: str = "general",
        tags: Optional[List[str]] = None,
        author: str = ""
    ) -> ContractTemplate:
        """Create a new template programmatically.
        
        Args:
            name: Template name (unique identifier)
            description: Template description
            template_dict: The contract template with {{variables}}
            variables: Variable definitions
            parent: Parent template name (for inheritance)
            category: Template category
            tags: Searchable tags
            author: Template author
            
        Returns:
            Created ContractTemplate instance
        """
        metadata = TemplateMetadata(
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            author=author,
            parent=parent
        )
        
        template = ContractTemplate(
            metadata=metadata,
            variables=variables or [],
            template=template_dict
        )
        
        return template

    def export_template(self, name: str, output_path: Union[str, Path], format: str = "yaml") -> Path:
        """Export a template to a file.
        
        Args:
            name: Template name to export
            output_path: Destination path
            format: Output format ('yaml' or 'json')
            
        Returns:
            Path to exported file
        """
        template = self.load_template(name)
        output_path = Path(output_path)
        
        if format == "yaml":
            content = yaml.safe_dump(template.model_dump(), default_flow_style=False, sort_keys=False)
        else:
            content = json.dumps(template.model_dump(), indent=2)
        
        output_path.write_text(content)
        logger.info("template_exported", name=name, path=str(output_path))
        return output_path

    def import_template(self, source_path: Union[str, Path]) -> ContractTemplate:
        """Import a template from a file.
        
        Args:
            source_path: Path to template file
            
        Returns:
            Imported ContractTemplate instance
        """
        source_path = Path(source_path)
        
        if source_path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(source_path.read_text())
        elif source_path.suffix == ".json":
            data = json.loads(source_path.read_text())
        else:
            raise ValueError(f"Unsupported file format: {source_path.suffix}")
        
        template = ContractTemplate.model_validate(data)
        
        # Save to template directory
        self.save_template(template, format="yaml" if source_path.suffix in (".yaml", ".yml") else "json")
        
        logger.info("template_imported", name=template.metadata.name, source=str(source_path))
        return template


def get_builtin_templates_dir() -> Path:
    """Get the directory containing built-in templates."""
    import importlib.resources
    return importlib.resources.files("agenlang") / "templates"


def install_builtin_templates(template_dir: Optional[Path] = None) -> List[str]:
    """Install built-in templates to the template directory.
    
    Args:
        template_dir: Target directory (default: ~/.agenlang/templates)
        
    Returns:
        List of installed template names
    """
    target_dir = template_dir or DEFAULT_TEMPLATE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        builtin_dir = get_builtin_templates_dir()
    except Exception:
        # Package not installed or templates not included
        logger.warning("builtin_templates_not_found")
        return []
    
    installed = []
    for source_file in builtin_dir.iterdir():
        if source_file.suffix not in (".yaml", ".yml", ".json"):
            continue
        
        target_file = target_dir / source_file.name
        shutil.copy2(source_file, target_file)
        installed.append(source_file.stem)
    
    logger.info("builtin_templates_installed", count=len(installed), templates=installed)
    return installed
