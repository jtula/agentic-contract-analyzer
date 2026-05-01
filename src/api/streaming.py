"""SSE (Server-Sent Events) streaming utilities.

The ``/analyze`` endpoint streams graph progress events to the client
as the LangGraph run progresses node by node.

Event types
-----------
- ``node_started``         — emitted before a node begins (best-effort)
- ``node_completed``       — emitted when a node writes back to state
- ``human_review_required``— emitted when the HITL gate triggers interrupt()
- ``analysis_completed``   — final event with report S3 URL
- ``error``                — emitted when a node fails

Format
------
Each SSE message is:
    data: <JSON string>\\n\\n

Clients receive a stream of JSON objects they can parse incrementally.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any


def _sse_line(payload: dict[str, Any]) -> str:
    """Format *payload* as a single SSE data line."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_graph_run(
    graph: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream SSE events for a LangGraph run.

    Iterates over ``graph.astream_events()`` and translates LangGraph
    lifecycle events into clean SSE payloads.

    Parameters
    ----------
    graph:
        A compiled LangGraph ``StateGraph``.
    initial_state:
        The initial ``GraphState`` dict for the run.
    config:
        LangGraph run config (must include ``{"configurable": {"thread_id": run_id}}``).

    Yields
    ------
    str
        SSE-formatted string chunks ready for ``StreamingResponse``.
    """
    try:
        async for event in graph.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            event_name: str = event.get("event", "")
            data: dict[str, Any] = event.get("data", {})
            metadata: dict[str, Any] = event.get("metadata", {})
            node_name: str = event.get("name", "")

            # ── Node completion ───────────────────────────────────────────
            if event_name == "on_chain_end" and node_name not in ("LangGraph", ""):
                output = data.get("output", {})
                payload = {
                    "event": "node_completed",
                    "node": node_name,
                    "status": "success",
                    "output": _sanitise_output(output),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                yield _sse_line(payload)

            # ── HITL interrupt ─────────────────────────────────────────────
            elif event_name == "on_chain_stream":
                chunk = data.get("chunk", {})
                if isinstance(chunk, dict) and "__interrupt__" in chunk:
                    interrupt_val = chunk["__interrupt__"]
                    payload = {
                        "event": "human_review_required",
                        "run_id": config.get("configurable", {}).get("thread_id"),
                        "reason": (
                            interrupt_val[0].value.get("reason", "Review required")
                            if interrupt_val
                            else "Review required"
                        ),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield _sse_line(payload)

            # ── Graph completed ────────────────────────────────────────────
            elif event_name == "on_chain_end" and node_name == "LangGraph":
                final_output = data.get("output", {})
                run_id = config.get("configurable", {}).get("thread_id")
                payload = {
                    "event": "analysis_completed",
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                yield _sse_line(payload)

    except Exception as exc:
        yield _sse_line({
            "event": "error",
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def _sanitise_output(output: Any) -> Any:
    """Recursively convert non-JSON-serialisable values to strings."""
    if isinstance(output, dict):
        return {k: _sanitise_output(v) for k, v in output.items()}
    if isinstance(output, list):
        return [_sanitise_output(i) for i in output]
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    try:
        json.dumps(output)
        return output
    except (TypeError, ValueError):
        return str(output)
