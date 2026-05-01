"""FastAPI route handlers for the Contract Risk Analyzer.

Endpoints
---------
POST /analyze
    Upload a PDF contract and start the analysis.
    Returns: StreamingResponse (SSE) with per-node progress events.

GET /runs/{run_id}
    Fetch the current state of an analysis run from DynamoDB.

POST /analyze/{run_id}/resume
    Resume a paused graph run after human review.

GET /health
    Health check endpoint for load-balancer probes.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.streaming import stream_graph_run
from src.services.dynamo_service import DynamoService
from src.services.s3_service import S3Service
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ── API Key auth (opt-in: only enforced when API_KEY env var is set) ───────
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_CONFIGURED_API_KEY: str | None = os.getenv("API_KEY")

_MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
_PDF_MAGIC = b"%PDF"


async def verify_api_key(
    api_key: str | None = Security(_API_KEY_HEADER),
) -> None:
    """Dependency that enforces API key auth when ``API_KEY`` env var is set.

    When ``API_KEY`` is not configured the dependency is a no-op, which is
    convenient for local development. Always set it in production.
    """
    if not _CONFIGURED_API_KEY:
        return  # auth disabled
    if api_key != _CONFIGURED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


class ResumeRequest(BaseModel):
    """Payload for the HITL resume endpoint."""

    action: str = "approve"
    """One of: ``approve``, ``reject``."""

    notes: str | None = None
    """Optional reviewer notes attached to the final report."""


class RunStatusResponse(BaseModel):
    """Response model for GET /runs/{run_id}."""

    run_id: str
    status: str
    document_id: str | None = None
    current_node: str | None = None
    global_confidence: float | None = None
    needs_human_review: bool | None = None
    errors: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None


@router.post(
    "/analyze",
    summary="Upload a PDF contract and start risk analysis",
    response_description="Server-Sent Events stream with analysis progress",
    dependencies=[Depends(verify_api_key)],
)
async def analyze_contract(
    request: Request,
    file: UploadFile = File(..., description="PDF contract file to analyse"),
) -> StreamingResponse:
    """Start a new contract analysis run.

    Uploads the PDF to S3, initialises a LangGraph run, and streams
    Server-Sent Events (SSE) as each node completes.

    The client reads the stream with:
    ```
    const es = new EventSource('/analyze');
    es.onmessage = (e) => console.log(JSON.parse(e.data));
    ```

    Returns
    -------
    StreamingResponse
        ``Content-Type: text/event-stream`` — each event is a JSON object.
    """
    # ── Extension check (fast, first gate) ────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()

    # ── Size check ─────────────────────────────────────────────────────────
    if len(pdf_bytes) > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"File exceeds {_MAX_FILE_SIZE_MB} MB limit."
        )

    # ── Magic bytes check (prevents disguised non-PDF uploads) ────────────
    if pdf_bytes[:4] != _PDF_MAGIC:
        raise HTTPException(
            status_code=400, detail="File content is not a valid PDF (bad magic bytes)."
        )

    # ── Upload to S3 ───────────────────────────────────────────────────────
    document_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    try:
        s3 = S3Service()
        s3_path = s3.upload_document(pdf_bytes, document_id)
    except Exception as exc:
        logger.error("s3_upload_failed", document_id=document_id, error=str(exc))
        raise HTTPException(status_code=503, detail="S3 upload failed.") from exc

    # ── Persist run metadata ───────────────────────────────────────────────
    try:
        dynamo = DynamoService()
        dynamo.put_run_metadata(
            run_id=run_id,
            metadata={
                "document_id": document_id,
                "s3_path": s3_path,
                "status": "running",
                "created_at": now,
                "updated_at": now,
            },
        )
    except Exception as exc:
        logger.warning("dynamo_metadata_failed", run_id=run_id, error=str(exc))
        # Non-fatal — SSE stream can still proceed

    # ── Build initial graph state ──────────────────────────────────────────
    initial_state: dict[str, Any] = {
        "document_id": document_id,
        "s3_path": s3_path,
        "document_text": "",
        "extractor_output": None,
        "summary_output": None,
        "risk_analysis_output": None,
        "validation_output": None,
        "global_confidence": 0.0,
        "needs_human_review": False,
        "current_node": "extractor",
        "errors": [],
        "retry_count": 0,
        "human_feedback": None,
        "created_at": now,
        "updated_at": now,
    }

    # Re-use the graph compiled once at startup (see main.py lifespan)
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": run_id}}

    logger.info("analysis_started", run_id=run_id, document_id=document_id)

    return StreamingResponse(
        stream_graph_run(graph, initial_state, config),
        media_type="text/event-stream",
        headers={
            "X-Run-ID": run_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    summary="Get the current state of a run",
    dependencies=[Depends(verify_api_key)],
)
async def get_run_status(run_id: uuid.UUID) -> RunStatusResponse:
    """Fetch run metadata from DynamoDB.

    Parameters
    ----------
    run_id:
        The UUID returned in the ``X-Run-ID`` response header of ``/analyze``.
        FastAPI validates that this is a well-formed UUID automatically.

    Returns
    -------
    RunStatusResponse
        Current run status and metadata.
    """
    run_id_str = str(run_id)
    try:
        dynamo = DynamoService()
        item = dynamo.get_run_metadata(run_id_str)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="DynamoDB unavailable.") from exc

    if not item:
        raise HTTPException(status_code=404, detail=f"Run '{run_id_str}' not found.")

    return RunStatusResponse(
        run_id=run_id_str,
        status=item.get("status", "unknown"),
        document_id=item.get("document_id"),
        current_node=item.get("current_node"),
        global_confidence=item.get("global_confidence"),
        needs_human_review=item.get("needs_human_review"),
        errors=item.get("errors", []),
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
    )


@router.post(
    "/analyze/{run_id}/resume",
    summary="Resume a paused HITL run with human feedback",
    dependencies=[Depends(verify_api_key)],
)
async def resume_run(
    request: Request,
    run_id: uuid.UUID,
    body: ResumeRequest,
) -> dict[str, str]:
    """Resume a graph run that was paused by the HITL gate.

    Submits human feedback using LangGraph's ``Command(resume=...)`` API,
    which un-pauses the graph and continues execution from the checkpoint.

    Parameters
    ----------
    run_id:
        The paused run's thread ID (must be a valid UUID).
    body:
        Human review decision and optional notes.

    Returns
    -------
    dict
        Confirmation with run_id and submitted action.
    """
    from langgraph.types import Command  # type: ignore[import]

    run_id_str = str(run_id)

    # Verify the run exists and is in a paused state before attempting resume
    try:
        dynamo = DynamoService()
        item = dynamo.get_run_metadata(run_id_str)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="DynamoDB unavailable.") from exc

    if not item:
        raise HTTPException(status_code=404, detail=f"Run '{run_id_str}' not found.")

    feedback = body.notes or body.action
    config = {"configurable": {"thread_id": run_id_str}}

    try:
        graph = request.app.state.graph
        await graph.ainvoke(Command(resume=feedback), config=config)
    except Exception as exc:
        logger.error("resume_failed", run_id=run_id_str, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Resume failed: {exc!s}") from exc

    logger.info("run_resumed", run_id=run_id_str, action=body.action)
    return {"run_id": run_id_str, "action": body.action, "status": "resumed"}


@router.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    """Health check for load-balancer probes.

    Returns
    -------
    dict
        ``{"status": "ok"}`` when the service is healthy.
    """
    return {"status": "ok"}
