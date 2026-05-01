---
name: q-python-code-style
description: This skill ensures that code follows this monorepo style guidelines by running pre-commit and other linting tools. It should be used after making code changes to verify compliance, fix formatting issues automatically, and maintain consistent code quality across the qlegal monorepo.
metadata:
  category: development
  source:
    path: code-style
  version: "1.0.0"
---

# q-code-style: Code Quality & Style for qlegal

## Overview

This skill ensures code quality and style consistency across the qlegal monorepo. Use it at the end of each coding cycle to verify compliance with project standards.

## When to Use This Skill

This skill should be used when:
- Code changes have been made and need validation
- Before committing code to the repository
- Setting up a new development environment
- CI/CD pipelines need to validate code
- Refactoring existing code

## Style Principles

1. **Consistency**: All code must adhere to the project's formatting rules
2. **Automation**: Use automated tools to detect and fix style issues
3. **Pre-commit Hooks**: Always run pre-commit before finalizing changes
4. **Zero Warnings**: Code should pass all checks without warnings

## Component Naming Conventions

Follow the qlegal prefix convention:

| Prefix | Layer | Purpose |
|--------|-------|---------|
| `core` | Domain | Single domain component (entities, protocols, enums, exceptions) |
| `app_*` | Use Cases | Use cases with Facade pattern |
| `util_*` | Use Cases | Utility functions/helpers (pure functions, no state) |
| `factory_*` | Interface Adapters | Factories with DI |
| `impl_*` | Interface Adapters | Adapters using libraries directly |
| `client_*` | Interface Adapters | External service/API clients |

### Naming Format for impl_*/client_*

```
<type>_<what_they_implement>_<technology_used>
```

**Examples:**
- ✅ `impl_to_pdf_gotenberg` - Converts to PDF using Gotenberg
- ✅ `impl_to_markdown_docling` - Converts PDF to Markdown using Docling
- ✅ `impl_http_client_requests` - HTTP client using requests library
- ✅ `impl_file_manager_s3` - File manager using S3
- ✅ `client_dense_embedder_runpod` - Embedder via RunPod API

## Available Tools

### Pre-commit

**Purpose**: Git hook framework that runs checks before commits
**Configuration**: `.pre-commit-config.yaml`

### Ruff

**Purpose**: Fast Python linter and code formatter (replaces flake8, black, isort)
**Configuration**: `pyproject.toml` under `[tool.ruff]`

### Pyright

**Purpose**: Static type checking
**Configuration**: `pyproject.toml` under `[tool.pyright]`

### Polylith

**Purpose**: Monorepo brick management and dependency sync
**Commands**:
```bash
uv run poly sync          # Sync bricks
uv run poly check --strict  # Verify dependencies
```

## Polylith Structure

This project uses **Polylith** with **uv** as package manager.

### Directory Structure

```
qlegal/
├── components/qlegal/    # Reusable components (bricks)
│   ├── core/             # Single domain component
│   ├── app_*/            # Use Cases
│   ├── util_*/           # Utility functions
│   ├── impl_*/           # Adapters (libraries)
│   ├── factory_*/        # Factories
│   └── client_*/         # External API clients
├── bases/qlegal/         # Entry points
└── projects/             # Deployable projects
```

### ⚠️ No Subdirectories

**CORRECT:** `components/qlegal/app_pdf_processing/` ✅
**INCORRECT:** `components/qlegal/ai/embedder/` ❌

Use prefixes to organize, not subdirectories.

## Workflow Guidelines

### Quick Check

Run all style checks on all files using **uv** with .venv from root:

```bash
# Run pre-commit on all files
uv run pre-commit run --all-files

# Ruff can fix many issues automatically
uv run ruff check --fix .
uv run ruff format .

# Type checking (cannot auto-fix)
uv run pyright

# Verify Polylith structure
uv run poly sync && uv run poly check --strict
```

### Manual Fix Process

If there are errors that cannot be fixed automatically:

1. **Review errors**: Read the error messages carefully
2. **Fix manually**: Edit the code to resolve the issue
3. **Re-run**: Execute pre-commit again
4. **Repeat**: Continue until all checks pass

```bash
# Example workflow
uv run pre-commit run --all-files
# Fix errors manually...
uv run pre-commit run --all-files
# Continue until ✅ All checks passed
```

## Configuration Files

### Pre-commit Configuration

File: `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: pyright
        language: system
        types: [python]
        pass_filenames: false
        always_run: true
```

### Ruff Configuration

File: `pyproject.toml`

```toml
[tool.ruff]
target-version = "py312"
line-length = 88
indent-width = 4

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "F",   # Pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "W",   # pycodestyle warnings
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
]
ignore = [
    "E501",  # Line too long (handled by formatter)
]

[tool.ruff.lint.pydantic]
convention = "google"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
```

### Type Checking Configuration

File: `pyproject.toml`

