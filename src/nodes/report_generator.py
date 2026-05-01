"""Report Generator node — final report assembly and S3 upload.

Takes all previous node outputs and produces:
  1. A structured JSON report (ReportOutput Pydantic model).
  2. A human-readable Markdown report.

Both are uploaded to S3 at ``s3://bucket/reports/{document_id}/``.

The Markdown report is designed to be readable without tooling — Tech Leads
reviewing a candidate's portfolio expect clear, professional output.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from src.graph.state import GraphState
from src.models.report import ReportMetadata, ReportOutput
from src.models.risk import RiskItem, Severity
from src.services.s3_service import S3Service
from src.utils.logger import get_logger

logger = get_logger(__name__)

_MODEL_USED = os.getenv("OPENAI_MODEL", "gpt-4o")


def _severity_sort_key(risk: RiskItem) -> int:
    """Sort key so CRITICAL risks appear first."""
    order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    return order.get(risk.severity, 4)


def _build_markdown_report(report: ReportOutput) -> str:
    """Render *report* as a Markdown document.

    Parameters
    ----------
    report:
        The fully populated ReportOutput instance.

    Returns
    -------
    str
        Markdown-formatted report string.
    """
    severity_emoji = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }

    lines: list[str] = [
        "# Contract Risk Analysis Report",
        "",
        f"**Document ID:** `{report.document_id}`",
        f"**Generated:** {report.metadata.created_at}",
        f"**Model:** {report.metadata.model_used}",
        f"**Processing time:** {report.metadata.processing_time_ms} ms",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        report.executive_summary,
        "",
    ]

    if report.key_parties:
        lines += [
            "## Contracting Parties",
            "",
            *[f"- {party}" for party in report.key_parties],
            "",
        ]

    if report.contract_duration:
        lines += [f"**Contract duration:** {report.contract_duration}", ""]
    if report.governing_law:
        lines += [f"**Governing law:** {report.governing_law}", ""]

    lines += [
        "---",
        "",
        "## Risk Assessment",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total risks | {report.total_risks} |",
        f"| Highest severity | {severity_emoji.get(report.highest_severity.value, '')} {report.highest_severity.value} |",
        f"| Overall risk score | {report.overall_risk_score:.2f} / 1.00 |",
        f"| Analysis confidence | {report.global_confidence:.2f} / 1.00 |",
        "",
    ]

    if report.risks:
        lines += ["## Identified Risks", ""]
        for i, risk in enumerate(sorted(report.risks, key=_severity_sort_key), start=1):
            emoji = severity_emoji.get(risk.severity.value, "")
            lines += [
                f"### {i}. {emoji} [{risk.severity.value}] {risk.description[:80]}",
                "",
                f"**Category:** {risk.category.value}  ",
                f"**Confidence:** {risk.confidence:.0%}  ",
                f"**Risk ID:** `{risk.risk_id}`",
                "",
                f"> **Clause reference:** _{risk.clause_reference[:300]}_",
                "",
                f"**Recommendation:** {risk.recommendation}",
                "",
            ]

    if report.recommendations:
        lines += [
            "---",
            "",
            "## Key Recommendations",
            "",
            *[f"{i}. {rec}" for i, rec in enumerate(report.recommendations, start=1)],
            "",
        ]

    if report.human_feedback:
        lines += [
            "---",
            "",
            "## Human Reviewer Notes",
            "",
            f"> {report.human_feedback}",
            "",
        ]

    lines += [
        "---",
        "",
        "## Analysis Metadata",
        "",
        f"- **Run ID:** `{report.metadata.run_id}`",
        f"- **Total tokens:** {report.metadata.total_tokens}",
        f"- **Report JSON:** `{report.metadata.report_s3_path_json}`",
        f"- **Report Markdown:** `{report.metadata.report_s3_path_md}`",
    ]
    if report.metadata.langsmith_trace_url:
        lines.append(f"- **LangSmith trace:** {report.metadata.langsmith_trace_url}")

    return "\n".join(lines)


def report_generator_node(state: GraphState) -> dict[str, Any]:
    """Generate the final report and upload it to S3.

    Parameters
    ----------
    state:
        Current graph state (reads all previous node outputs).

    Returns
    -------
    dict
        Keys updated: ``current_node``, ``updated_at``, and optionally ``errors``.
    """
    document_id = state["document_id"]
    logger.info("node_started", node="report_generator", document_id=document_id)

    updates: dict[str, Any] = {
        "current_node": "report_generator",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        start_time = time.perf_counter()

        summary = state.get("summary_output")
        risk = state.get("risk_analysis_output")
        validation = state.get("validation_output")
        run_id = state.get("document_id", "unknown")

        # ── Aggregate recommendations ──────────────────────────────────────
        recommendations: list[str] = []
        if risk:
            seen: set[str] = set()
            for r in sorted(risk.risks, key=_severity_sort_key):
                rec = r.recommendation.strip()
                if rec and rec not in seen:
                    recommendations.append(rec)
                    seen.add(rec)

        # ── Placeholder S3 paths (filled after actual upload) ──────────────
        json_s3 = f"s3://{os.getenv('S3_BUCKET_NAME', 'contract-analyzer-docs')}/reports/{document_id}/report.json"
        md_s3 = f"s3://{os.getenv('S3_BUCKET_NAME', 'contract-analyzer-docs')}/reports/{document_id}/report.md"

        metadata = ReportMetadata(
            document_id=document_id,
            run_id=run_id,
            model_used=_MODEL_USED,
            total_tokens=0,  # would be summed from per-call logs in production
            processing_time_ms=0,  # filled after upload
            langsmith_trace_url=os.getenv("LANGSMITH_TRACE_URL"),
            created_at=state.get("created_at", datetime.now(timezone.utc).isoformat()),
            report_s3_path_json=json_s3,
            report_s3_path_md=md_s3,
        )

        report = ReportOutput(
            document_id=document_id,
            executive_summary=(
                summary.executive_summary
                if summary
                else "Summary unavailable — extractor or summarizer failed."
            ),
            key_parties=summary.key_parties if summary else [],
            contract_duration=summary.contract_duration if summary else None,
            governing_law=summary.governing_law if summary else None,
            risks=list(risk.risks) if risk else [],
            total_risks=risk.total_risks if risk else 0,
            highest_severity=(
                risk.highest_severity if risk else Severity.LOW
            ),
            overall_risk_score=risk.overall_risk_score if risk else 0.0,
            global_confidence=state.get("global_confidence", 0.0),
            recommendations=recommendations,
            human_feedback=state.get("human_feedback"),
            metadata=metadata,
        )

        # ── Generate Markdown ──────────────────────────────────────────────
        md_content = _build_markdown_report(report)

        # ── Upload to S3 ───────────────────────────────────────────────────
        s3 = S3Service()
        report_dict = report.model_dump(mode="json")
        json_path, md_path = s3.upload_report(
            report_json=report_dict,
            report_md=md_content,
            document_id=document_id,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "node_completed",
            node="report_generator",
            document_id=document_id,
            json_path=json_path,
            md_path=md_path,
            elapsed_ms=elapsed_ms,
        )

    except Exception as exc:
        error_msg = f"report_generator_node failed: {exc!s}"
        logger.error(
            "node_failed", node="report_generator", document_id=document_id, error=str(exc)
        )
        updates["errors"] = [*state.get("errors", []), error_msg]

    return updates
