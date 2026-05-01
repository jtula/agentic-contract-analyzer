"""S3 service — abstraction over boto3 for all S3 operations.

All bucket names and region are read from environment variables so the
same code works against both LocalStack (local dev) and real AWS (prod).

Never import boto3 directly in node code — go through this service.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.config import Config

from src.utils.logger import get_logger
from src.utils.retry import with_retry

logger = get_logger(__name__)

_BUCKET = os.getenv("S3_BUCKET_NAME", "contract-analyzer-docs")
_REGION = os.getenv("AWS_REGION", "us-east-1")
_ENDPOINT = os.getenv("AWS_ENDPOINT_URL")  # LocalStack endpoint when set

# ── Module-level cached boto3 client ──────────────────────────────────────
# boto3 clients are thread-safe for concurrent read operations and expensive
# to create (TLS handshake, credential resolution). Re-use across requests.
_s3_client: Any = None


def _get_client() -> Any:
    """Return the process-level boto3 S3 client, creating it on first call."""
    global _s3_client
    if _s3_client is None:
        kwargs: dict[str, Any] = {
            "region_name": _REGION,
            "config": Config(retries={"max_attempts": 1}),  # we handle retries ourselves
        }
        if _ENDPOINT:
            kwargs["endpoint_url"] = _ENDPOINT
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def _assert_own_bucket(s3_path: str) -> str:
    """Validate *s3_path* belongs to our bucket and return the object key.

    Raises
    ------
    ValueError
        If *s3_path* does not start with the expected ``s3://<bucket>/``
        prefix, which would indicate a path-traversal or mis-configuration.
    """
    expected_prefix = f"s3://{_BUCKET}/"
    if not s3_path.startswith(expected_prefix):
        raise ValueError(
            f"s3_path '{s3_path}' does not belong to configured bucket '{_BUCKET}'. "
            "Refusing to operate on a foreign bucket."
        )
    return s3_path[len(expected_prefix):]


class S3Service:
    """Wrapper around boto3 S3 for contract document and report storage.

    Methods raise the original boto3 exceptions on failure so the
    ``@with_retry`` decorator or the calling node can handle them.

    The underlying boto3 client is shared at the module level — instantiating
    ``S3Service()`` multiple times is cheap and safe.
    """

    def __init__(self) -> None:
        self._client = _get_client()

    # ── Documents ─────────────────────────────────────────────────────────

    @with_retry(max_retries=3, backoff_factor=2.0)
    def upload_document(self, file_bytes: bytes, document_id: str) -> str:
        """Upload a raw PDF to S3 and return its S3 URI.

        Parameters
        ----------
        file_bytes:
            Raw PDF content as bytes.
        document_id:
            Unique document identifier used as the S3 key prefix.

        Returns
        -------
        str
            Full S3 URI, e.g. ``s3://bucket/contracts/doc-123/original.pdf``.
        """
        key = f"contracts/{document_id}/original.pdf"
        self._client.put_object(
            Bucket=_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType="application/pdf",
        )
        s3_path = f"s3://{_BUCKET}/{key}"
        logger.info("document_uploaded", document_id=document_id, s3_path=s3_path)
        return s3_path

    @with_retry(max_retries=3, backoff_factor=2.0)
    def download_document(self, s3_path: str) -> bytes:
        """Download a document from S3 by its URI.

        Parameters
        ----------
        s3_path:
            Full S3 URI as returned by :meth:`upload_document`.

        Returns
        -------
        bytes
            Raw file content.

        Raises
        ------
        ValueError
            If *s3_path* does not belong to the configured bucket.
        """
        key = _assert_own_bucket(s3_path)
        response = self._client.get_object(Bucket=_BUCKET, Key=key)
        content = response["Body"].read()
        logger.info("document_downloaded", s3_path=s3_path, bytes=len(content))
        return content

    # ── Reports ───────────────────────────────────────────────────────────

    @with_retry(max_retries=3, backoff_factor=2.0)
    def upload_report(
        self,
        report_json: dict[str, Any],
        report_md: str,
        document_id: str,
    ) -> tuple[str, str]:
        """Upload the final analysis report in both JSON and Markdown formats.

        Parameters
        ----------
        report_json:
            Serialisable dict representing the full report.
        report_md:
            Markdown-formatted report string.
        document_id:
            Used as the S3 key prefix.

        Returns
        -------
        tuple[str, str]
            ``(json_s3_path, md_s3_path)``
        """
        json_key = f"reports/{document_id}/report.json"
        md_key = f"reports/{document_id}/report.md"

        self._client.put_object(
            Bucket=_BUCKET,
            Key=json_key,
            Body=json.dumps(report_json, indent=2, ensure_ascii=False).encode(),
            ContentType="application/json",
        )
        self._client.put_object(
            Bucket=_BUCKET,
            Key=md_key,
            Body=report_md.encode("utf-8"),
            ContentType="text/markdown",
        )

        json_path = f"s3://{_BUCKET}/{json_key}"
        md_path = f"s3://{_BUCKET}/{md_key}"
        logger.info(
            "report_uploaded",
            document_id=document_id,
            json_path=json_path,
            md_path=md_path,
        )
        return json_path, md_path

    @with_retry(max_retries=2, backoff_factor=1.5)
    def generate_presigned_url(self, s3_path: str, expiry_seconds: int = 3600) -> str:
        """Generate a time-limited pre-signed URL for a stored report.

        Parameters
        ----------
        s3_path:
            Full S3 URI of the object.
        expiry_seconds:
            URL validity window in seconds (default 1 hour).

        Returns
        -------
        str
            HTTPS pre-signed URL.

        Raises
        ------
        ValueError
            If *s3_path* does not belong to the configured bucket.
        """
        key = _assert_own_bucket(s3_path)
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": _BUCKET, "Key": key},
            ExpiresIn=expiry_seconds,
        )
        return url
