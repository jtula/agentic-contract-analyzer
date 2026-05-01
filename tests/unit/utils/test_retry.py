"""Unit tests for the retry decorator.

Tests cover:
- Successful call on first attempt (no retries)
- Retry on failure + eventual success
- Exhausted retries re-raise the original exception
- Async variant behaves identically
"""

from __future__ import annotations

import asyncio

import pytest

from src.utils.retry import with_retry


def test_no_retry_on_success() -> None:
    """Decorator does not retry when the function succeeds first time."""
    call_count = 0

    @with_retry(max_retries=3)
    def always_succeeds() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    result = always_succeeds()
    assert result == "ok"
    assert call_count == 1


def test_retries_on_failure_then_succeeds() -> None:
    """Decorator retries and returns value when the function eventually succeeds."""
    call_count = 0

    @with_retry(max_retries=3, backoff_factor=0.0)
    def fails_twice_then_succeeds() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient error")
        return "recovered"

    result = fails_twice_then_succeeds()
    assert result == "recovered"
    assert call_count == 3


def test_raises_after_max_retries() -> None:
    """Decorator re-raises the last exception after exhausting all retries."""
    call_count = 0

    @with_retry(max_retries=2, backoff_factor=0.0)
    def always_fails() -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("permanent error")

    with pytest.raises(RuntimeError, match="permanent error"):
        always_fails()

    assert call_count == 3  # 1 initial + 2 retries


def test_specific_exception_type_retried() -> None:
    """Only the specified exception type triggers a retry."""
    call_count = 0

    @with_retry(max_retries=3, backoff_factor=0.0, retriable_exceptions=(ValueError,))
    def raises_type_error() -> None:
        nonlocal call_count
        call_count += 1
        raise TypeError("not retriable")

    with pytest.raises(TypeError):
        raises_type_error()

    assert call_count == 1  # No retries for unmatched exception type


@pytest.mark.asyncio
async def test_async_retry_on_failure_then_succeeds() -> None:
    """Async decorator retries and returns value on eventual success."""
    call_count = 0

    @with_retry(max_retries=3, backoff_factor=0.0)
    async def async_fails_twice() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("async transient error")
        return "async_recovered"

    result = await async_fails_twice()
    assert result == "async_recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_raises_after_max_retries() -> None:
    """Async decorator re-raises after exhausting retries."""

    @with_retry(max_retries=1, backoff_factor=0.0)
    async def always_fails_async() -> None:
        raise RuntimeError("async permanent error")

    with pytest.raises(RuntimeError):
        await always_fails_async()
