---
name: q-python-code
description: This skill is responsible for generating python code in this monorepo. It implements Clean Architecture + Polylith + DDD + SOLID principles with strict component naming conventions. Use this skill whenever you need to create new features, services, adapters, or any code in this repository.
metadata:
  category: development
  source:
    path: coding
  version: "1.0.0"
---

# q-code: Code Generation for qlegal Monorepo

## Overview

This skill generates code following **Clean Architecture + Polylith + DDD + SOLID** principles as defined in AGENTS.md. Use this skill for any code generation task in the qlegal repository.

## Project Structure Reference

```
qlegal/
├── components/qlegal/    # Reusable components (bricks)
│   ├── core/              # Domain layer (SINGLE)
│   │   ├── __init__.py    # Exports entities, protocols, enums, exceptions
│   │   ├── entities.py    # Domain entities (dataclasses)
│   │   ├── enums.py       # Domain-specific enumerations
│   │   ├── exceptions.py  # Domain exceptions
│   │   └── protocols.py   # Protocol interfaces
│   ├── app_*/             # Use cases with Facade pattern
│   │   ├── __init__.py
│   │   ├── facade.py      # Facade pattern
│   │   └── uc/            # Pure use cases
│   ├── util_*/            # Utility functions/helpers
│   │   ├── __init__.py
│   │   └── core.py        # Pure functions, no state
│   ├── impl_*/            # Adapters (implement core/ protocols)
│   │   ├── __init__.py
│   │   ├── core.py
│   │   ├── models.py     # DB models - NOT in core/
│   │   └── dtos.py       # Adapter DTOs - NOT in core/
│   ├── factory_*/        # Factories
│   │   ├── __init__.py
│   │   └── core.py       # Factory with lazy imports
│   └── client_*/         # External API clients
│       ├── __init__.py
│       ├── core.py
│       └── dtos.py
├── bases/qlegal/          # Entry points
│   └── <base>/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py     # pydantic-settings
│       └── core.py       # create_facade() - os.getenv() ONLY here
└── projects/             # Deployable projects
    └── <project_name>/
        ├── pyproject.toml
        ├── docker-compose.yml
        └── .env.example
```

## Component Prefix Convention

| Prefix | Layer | Purpose |
|--------|-------|---------|
| `core` | Domain | Single domain component (entities, protocols, enums, exceptions) |
| `app_*` | Use Cases | Use cases with Facade pattern |
| `util_*` | Use Cases | Utility functions/helpers (pure functions, no state) |
| `factory_*` | Interface Adapters | Factories with DI |
| `impl_*` | Interface Adapters | Adapters using libraries directly |
| `client_*` | Interface Adapters | External service/API clients |

### Component Naming Format

```
<type>_<what_they_implement>_<technology_used>
```

**Examples:**
- ✅ `impl_to_pdf_gotenberg` - Converts to PDF using Gotenberg
- ✅ `impl_to_markdown_docling` - Converts PDF to Markdown using Docling
- ✅ `impl_http_client_requests` - HTTP client using requests library
- ✅ `impl_html_parser_lxml` - HTML parser using lxml
- ✅ `impl_file_manager_s3` - File manager using S3
- ✅ `client_dense_embedder_runpod` - Embedder via RunPod API

## Data Types per Layer

| Layer | Type | Suffix | Location | Example |
|-------|------|--------|----------|---------|
| Domain | `dataclass` | `Entity` | `core/entities.py` | `RawFileEntity` |
| Config | Pydantic `BaseModel` | `Config` | `bases/<base>/config.py` | `ScraperConfig` |
| Adapter DTO | Pydantic `BaseModel` | `DTO` | `impl_*/dtos.py` | `HttpResponseDTO` |
| DB Models | Pydantic `BaseModel` | `Model` | `impl_repository_*/models.py` | `ProcessedPdfModel` |

## Critical Rules from AGENTS.md

### 1. Single Core Component
- ✅ `core/entities.py`, `core/protocols.py`, `core/enums.py`, `core/exceptions.py`
- ❌ NO `core_pdf/`, `core_rag/` - all domain in ONE `core/`

### 2. Dependency Rule
```
Dependencies point inward:
impl_* ──▶ core/protocols (abstractions)
app_* ──▶ core/ (domain)
factory_* ──▶ impl_* (creates instances)
bases/ ──▶ factory_* + os.getenv() (entry points)
```

