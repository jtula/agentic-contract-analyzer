"""DynamoDB service — checkpointer + run metadata store.

DynamoDBSaver (from ``langgraph-checkpoint-dynamodb``) plugs directly into
LangGraph as a checkpointer, persisting the full GraphState after every node.

This module also provides a thin ``DynamoService`` for reading / writing
run metadata that doesn't go through the checkpointer (e.g. run status,
timestamps, SSE progress events).

Table schema
------------
``contract-analyzer-runs``
  PK: run_id (String)

Never store raw contract text in DynamoDB — keep it in S3.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.config import Config

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = os.getenv("DYNAMODB_TABLE_NAME", "contract-analyzer-runs")
_REGION = os.getenv("AWS_REGION", "us-east-1")
_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")

# ── Module-level cached boto3 resource ────────────────────────────────────
_dynamo_resource: Any = None


def _get_resource() -> Any:
    """Return the process-level boto3 DynamoDB resource, creating it once."""
    global _dynamo_resource
    if _dynamo_resource is None:
        kwargs: dict[str, Any] = {
            "region_name": _REGION,
            "config": Config(retries={"max_attempts": 1}),
        }
        if _ENDPOINT:
            kwargs["endpoint_url"] = _ENDPOINT
        _dynamo_resource = boto3.resource("dynamodb", **kwargs)
    return _dynamo_resource


def get_checkpointer() -> Any:
    """Return a LangGraph-compatible DynamoDB checkpointer.

    Uses ``langgraph-checkpoint-aws`` if available, otherwise raises
    ``ImportError`` with an informative message.

    Returns
    -------
    DynamoDBSaver
        A checkpointer instance ready to pass to ``StateGraph.compile()``.
    """
    try:
        from langgraph.checkpoint.dynamodb import DynamoDBSaver  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "Install 'langgraph-checkpoint-aws' to use DynamoDB checkpointing: "
            "pip install langgraph-checkpoint-aws"
        ) from exc

    client_kwargs: dict[str, Any] = {"region_name": _REGION}
    if _ENDPOINT:
        client_kwargs["endpoint_url"] = _ENDPOINT

    return DynamoDBSaver(
        table_name=_TABLE,
        **client_kwargs,
    )


class DynamoService:
    """Thin wrapper for reading and writing run metadata to DynamoDB.

    The checkpointer handles full graph state. This class handles
    lightweight metadata — run status, SSE event log, timestamps.
    """

    def __init__(self) -> None:
        resource = _get_resource()
        self._table = resource.Table(_TABLE)

    def put_run_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        """Upsert metadata for a run.

        Parameters
        ----------
        run_id:
            LangGraph thread / run identifier.
        metadata:
            Arbitrary key-value metadata to store alongside the run.
        """
        self._table.put_item(Item={"run_id": run_id, **metadata})
        logger.info("run_metadata_saved", run_id=run_id)

    def get_run_metadata(self, run_id: str) -> dict[str, Any] | None:
        """Fetch metadata for a run.

        Returns
        -------
        dict or None
            The stored item, or ``None`` if the run does not exist.
        """
        response = self._table.get_item(Key={"run_id": run_id})
        item: dict[str, Any] | None = response.get("Item")
        return item

    def append_sse_event(self, run_id: str, event: dict[str, Any]) -> None:
        """Append a single SSE event payload to the run's event log.

        Uses a DynamoDB list_append expression so events are never lost.
        """
        self._table.update_item(
            Key={"run_id": run_id},
            UpdateExpression=(
                "SET sse_events = list_append("
                "if_not_exists(sse_events, :empty), :evt)"
            ),
            ExpressionAttributeValues={":empty": [], ":evt": [event]},
        )
