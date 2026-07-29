"""Object storage abstraction — S3 when configured, else local UPLOAD_DIR.

Keeps DB `storage_path` / filename fields as relative keys so existing rows
and download endpoints keep working after enabling S3.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger("app.services.object_storage")


class ObjectStorage:
    """Upload / download / delete files via S3 or local disk."""

    def __init__(self) -> None:
        settings = get_settings()
        self._s3_client = None
        self._s3_ready = False
        if settings.s3_enabled:
            try:
                import boto3  # type: ignore

                self._s3_client = boto3.client(
                    "s3",
                    region_name=settings.AWS_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
                self._s3_ready = True
            except Exception as exc:  # pragma: no cover - depends on env/creds
                logger.warning("S3 configured but client init failed — using local disk: %s", exc)
                self._s3_client = None
                self._s3_ready = False

    @property
    def backend(self) -> str:
        return "s3" if self._s3_ready else "local"

    @property
    def local_root(self) -> Path:
        root = Path(get_settings().UPLOAD_DIR)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _s3_key(self, key: str) -> str:
        settings = get_settings()
        key = key.lstrip("/").replace("\\", "/")
        prefix = (settings.S3_PREFIX or "").strip().strip("/")
        if not prefix:
            return key
        if key.startswith(f"{prefix}/"):
            return key
        return f"{prefix}/{key}"

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        """Store bytes under `key`. Returns the relative key for DB persistence."""
        settings = get_settings()
        if not key or not key.strip():
            raise ValueError("storage key is required")
        relative_key = key.lstrip("/").replace("\\", "/")
        mime = content_type or mimetypes.guess_type(relative_key)[0] or "application/octet-stream"

        local_path = self.local_root / relative_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

        if self._s3_ready and self._s3_client is not None:
            try:
                self._s3_client.put_object(
                    Bucket=settings.S3_BUCKET,
                    Key=self._s3_key(relative_key),
                    Body=data,
                    ContentType=mime,
                )
            except Exception as exc:
                logger.error("S3 put_object failed for %s: %s", relative_key, exc)
                raise

        return relative_key

    def exists(self, key: str) -> bool:
        settings = get_settings()
        relative_key = key.lstrip("/").replace("\\", "/")
        local_path = self.local_root / relative_key
        if local_path.is_file():
            return True
        if not self._s3_ready or self._s3_client is None:
            return False
        try:
            self._s3_client.head_object(
                Bucket=settings.S3_BUCKET,
                Key=self._s3_key(relative_key),
            )
            return True
        except Exception:
            return False

    def get_bytes(self, key: str) -> bytes:
        settings = get_settings()
        relative_key = key.lstrip("/").replace("\\", "/")
        local_path = self.local_root / relative_key
        if local_path.is_file():
            return local_path.read_bytes()
        if not self._s3_ready or self._s3_client is None:
            raise FileNotFoundError(relative_key)
        try:
            response = self._s3_client.get_object(
                Bucket=settings.S3_BUCKET,
                Key=self._s3_key(relative_key),
            )
            data = response["Body"].read()
        except Exception as exc:
            raise FileNotFoundError(relative_key) from exc
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return data

    def resolve_local_path(self, key: str) -> Path:
        """Ensure object is available on disk (download from S3 if needed)."""
        relative_key = key.lstrip("/").replace("\\", "/")
        local_path = self.local_root / relative_key
        if local_path.is_file():
            return local_path
        self.get_bytes(relative_key)
        if not local_path.is_file():
            raise FileNotFoundError(relative_key)
        return local_path

    def delete(self, key: str) -> bool:
        """Delete from local disk and S3 when configured. Returns True if anything removed."""
        settings = get_settings()
        relative_key = key.lstrip("/").replace("\\", "/")
        removed = False
        local_path = self.local_root / relative_key
        if local_path.is_file():
            try:
                local_path.unlink()
                removed = True
            except OSError as exc:
                logger.warning("Failed to delete local file %s: %s", local_path, exc)

        if self._s3_ready and self._s3_client is not None:
            try:
                self._s3_client.delete_object(
                    Bucket=settings.S3_BUCKET,
                    Key=self._s3_key(relative_key),
                )
                removed = True
            except Exception as exc:
                logger.warning("S3 delete_object failed for %s: %s", relative_key, exc)

        return removed


_storage: ObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        _storage = ObjectStorage()
    return _storage


def reset_object_storage_cache() -> None:
    """Test helper — force re-read of settings on next get_object_storage()."""
    global _storage
    _storage = None