### 3. Forbidden in Domain Layer (core/ and app_*/)
```python
# ❌ NEVER in core/ or app_*/
import os
os.getenv("SOME_VAR")

import requests
from lxml import html
from pydantic import BaseModel  # NO Pydantic in core/
```

### 4. Factory Pattern with Lazy Imports
```python
# ❌ BAD - hard dependency at module level
from qlegal.impl_http_client_requests import HttpClient

# ✅ GOOD - lazy import inside factory
def create_http_client(type: str = "requests"):
    if type == "requests":
        from qlegal.impl_http_client_requests import HttpClient  # Lazy!
        return HttpClient()
```

### 5. Dependency Injection Pattern

**Core Principle**: Configuration is injected via constructor, NEVER created inside or obtained via `os.getenv()` inside adapters.

**The Flow**:
```
os.getenv() → config.py → factory_* → impl_* ← protocol from core/
                  ↓
              app_* ← protocol from core/
                  ↑
         bases/core.py ← os.getenv()
```

**Configuration Entry Point** (only place with `os.getenv()`):
```python
# bases/qlegal/<base>/config.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from qlegal.core.exceptions import ConfigurationError


class MyConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYAPP_")

    api_key: str = Field(...)
    timeout: int = Field(default=30)
```

**Factory Creates Instances with Injected Config**:
```python
# components/qlegal/factory_http_client/core.py
def create_http_client(config: HttpClientConfig) -> IHttpClient:
    if config.client_type == "requests":
        from qlegal.impl_http_client_requests import HttpClient
        return HttpClient(
            timeout=config.timeout,
            api_key=config.api_key,  # Injected, not os.getenv()
        )
    raise ValueError(f"Unknown client type: {config.client_type}")
```

**Adapter Receives Config via Constructor**:
```python
# components/qlegal/impl_http_client_requests/core.py
from qlegal.core.protocols import IHttpClient


class HttpClient(IHttpClient):
    def __init__(self, timeout: int, api_key: str):  # DI via constructor
        self._timeout = timeout
        self._api_key = api_key  # Stored, not from os.getenv()

    def get(self, url: str) -> HttpResponseEntity:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        # Use self._timeout and self._api_key
```

**App Receives Interfaces via Constructor**:
```python
# components/qlegal/app_myfeature/facade.py
class MyFeatureFacade:
    def __init__(
        self,
        http_client: IHttpClient,  # Protocol from core/, injected
        repository: IMyRepository,  # Protocol from core/, injected
    ):
        self._http_client = http_client
        self._repository = repository
```

**Entry Point Wires Everything**:
```python
# bases/qlegal/mybase/core.py
def create_facade() -> MyFeatureFacade:
    config = MyConfig()  # os.getenv() happens HERE

    http_client = create_http_client(config.http_client)
    repository = create_repository(config.repository)

    return MyFeatureFacade(
        http_client=http_client,
        repository=repository,
    )
```

**Key Rules**:
- ❌ NEVER `os.getenv()` in `impl_*`, `client_*`, `app_*`
- ❌ NEVER `api_key = os.getenv("API_KEY")` in adapter's `__init__`
- ✅ ALWAYS receive config via constructor parameter
- ✅ ALWAYS use `pydantic-settings` in `bases/<base>/config.py`
- ✅ ALWAYS create adapters via factories with injected config

## Code Generation Workflow

### Step 1: Analyze Requirements
- Identify the domain concern
- Determine if new Protocol is needed in `core/protocols.py`
- Determine if new Entity is needed in `core/entities.py`

### Step 2: Create Domain Layer (if needed)
```python
# components/qlegal/core/entities.py
@dataclass
class MyEntity:
    id: UUID
    name: str
    status: MyStatusEnum = MyStatusEnum.PENDING
```

```python
# components/qlegal/core/protocols.py
class IMyRepository(Protocol):
    def find_pending(self) -> list[MyEntity]: ...
    def create(self, entity: MyEntity) -> MyEntity: ...
```

### Step 3: Create Use Cases (app_*)
```python
# components/qlegal/app_myfeature/facade.py
class MyFeatureFacade:
    def __init__(
        self,
        repository: IMyRepository,  # Protocol from core/
        http_client: IHttpClient,   # Protocol from core/
    ):
        self.repository = repository
        self.http_client = http_client
```