```toml
[tool.pyright]
include = ["components/", "bases/"]
exclude = ["**/__pycache__", "**/.venv"]
venvPath = "."
venv = ".venv"
pythonVersion = "3.12"
strict = ["core", "app_"]
useLibraryCodeForTypes = true
typeCheckingMode = "standard"
```

## Style Rules Summary

### Python Style

- **Line length**: 88 characters (Black-compatible)
- **Quotes**: Double quotes for strings
- **Indentation**: 4 spaces
- **Imports**: Sorted and grouped (stdlib, third-party, local)
- **Type hints**: Required for all function signatures

### Data Type Naming

| Layer | Type | Suffix | Location | Example |
|-------|------|--------|----------|---------|
| Domain | `dataclass` | `Entity` | `core/entities.py` | `RawFileEntity` |
| Config | Pydantic `BaseModel` | `Config` | `bases/<base>/config.py` | `ScraperConfig` |
| Adapter DTO | Pydantic `BaseModel` | `DTO` | `impl_*/dtos.py` | `HttpResponseDTO` |
| DB Models | Pydantic `BaseModel` | `Model` | `impl_repository_*/models.py` | `ProcessedPdfModel` |

### Import Ordering

```python
# 1. Standard library
import os
import sys
from pathlib import Path

# 2. Third-party libraries
import requests
from pydantic import BaseModel

# 3. Local application - qlegal.*
from qlegal.core.entities import RawFileEntity
from qlegal.core.protocols import IFileManager
from qlegal.app_gaceta.core import DocumentProcessorApp
```

## Common Issues and Solutions

### Issue: Import Sorting

**Error**:
```
I001 Import block is un-sorted or un-formatted
```

**Solution**:
```bash
uv run ruff check --select I --fix .
```

### Issue: Trailing Whitespace

**Error**:
```
Trailing whitespace
```

**Solution**: Pre-commit will fix this automatically. If manual:
```bash
# Remove trailing whitespace
sed -i 's/[[:space:]]*$//' file.py
```

### Issue: Line Too Long

**Error**:
```
E501 Line too long (95 > 88 characters)
```

**Solution**: Ruff format will fix automatically, or manually break lines:
```python
# Bad
result = some_function(with_many_arguments, that_make_this_line, way_too_long_for_the_limit)

# Good
result = some_function(
    with_many_arguments,
    that_make_this_line,
    way_too_long_for_the_limit,
)
```

### Issue: Missing Type Hints

**Error**:
```
Missing type annotation for function argument
```

**Solution**: Add type hints:
```python
# Bad
def process(data):
    return data.upper()

# Good
def process(data: str) -> str:
    return data.upper()
```

### Issue: Type Checking Errors

**Error**:
```
error: Argument of type "int" cannot be assigned to parameter "name" of type "str"
```

**Solution**: Fix the type mismatch or use proper type annotations.

### Issue: Wrong Layer Import

**Error**:
```
error: Cannot import from impl_* into core
```

**Solution**: Follow the dependency rule - core/ can only import from core/.

## Dependency Rule

qlegal follows these dependency rules:

- ❌ `core/` **NEVER** imports from `app_*`, `impl_*`, `client_*`
- ❌ `app_*` **NEVER** imports concrete implementations (`impl_*`, `client_*`)
- ✅ `app_*` imports from `core/` (interfaces) and other `app_*` components
- ✅ Dependencies are injected via constructor (not created inside __init__)
- ✅ `factory_*` imports from all layers (creates instances)

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Code Quality

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Run pre-commit
        run: uv run pre-commit run --all-files
```

## IDE Integration

### VSCode

Extensions:
- Ruff (astral-sh.ruff)
- Python (ms-python.python)

Settings:
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "astral-sh.ruff",
  "ruff.format.args": ["--line-length=88"],
  "ruff.lint.args": ["--select=E,F,I,N,W,UP,B,C4,SIM"]
}
```

### PyCharm

1. Install Ruff plugin
2. Configure in Settings → Tools → Ruff
3. Enable "Run Ruff on save"

## Setup for New Components

### 1. Install Pre-commit

```bash
# Install pre-commit with uv
uv add --dev pre-commit

# Install hooks
uv run pre-commit install
```

### 2. Run Initial Check

```bash
uv run pre-commit run --all-files
```

## Checklist Before Committing

- [ ] `uv run ruff check --fix .` passes
- [ ] `uv run ruff format .` applied
- [ ] `uv run pyright` passes
- [ ] `uv run poly sync && uv run poly check --strict` passes
- [ ] `uv run pre-commit run --all-files` passes
- [ ] All imports use absolute paths (no relative imports)
- [ ] Component prefix follows convention (`core`, `app_*`, `util_*`, `impl_*`, `client_*`, `factory_*`)
- [ ] No `os.getenv()` in adapters (use DI)
- [ ] Domain layer (`core/`) has no external dependencies
