"""
Vault File Storage — Manages physical file storage for uploaded documents.

Organizes files as: uploads/{tenant_id}/{project_id}/{document_type}/{year}/{month}/{uuid}_{filename}
Uses configuration from src.config for storage backend selection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from pathlib import Path

from loguru import logger

from src.config import get_settings, StorageBackend


class VaultFileStorage:
    """File storage service for the Document Vault."""

    def save_uploaded_file(
        self,
        file_content: bytes,
        original_filename: str,
        tenant_id: str,
        project_id: str,
        document_type: str = "UNCLASSIFIED",
    ) -> str:
        """
        Save an uploaded file and return the relative stored path.

        Path format: uploads/{tenant_id}/{project_id}/{document_type}/{year}/{month}/{uuid}_{filename}
        """
        settings = get_settings()
        now = datetime.now(UTC)
        file_id = uuid.uuid4().hex[:12]
        safe_filename = _sanitize_filename(original_filename)

        relative_path = (
            f"uploads/{tenant_id}/{project_id}/{document_type}"
            f"/{now.year}/{now.month:02d}/{file_id}_{safe_filename}"
        )

        if settings.storage_backend == StorageBackend.LOCAL:
            full_path = Path(settings.storage_local_path) / relative_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(file_content)
            logger.info(
                "Saved vault file locally",
                path=relative_path,
                size=len(file_content),
            )
        else:
            # S3 storage — write to S3 bucket
            try:
                import boto3

                s3 = boto3.client("s3", region_name=settings.s3_region)
                s3.put_object(
                    Bucket=settings.s3_bucket,
                    Key=relative_path,
                    Body=file_content,
                )
                logger.info(
                    "Saved vault file to S3",
                    bucket=settings.s3_bucket,
                    key=relative_path,
                )
            except Exception:
                logger.exception("Failed to save file to S3, falling back to local")
                full_path = Path(settings.storage_local_path) / relative_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_bytes(file_content)

        return relative_path

    def get_file_url(self, stored_path: str) -> str:
        """Generate a URL or local path for retrieving a stored file."""
        settings = get_settings()

        if settings.storage_backend == StorageBackend.S3 and settings.s3_bucket:
            return f"s3://{settings.s3_bucket}/{stored_path}"

        return f"/files/{stored_path}"

    def delete_file(self, stored_path: str) -> bool:
        """Delete a stored file. Returns True if deleted successfully."""
        settings = get_settings()

        if settings.storage_backend == StorageBackend.LOCAL:
            full_path = Path(settings.storage_local_path) / stored_path
            if full_path.exists():
                full_path.unlink()
                logger.info("Deleted vault file", path=stored_path)
                return True
            logger.warning("Vault file not found for deletion", path=stored_path)
            return False

        # S3 deletion
        try:
            import boto3

            s3 = boto3.client("s3", region_name=settings.s3_region)
            s3.delete_object(Bucket=settings.s3_bucket, Key=stored_path)
            logger.info("Deleted vault file from S3", key=stored_path)
            return True
        except Exception:
            logger.exception("Failed to delete file from S3")
            return False


def _sanitize_filename(filename: str) -> str:
    """Remove path separators and dangerous characters from a filename."""
    name = Path(filename).name
    # Keep alphanumeric, dots, hyphens, underscores
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)


# Singleton instance
vault_file_storage = VaultFileStorage()