### Step 4: Create Adapter (impl_*)
```python
# components/qlegal/impl_my_adapter_lib/core.py
class MyAdapter(IMyRepository):
    def __init__(self, connection_string: str):  # DI, no os.getenv()
        self.connection = connect(connection_string)
```

### Step 5: Create Factory
```python
# components/qlegal/factory_my_feature/core.py
def create_my_adapter(config: MyConfig) -> IMyRepository:
    if config.adapter_type == "lib":
        from qlegal.impl_my_adapter_lib import MyAdapter
        return MyAdapter(config.connection_string)
    raise ValueError(f"Unknown adapter: {config.adapter_type}")
```

### Step 6: Create Entry Point (base)
```python
# bases/qlegal/mybase/core.py
from qlegal.app_myfeature import MyFeatureFacade
from qlegal.mybase.config import MyConfig
from qlegal.factory_my_adapter import create_my_adapter

def create_facade() -> MyFeatureFacade:
    config = MyConfig()  # Loads from env vars
    adapter = create_my_adapter(config)
    return MyFeatureFacade(repository=adapter)
```

## API Response Standard

All API endpoints MUST use `ApiResponse[T]`:
```python
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    success: bool = Field(..., description="Indicates if request was successful")
    data: T | None = Field(None, description="Response data when success is True")
    error: str | None = Field(None, description="Error message when success is False")
```

## Anti-Patterns to Avoid

### ❌ Domain Accessing Infrastructure
```python
# core/entities.py - WRONG
class DocumentEntity:
    def save_to_database(self):
        db_connection.execute(...)  # ❌ Infrastructure leakage
```

### ❌ Global State in Adapters
```python
# impl_*/some_adapter.py - WRONG
API_KEY = os.getenv("API_KEY")  # ❌ Global state

def make_request():
    headers = {"Authorization": f"Bearer {API_KEY}"}
```

### ❌ Infrastructure Models in Domain
```python
# core/entities.py - WRONG
from sqlalchemy import Column, String

class DocumentEntity(Base):
    __tablename__ = "documents"
```

### ❌ app_* Importing Concrete impl_*
```python
# app_*/some_app.py - WRONG
from impl_llm_openai import OpenAIAdapter  # ❌ Should use core/ protocol

class SomeApp:
    def __init__(self):
        self.llm = OpenAIAdapter()  # ❌ Violates DIP
```

## Naming Conventions

- **Functions**: `snake_case` with descriptive names
- **Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Files**: `snake_case.py`

## Import Ordering

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

## Testing Guidelines

- Tests mirror component structure
- Use `pytest-asyncio` for async tests
- Mock external dependencies
- Minimum 80% coverage per component
- Use descriptive test names: `test_<what>_<condition>_<expected>`

## Build/Lint/Test Commands

> **NOTE**: This project uses **Polylith** for monorepo management and **uv** as the package manager. All commands should use `uv run` to execute within the `.venv` environment.

```bash
# Install dependencies (using uv with .venv)
uv sync

# Run linting & formatting
uv run ruff check --fix .
uv run ruff format .

# Type checking
uv run pyright

# Run tests
uv run pytest test/

# Polylith commands - Creating components, bases, and projects
uv run poly create component --name <name>    # Create new component (brick)
uv run poly create base --name <name>         # Create new base (entry point)
uv run poly create project --name <name>      # Create new project (deployable app)

# Polylith management
uv run poly sync                       # Sync bricks after import changes
uv run poly check --strict             # Verify dependencies and structure
uv run poly info                       # Show workspace info
```

## Checklist Before Generating Code

- [ ] Component uses correct prefix (`core`, `app_*`, `util_*`, `impl_*`, `client_*`, `factory_*`)
- [ ] All functions have type hints
- [ ] Domain layer (`core/`) has NO external dependencies
- [ ] Adapters receive config via constructors (DI)
- [ ] No `os.getenv()` in adapters
- [ ] All API endpoints use `ApiResponse[T]`
- [ ] Uses absolute imports (not relative)
- [ ] Structure follows Polylith (flat, no subdirectories)
- [ ] Run `uv run poly sync && uv run poly check --strict`
