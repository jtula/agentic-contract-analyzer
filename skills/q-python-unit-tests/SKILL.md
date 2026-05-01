---
name: q-python-unit-tests
description: This skill provides guidelines for implementing essential python unit tests in this monorepo. Use it when writing tests for new features or verifying existing code. IMPORTANT: We do NOT need high coverage - only essential, fundamental, and critical unit tests.
metadata:
  category: development
  source:
    path: testing
  version: "1.0.0"
---

# q-unit-tests: Essential Unit Testing for qlegal

## Overview

This skill provides guidelines for implementing **essential** unit tests in the qlegal monorepo.

> **IMPORTANT**: We do NOT need high code coverage. Focus on **essential, fundamental, and critical** tests only.

## When to Use This Skill

This skill should be used when:
- Writing tests for new features or components
- Code is modified and tests need verification
- Setting up test infrastructure for a new component

## Coverage Philosophy

### ❌ NOT Required
- High coverage percentage (80%+)
- Testing every edge case
- Testing trivial code (getters, setters, simple properties)
- Testing boilerplate code

### ✅ Required - Essential Tests Only
- **Critical business logic** in domain entities
- **Key use cases** in app_* facades
- **Error handling** for main workflows
- **Protocol interfaces** that define contracts

## Testing Principles

### 1. Focus on What Matters

**Essential tests**:
- Domain entity creation and state transitions
- Core business rules and validations
- Main use case flows (happy path)
- Error handling for critical failures

**Skip these**:
- Simple getters/setters
- Boilerplate code
- Trivial conversions
- Mock-heavy tests that don't add value

### 2. Isolation

Tests must be isolated and not depend on external systems:

```python
@pytest.mark.asyncio
async def test_conversion_app_with_mock():
    # Mock external dependency
    mock_converter = AsyncMock()
    mock_converter.convert.return_value = b"converted content"

    app = ConversionApp(converter=mock_converter)
    result = await app.convert(input_data)

    # Verify interaction
    mock_converter.convert.assert_called_once_with(input_data)
    assert result == b"converted content"
```

### 3. Mocking

Use `pytest-mock` and `unittest.mock` to simulate dependencies:

```python
@pytest.fixture
def mock_repository(mocker):
    """Create a mock repository implementing the IRepository interface."""
    return mocker.AsyncMock(spec=IJobRepository)
```

## Component Structure Testing

Tests must mirror the component architecture:

```
test/
├── conftest.py                    # Global fixtures
├── core/                          # Domain layer tests
│   └── test_entities.py          # Entity tests (ESSENTIAL)
├── app_*/                        # Application layer tests
│   └── test_facade.py           # Facade tests (KEY USE CASES)
├── impl_*/                       # Implementation tests
│   └── test_adapter.py          # Adapter tests (MINIMAL)
└── factory_*/                    # Factory tests
    └── test_factory.py          # Factory tests (CREATE CORRECTLY)
```

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest test/

# Run with verbose output
uv run pytest test/ -v

# Run specific test file
uv run pytest test/components/qlegal/core/test_entities.py -v

# Run specific test function
uv run pytest test/components/qlegal/core/test_entities.py::test_entity_creation -v
```

## Test Structure

### Naming Conventions

- **Test files**: `test_<module_name>.py`
- **Test functions**: `test_<what_is_being_tested>_<condition>_<expected_result>`

**Examples**:
```python
def test_entity_creation_with_valid_data_succeeds():
    """Test that entity is created with correct initial state."""
    pass

def test_facade_convert_document_success_returns_result():
    """Test successful document conversion."""
    pass

def test_facade_convert_document_not_found_raises_error():
    """Test error handling when document not found."""
    pass
```

## Layer-Specific Testing

### Domain Layer Tests (core/)

**Focus**: Entity creation, state transitions, business rules

```python
# test/core/test_entities.py
import pytest
from qlegal.core.entities import ConversionJobEntity
from qlegal.core.exceptions import InvalidStatusError

def test_entity_creation():
    """Test entity is created with correct initial state."""
    entity = ConversionJobEntity(
        id="123",
        source_format="pdf",
        target_format="markdown"
    )
    assert entity.id == "123"
    assert entity.status == "pending"

def test_entity_mark_completed():
    """Test marking entity as completed."""
    entity = ConversionJobEntity(
        id="123",
        source_format="pdf",
        target_format="markdown"
    )
    entity.mark_completed()
    assert entity.status == "completed"
```

### Application Layer Tests (app_*)

**Focus**: Key use cases, main workflows, critical error handling

```python
# test/app_converter/test_facade.py
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_convert_document_success(mock_repository, mock_converter, sample_entity):
    """Test successful document conversion."""
    mock_repository.get_by_id.return_value = sample_entity
    mock_converter.convert.return_value = b"converted markdown"

    from qlegal.app_converter.facade import ConverterFacade
    facade = ConverterFacade(
        repo=mock_repository,
        converter=mock_converter
    )

    result = await facade.convert(sample_entity.id)

    assert result.status == "completed"
    mock_converter.convert.assert_called_once()

