# Phase 0: Setup — Plan

**Objective:** Project scaffolding with src layout, dependencies, and CLI entry point

**Dependencies:** None (first phase)

**Requirements covered:** SET-01, SET-02, SET-03, SET-04

---

## Tasks

### Task 1: Create pyproject.toml with src layout
- Create `pyproject.toml` following modern Python packaging standards
- Use src/agenlang/ layout
- Include all core dependencies from REQUIREMENTS.md
- Include optional extras: brokers, observability

### Task 2: Create src/agenlang/ package structure
- Create `src/agenlang/__init__.py` with basic exports
- Create placeholder modules: identity.py, schema.py, transport/, core.py, contracts.py, negotiation.py, economy.py, bridge.py, discovery.py
- Create `src/agenlang/py.typed` marker file

### Task 3: Create CLI entry point
- Create `src/agenlang/cli.py` with basic CLI structure
- Entry point: agenlang CLI with agent start, discover, inspect commands

### Task 4: Verify setup
- Run `pip install -e .` to install package
- Verify `import agenlang` works
- Verify CLI entry point works

---

## Success Criteria

1. `pyproject.toml` exists with src layout and all core dependencies
2. All dependencies install without version conflicts
3. CLI entry point `agenlang` is functional
4. Project can be imported without errors (`import agenlang`)
