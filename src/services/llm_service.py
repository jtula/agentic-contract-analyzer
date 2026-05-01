"""LLM service — centralised wrapper around the language model client.

All node code calls this service. It never instantiates the LLM directly.

Features
--------
- Provider switching via ``LLM_PROVIDER`` env var (``openai`` | ``bedrock``)
- Automatic LangSmith tracing (enabled via env vars, not code)
- Per-call token and latency logging
- ``@with_retry`` for transient API errors
- ``.with_structured_output()`` helper that forces Pydantic schema responses
- Module-level singleton so the LLM client is created only once per process
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def _build_llm() -> BaseChatModel:
    """Instantiate the LLM client based on ``LLM_PROVIDER``.

    Env vars are read here (not at module import time) so that the process
    can set them before the first call without stale-value issues.

    Returns
    -------
    BaseChatModel
        A LangChain-compatible chat model ready for use.

    Raises
    ------
    ValueError
        If ``LLM_PROVIDER`` is set to an unsupported value.
    """
    provider = os.getenv("LLM_PROVIDER", "openai")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI  # type: ignore[import]
        from pydantic import SecretStr

        raw_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=SecretStr(raw_key) if raw_key else None,
        )

    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse  # type: ignore[import]

        return ChatBedrockConverse(
            model=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER='{provider}'. Choose 'openai' or 'bedrock'."
    )


class LLMService:
    """LLM wrapper with structured output support.

    Use :func:`get_llm_service` to obtain the process-level singleton rather
    than constructing this directly — it avoids re-creating boto3/OpenAI
    clients on every LangGraph node invocation.

    Example
    -------
    ::

        from src.services.llm_service import get_llm_service
        from src.models import SummaryOutput

        svc = get_llm_service()
        result: SummaryOutput = await svc.invoke_structured(
            prompt="Summarise the following contract: ...",
            output_schema=SummaryOutput,
            node="summarizer",
            document_id="doc-123",
        )
    """

    def __init__(self) -> None:
        self._llm: BaseChatModel = _build_llm()
        provider = os.getenv("LLM_PROVIDER", "openai")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        logger.info("llm_service_initialized", provider=provider, model=model)

    @property
    def llm(self) -> BaseChatModel:
        """Raw LangChain LLM instance (use sparingly — prefer helper methods)."""
        return self._llm

    @with_retry(max_retries=3, backoff_factor=2.0)
    async def invoke_structured(
        self,
        prompt: str,
        output_schema: type[T],
        node: str,
        document_id: str,
        system_prompt: str | None = None,
    ) -> T:
        """Invoke the LLM and parse the response into a Pydantic model.

        Uses LangChain's ``.with_structured_output(include_raw=True)`` to
        capture both the parsed Pydantic output AND the raw AIMessage (which
        carries ``usage_metadata`` for token accounting).

        Parameters
        ----------
        prompt:
            The user-facing instruction + contract text.
        output_schema:
            Pydantic model class that defines the expected JSON structure.
        node:
            Name of the calling node (for logging).
        document_id:
            Document identifier (for logging).
        system_prompt:
            Optional system-level instruction to prepend.

        Returns
        -------
        T
            Validated Pydantic model instance.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        # include_raw=True returns {"raw": AIMessage, "parsed": T, "parsing_error": ...}
        structured_llm = self._llm.with_structured_output(output_schema, include_raw=True)

        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        start = time.perf_counter()
        raw_output: dict[str, Any] = await structured_llm.ainvoke(messages)  # type: ignore[assignment]
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        result: T = raw_output["parsed"]  # type: ignore[assignment]
        raw_response = raw_output.get("raw")
        usage = getattr(raw_response, "usage_metadata", None) or {}

        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        logger.info(
            "llm_invoked",
            node=node,
            document_id=document_id,
            model=model,
            latency_ms=elapsed_ms,
            prompt_tokens=usage.get("input_tokens", "n/a"),
            completion_tokens=usage.get("output_tokens", "n/a"),
        )
        return result

    @with_retry(max_retries=3, backoff_factor=2.0)
    async def invoke_raw(
        self,
        prompt: str,
        node: str,
        document_id: str,
        system_prompt: str | None = None,
    ) -> str:
        """Invoke the LLM and return the raw string content.

        Use this when you need free-form text (e.g. Markdown report body)
        rather than a structured Pydantic output.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        start = time.perf_counter()
        response = await self._llm.ainvoke(messages)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        content: str = response.content  # type: ignore[union-attr]
        logger.info(
            "llm_raw_invoked",
            node=node,
            document_id=document_id,
            latency_ms=elapsed_ms,
        )
        return content


# ── Process-level singleton ────────────────────────────────────────────────
# Nodes call get_llm_service() instead of LLMService() so the underlying
# LLM client (and its connection pool) is initialised exactly once.

_llm_service_instance: LLMService | None = None
_llm_service_lock = threading.Lock()


def get_llm_service() -> LLMService:
    """Return the process-level LLMService singleton (thread-safe).

    Creates the instance on first call using double-checked locking.
    Subsequent calls return the same object with zero overhead.
    """
    global _llm_service_instance
    if _llm_service_instance is None:
        with _llm_service_lock:
            if _llm_service_instance is None:
                _llm_service_instance = LLMService()
    return _llm_service_instance
