"""CLI commands for AgenLang Contract Templates.

This module provides Click commands for template management:
- create: Create a new template interactively
- list: List available templates
- use: Render a template to create a contract
- validate: Validate a template
- show: Show template details
- export: Export a template to a file
- import: Import a template from a file
- delete: Delete a template
- install: Install built-in templates
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click
import structlog
import yaml

from .template import (
    ContractTemplate,
    TemplateEngine,
    TemplateMetadata,
    TemplateVariable,
    install_builtin_templates,
)

logger = structlog.get_logger()


@click.group(name="template")
def template_group() -> None:
    """Manage AgenLang contract templates."""
    pass


@template_group.command(name="create")
@click.option("--name", "-n", required=True, help="Template name (unique identifier)")
@click.option("--description", "-d", default="", help="Template description")
@click.option("--category", "-c", default="general", help="Template category")
@click.option("--parent", "-p", help="Parent template for inheritance")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml", help="Output format")
@click.option("--from-contract", "-f", type=click.Path(exists=True), help="Create template from existing contract file")
@click.option("--output", "-o", type=click.Path(), help="Output file path (default: ~/.agenlang/templates/)")
def create_template(
    name: str,
    description: str,
    category: str,
    parent: Optional[str],
    fmt: str,
    from_contract: Optional[str],
    output: Optional[str],
) -> None:
    """Create a new contract template.
    
    Creates an interactive prompt to define variables and build a template.
    If --from-contract is provided, extracts template from an existing contract.
    """
    log = structlog.get_logger()
    engine = TemplateEngine()
    
    try:
        if from_contract:
            # Create template from existing contract
            click.echo(f"Creating template from contract: {from_contract}")
            contract_data = json.loads(Path(from_contract).read_text())
            
            # Detect variables from contract content
            template_dict, variables = _extract_variables_from_contract(contract_data)
            
            click.echo(f"\nDetected {len(variables)} potential variables:")
            for var in variables:
                click.echo(f"  - {var.name}: {var.description}")
        else:
            # Interactive template creation
            template_dict = _interactive_template_builder()
            variables = _interactive_variable_builder()
        
        # Create template
        template = engine.create_template(
            name=name,
            description=description or click.prompt("Description", default=f"Template for {name}"),
            template_dict=template_dict,
            variables=variables,
            parent=parent,
            category=category,
            author="",  # Could be populated from config
        )
        
        # Save template
        if output:
            output_path = Path(output)
            if fmt == "yaml":
                content = yaml.safe_dump(template.model_dump(), default_flow_style=False, sort_keys=False)
            else:
                content = json.dumps(template.model_dump(), indent=2)
            output_path.write_text(content)
            click.echo(f"Template saved to: {output_path}")
        else:
            path = engine.save_template(template, format=fmt)
            click.echo(f"Template saved to: {path}")
        
        log.info("template_created", name=name, category=category)
        click.echo(f"\n✓ Template '{name}' created successfully!")
        
        if parent:
            click.echo(f"  Parent: {parent}")
        click.echo(f"  Variables: {len(variables)}")
        
    except Exception as e:
        log.error("template_create_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def list_templates(category: Optional[str], tag: Optional[str], json_output: bool) -> None:
    """List available contract templates."""
    try:
        engine = TemplateEngine()
        templates = engine.list_templates()
        
        # Apply filters
        if category:
            templates = [t for t in templates if t.category == category]
        if tag:
            templates = [t for t in templates if tag in t.tags]
        
        if json_output:
            click.echo(json.dumps([t.model_dump() for t in templates], indent=2))
            return
        
        if not templates:
            click.echo("No templates found.")
            click.echo(f"\nInstall built-in templates with: agenlang template install")
            return
        
        click.echo(f"\n{'Name':<25} {'Category':<15} {'Version':<10} {'Description'}")
        click.echo("-" * 100)
        
        for meta in templates:
            desc = meta.description[:40] + "..." if len(meta.description) > 43 else meta.description
            click.echo(f"{meta.name:<25} {meta.category:<15} {meta.version:<10} {desc}")
        
        click.echo(f"\nTotal: {len(templates)} template(s)")
        
    except Exception as e:
        logger.error("template_list_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="use")
@click.argument("template_name")
@click.option("--var", "-v", multiple=True, help="Variable assignment (key=value)")
@click.option("--var-file", "-f", type=click.Path(exists=True), help="YAML/JSON file with variable values")
@click.option("--output", "-o", type=click.Path(), help="Output contract file path")
@click.option("--validate/--no-validate", default=True, help="Validate against schema")
@click.option("--sign", is_flag=True, help="Sign the generated contract")
def use_template(
    template_name: str,
    var: tuple,
    var_file: Optional[str],
    output: Optional[str],
    validate: bool,
    sign: bool,
) -> None:
    """Render a template to create a contract.
    
    TEMPLATE_NAME: Name of the template to use
    
    Examples:
        agenlang template use simple-agent -v goal="Research AI" -v joule_budget=1000
        agenlang template use simple-agent -f vars.yaml -o contract.json
    """
    log = structlog.get_logger()
    
    try:
        engine = TemplateEngine()
        
        # Load template to show required variables
        template = engine.load_template(template_name)
        required = template.get_required_variables()
        
        if required and not var and not var_file:
            click.echo(f"\nTemplate '{template_name}' requires the following variables:")
            for v in required:
                click.echo(f"  - {v.name}: {v.description}")
            click.echo(f"\nUsage: agenlang template use {template_name} -v {required[0].name}=value ...")
            return
        
        # Parse variables
        variables = {}
        
        # Load from file if provided
        if var_file:
            var_path = Path(var_file)
            if var_path.suffix in (".yaml", ".yml"):
                file_vars = yaml.safe_load(var_path.read_text())
            else:
                file_vars = json.loads(var_path.read_text())
            variables.update(file_vars)
        
        # Parse command line variables
        for v in var:
            if "=" not in v:
                click.echo(f"Error: Invalid variable format '{v}'. Use key=value", err=True)
                sys.exit(1)
            key, value = v.split("=", 1)
            # Try to parse as number/boolean
            try:
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif "." in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass  # Keep as string
            variables[key] = value
        
        # Render contract
        contract = engine.render_contract(template_name, variables, validate_schema=validate)
        
        # Sign if requested
        if sign:
            from .keys import KeyManager
            km = KeyManager()
            if not km.key_exists():
                click.echo("No key found. Generating new keypair...")
                km.generate()
            contract.sign(km)
            click.echo("Contract signed.")
        
        # Output contract
        contract_json = contract.to_json()
        
        if output:
            Path(output).write_text(contract_json)
            click.echo(f"Contract saved to: {output}")
        else:
            click.echo(contract_json)
        
        log.info("template_used", 
                template=template_name, 
                contract_id=contract.contract_id,
                variables=list(variables.keys()))
        
        click.echo(f"\n✓ Contract generated successfully!")
        click.echo(f"  Contract ID: {contract.contract_id}")
        click.echo(f"  Goal: {contract.goal[:60]}..." if len(contract.goal) > 60 else f"  Goal: {contract.goal}")
        
    except FileNotFoundError as e:
        click.echo(f"Template not found: {template_name}", err=True)
        click.echo(f"Run 'agenlang template list' to see available templates.", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Validation error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        log.error("template_use_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="validate")
@click.argument("template_name")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed validation output")
def validate_template(template_name: str, verbose: bool) -> None:
    """Validate a template for correctness."""
    try:
        engine = TemplateEngine()
        errors = engine.validate_template(template_name)
        
        if errors:
            click.echo(f"\n✗ Template '{template_name}' has validation errors:")
            for error in errors:
                click.echo(f"  - {error}")
            sys.exit(1)
        else:
            click.echo(f"\n✓ Template '{template_name}' is valid!")
            
            if verbose:
                template = engine.load_template(template_name)
                click.echo(f"\n  Name: {template.metadata.name}")
                click.echo(f"  Version: {template.metadata.version}")
                click.echo(f"  Description: {template.metadata.description}")
                click.echo(f"  Category: {template.metadata.category}")
                if template.metadata.parent:
                    click.echo(f"  Parent: {template.metadata.parent}")
                click.echo(f"  Variables: {len(template.variables)}")
                for var in template.variables:
                    req = "(required)" if var.required and var.default is None else "(optional)"
                    click.echo(f"    - {var.name}: {var.description} {req}")
        
    except FileNotFoundError:
        click.echo(f"Template not found: {template_name}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error("template_validation_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="show")
@click.argument("template_name")
@click.option("--format", "fmt", type=click.Choice(["yaml", "json", "summary"]), default="summary")
def show_template(template_name: str, fmt: str) -> None:
    """Show template details."""
    try:
        engine = TemplateEngine()
        template = engine.load_template(template_name)
        
        if fmt == "summary":
            click.echo(f"\nTemplate: {template.metadata.name}")
            click.echo(f"Version: {template.metadata.version}")
            click.echo(f"Description: {template.metadata.description or 'N/A'}")
            click.echo(f"Author: {template.metadata.author or 'N/A'}")
            click.echo(f"Category: {template.metadata.category}")
            click.echo(f"Created: {template.metadata.created}")
            click.echo(f"Updated: {template.metadata.updated}")
            if template.metadata.parent:
                click.echo(f"Parent: {template.metadata.parent}")
            if template.metadata.tags:
                click.echo(f"Tags: {', '.join(template.metadata.tags)}")
            
            click.echo(f"\nVariables ({len(template.variables)}):")
            for var in template.variables:
                req = "*" if var.required and var.default is None else ""
                default = f" (default: {var.default})" if var.default is not None else ""
                click.echo(f"  {var.name}{req}: {var.description}{default}")
                click.echo(f"    Type: {var.type}")
                if var.example:
                    click.echo(f"    Example: {var.example}")
        
        elif fmt == "yaml":
            click.echo(yaml.safe_dump(template.model_dump(), default_flow_style=False, sort_keys=False))
        
        else:  # json
            click.echo(json.dumps(template.model_dump(), indent=2))
        
    except FileNotFoundError:
        click.echo(f"Template not found: {template_name}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error("template_show_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="export")
@click.argument("template_name")
@click.argument("output_path", type=click.Path())
@click.option("--format", "fmt", type=click.Choice(["yaml", "json"]), default="yaml")
def export_template(template_name: str, output_path: str, fmt: str) -> None:
    """Export a template to a file."""
    try:
        engine = TemplateEngine()
        path = engine.export_template(template_name, output_path, fmt)
        click.echo(f"Template exported to: {path}")
    except FileNotFoundError:
        click.echo(f"Template not found: {template_name}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error("template_export_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="import")
@click.argument("source_path", type=click.Path(exists=True))
@click.option("--name", "-n", help="Override template name")
def import_template(source_path: str, name: Optional[str]) -> None:
    """Import a template from a file."""
    try:
        engine = TemplateEngine()
        template = engine.import_template(source_path)
        
        if name:
            template.metadata.name = name
            engine.save_template(template)
        
        click.echo(f"✓ Template '{template.metadata.name}' imported successfully!")
        click.echo(f"  Description: {template.metadata.description or 'N/A'}")
        click.echo(f"  Variables: {len(template.variables)}")
        
    except Exception as e:
        logger.error("template_import_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="delete")
@click.argument("template_name")
@click.confirmation_option(prompt="Are you sure you want to delete this template?")
def delete_template(template_name: str) -> None:
    """Delete a template."""
    try:
        engine = TemplateEngine()
        if engine.delete_template(template_name):
            click.echo(f"✓ Template '{template_name}' deleted.")
        else:
            click.echo(f"Template '{template_name}' not found.")
            sys.exit(1)
    except Exception as e:
        logger.error("template_delete_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="install")
@click.option("--force", is_flag=True, help="Overwrite existing templates")
def install_templates(force: bool) -> None:
    """Install built-in templates."""
    try:
        engine = TemplateEngine()
        
        # Check for existing templates
        existing = [t.name for t in engine.list_templates()]
        
        if existing and not force:
            click.echo(f"Found {len(existing)} existing template(s).")
            click.echo("Use --force to overwrite or install to a different directory.")
            return
        
        installed = install_builtin_templates()
        
        if installed:
            click.echo(f"✓ Installed {len(installed)} built-in template(s):")
            for name in installed:
                click.echo(f"  - {name}")
        else:
            click.echo("No built-in templates found or already installed.")
        
    except Exception as e:
        logger.error("template_install_failed", error=str(e))
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Helper functions

def _interactive_template_builder() -> dict:
    """Interactive CLI for building a contract template."""
    click.echo("\nLet's create your contract template.")
    click.echo("Press Ctrl+C at any time to cancel.\n")
    
    template = {
        "agenlang_version": "1.0",
        "contract_id": "{{contract_id}}",
        "issuer": {"agent_id": "{{issuer_id}}", "pubkey": "{{issuer_pubkey}}"},
        "receiver": {"agent_id": "{{receiver_id}}"},
        "goal": "{{goal}}",
        "intent_anchor": {"hash": "{{intent_hash}}"},
        "constraints": {"joule_budget": "{{joule_budget}}"},
        "workflow": {
            "type": "sequence",
            "steps": []
        },
        "memory_contract": {"handoff_keys": [], "ttl": "24h"},
        "settlement": {"joule_recipient": "{{receiver_id}}", "rate": 1.0},
        "capability_attestations": [],
    }
    
    # Get goal
    goal = click.prompt("Contract goal", type=str)
    template["goal"] = goal
    
    # Get workflow type
    workflow_type = click.prompt(
        "Workflow type", 
        type=click.Choice(["sequence"]), 
        default="sequence"
    )
    template["workflow"]["type"] = workflow_type
    
    # Add steps
    click.echo("\nAdd workflow steps (leave action empty to finish):")
    step_num = 1
    while True:
        click.echo(f"\nStep {step_num}:")
        action = click.prompt(
            "Action", 
            type=click.Choice(["tool", "skill", "subcontract", "embed", ""]),
            default="tool"
        )
        if not action:
            break
        
        target = click.prompt("Target (tool/skill name)", type=str)
        
        step = {
            "action": action,
            "target": target,
            "args": {}
        }
        
        # Add args
        click.echo("Add arguments (leave key empty to finish):")
        while True:
            key = click.prompt("Argument key", type=str, default="")
            if not key:
                break
            value = click.prompt("Argument value", type=str)
            step["args"][key] = value
        
        template["workflow"]["steps"].append(step)
        step_num += 1
    
    return template


def _interactive_variable_builder() -> list:
    """Interactive CLI for defining template variables."""
    click.echo("\nDefine template variables:")
    
    # Pre-defined variables
    variables = [
        TemplateVariable(
            name="contract_id",
            description="Unique contract identifier (auto-generated if empty)",
            type="string",
            required=False,
            default="",
        ),
        TemplateVariable(
            name="issuer_id",
            description="Issuer agent ID",
            type="string",
            required=True,
        ),
        TemplateVariable(
            name="receiver_id",
            description="Receiver agent ID",
            type="string",
            required=True,
        ),
        TemplateVariable(
            name="goal",
            description="Contract goal description",
            type="string",
            required=True,
        ),
        TemplateVariable(
            name="joule_budget",
            description="Maximum joule budget",
            type="float",
            required=True,
            example=1000.0,
        ),
        TemplateVariable(
            name="intent_hash",
            description="Intent anchor hash",
            type="string",
            required=False,
            default="sha256:auto",
        ),
        TemplateVariable(
            name="issuer_pubkey",
            description="Issuer public key (PEM format)",
            type="string",
            required=False,
            default="",
        ),
    ]
    
    # Allow adding custom variables
    click.echo("\nAdd custom variables (leave name empty to finish):")
    while True:
        name = click.prompt("Variable name", type=str, default="")
        if not name:
            break
        
        description = click.prompt("Description", type=str)
        var_type = click.prompt(
            "Type",
            type=click.Choice(["string", "integer", "float", "boolean", "list", "dict"]),
            default="string"
        )
        required = click.confirm("Required?", default=True)
        
        var = TemplateVariable(
            name=name,
            description=description,
            type=var_type,
            required=required
        )
        
        if not required:
            default = click.prompt("Default value", type=str, default="")
            if default:
                # Convert to appropriate type
                if var_type == "integer":
                    var.default = int(default)
                elif var_type == "float":
                    var.default = float(default)
                elif var_type == "boolean":
                    var.default = default.lower() == "true"
                else:
                    var.default = default
        
        variables.append(var)
    
    return variables


def _extract_variables_from_contract(contract_data: dict) -> tuple:
    """Extract potential template variables from a contract."""
    template_dict = contract_data.copy()
    variables = []
    
    # Simple heuristic: replace likely variable values with placeholders
    var_map = {
        "contract_id": ("{{contract_id}}", "string", "Unique contract identifier"),
        "issuer.agent_id": ("{{issuer_id}}", "string", "Issuer agent ID"),
        "receiver.agent_id": ("{{receiver_id}}", "string", "Receiver agent ID"),
        "goal": ("{{goal}}", "string", "Contract goal"),
        "constraints.joule_budget": ("{{joule_budget}}", "float", "Maximum joule budget"),
    }
    
    def set_nested(d, path, value):
        keys = path.split(".")
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
    
    def get_nested(d, path):
        keys = path.split(".")
        for key in keys:
            if isinstance(d, dict) and key in d:
                d = d[key]
            else:
                return None
        return d
    
    for path, (placeholder, var_type, description) in var_map.items():
        value = get_nested(contract_data, path)
        if value is not None:
            set_nested(template_dict, path, placeholder)
            variables.append(TemplateVariable(
                name=path.replace(".", "_"),
                description=description,
                type=var_type,
                required=True,
                example=value if var_type == "string" else str(value)
            ))
    
    return template_dict, variables