@pytest.mark.asyncio
async def test_convert_document_not_found_raises_error(mock_repository, mock_converter):
    """Test conversion when document not found."""
    mock_repository.get_by_id.return_value = None

    from qlegal.app_converter.facade import ConverterFacade
    from qlegal.core.exceptions import NotFoundError

    facade = ConverterFacade(
        repo=mock_repository,
        converter=mock_converter
    )

    with pytest.raises(NotFoundError):
        await facade.convert("non-existent-id")
```

### Implementation Tests (impl_*)

**Focus**: Minimal - only critical adapter behavior

```python
# test/impl_file_manager_s3/test_core.py
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_boto3():
    with patch('boto3.client') as mock:
        yield mock

@pytest.mark.asyncio
async def test_upload_returns_url(mock_boto3):
    """Test S3 upload returns correct URL."""
    mock_client = MagicMock()
    mock_client.upload_fileobj.return_value = None
    mock_boto3.return_value = mock_client

    from qlegal.impl_file_manager_s3.core import S3FileManager
    manager = S3FileManager(bucket_name="test-bucket", region="us-east-1")

    url = await manager.upload("test.txt", b"content")

    assert "test-bucket" in url
    assert "test.txt" in url
```

### Factory Tests (factory_*)

**Focus**: Verify factory creates correct instances

```python
# test/factory_file_manager/test_core.py
import pytest

def test_create_returns_s3_manager():
    """Test factory creates S3 file manager."""
    from qlegal.factory_file_manager.core import create_file_manager

    manager = create_file_manager(
        file_manager_type="s3",
        bucket_name="test-bucket",
        region="us-east-1"
    )

    assert manager is not None

def test_create_invalid_type_raises_error():
    """Test factory raises error for invalid type."""
    from qlegal.factory_file_manager.core import create_file_manager

    with pytest.raises(ValueError):
        create_file_manager(file_manager_type="invalid")
```

## Global Fixtures

Place common fixtures in `test/conftest.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from qlegal.core.entities import ConversionJobEntity
from qlegal.core.protocols import IJobRepository

@pytest.fixture
def sample_entity():
    """Return a sample entity."""
    return ConversionJobEntity(
        id="123",
        source_format="pdf",
        target_format="markdown"
    )

@pytest.fixture
def mock_converter():
    """Create a mock converter."""
    mock = AsyncMock()
    mock.convert.return_value = b"converted"
    return mock

@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    mock = AsyncMock(spec=IJobRepository)
    mock.get_by_id.return_value = None
    mock.save.return_value = None
    return mock
```

## Async Support

Use `pytest-asyncio` for all asynchronous operations:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_operation():
    mock_service = AsyncMock()
    mock_service.process.return_value = {"status": "ok"}

    result = await mock_service.process()
    assert result["status"] == "ok"
```

## Parametrize

Use `@pytest.mark.parametrize` for testing multiple values efficiently. This is ESSENTIAL for testing edge cases without writing multiple test functions:

```python
@pytest.mark.parametrize(
    "invalid_id",
    [
        "not-a-uuid",
        "",
        None,
    ],
)
def test_invalid_document_ids_raise_error(invalid_id):
    with pytest.raises(InvalidDocumentIdError):
        DocumentId(invalid_id)

@pytest.mark.parametrize(
    "input_value,expected",
    [
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("txt", "text/plain"),
    ],
)
def test_mime_type_detection_returns_correct_type(input_value, expected):
    result = detect_mime_type(f"document.{input_value}")
    assert result == expected
```

## Dependency Rule

When writing tests, verify dependency rules:

- ❌ `core/` **NEVER** imports from `app_*`, `impl_*`, `client_*`
- ❌ `app_*` **NEVER** imports concrete implementations (`impl_*`, `client_*`)
- ✅ `app_*` imports from `core/` (interfaces)
- ✅ Dependencies are injected via constructor

**Testing rule**: When testing `app_*`, mock `core/` interfaces. When testing `impl_*`, mock external libraries.

## Essential Testing Checklist

Before submitting code:

- [ ] Critical business logic has tests (entity creation, state changes)
- [ ] Key use cases have tests (main workflows)
- [ ] Error handling tested for critical failures
- [ ] Tests pass: `uv run pytest test/`
- [ ] Async tests use `@pytest.mark.asyncio`
- [ ] Test names are descriptive
- [ ] Fixtures used for common setup
- [ ] Tests follow component structure
- [ ] Dependency injection is used (no direct imports in app_*)
- [ ] **NO** high coverage requirement - focus on essential tests only
