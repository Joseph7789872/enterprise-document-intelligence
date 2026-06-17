"""S3 / MinIO storage backend (production).

Works with AWS S3 or any S3-compatible service (MinIO) via ``S3_ENDPOINT_URL``.
Bytes are already envelope-encrypted by the caller; server-side encryption can be
layered on as defense in depth in a later phase.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.storage import StorageError


class S3StorageBackend:
    def __init__(self) -> None:
        import boto3

        self._bucket = settings.S3_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        try:
            resp: dict[str, Any] = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            raise StorageError(f"Object not found: {key!r}") from exc
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
