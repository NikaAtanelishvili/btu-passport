"""MinIO / S3 object storage (BE-22). Objects are keyed by their SHA-256 and never overwritten.

Started in M2 for the seed's stamp images; BE-22 (M4) adds PDFs.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = object


@lru_cache
def client() -> S3Client:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _bucket() -> str:
    return get_settings().s3_bucket


def ensure_bucket() -> None:
    """Create the bucket if missing (dev uses minio-init; tests use their own bucket)."""
    try:
        client().head_bucket(Bucket=_bucket())
    except ClientError:
        client().create_bucket(Bucket=_bucket())


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return True


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    """Upload unless the key already exists (keys are content hashes, so the bytes match)."""
    if not exists(key):
        client().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type)


def get_bytes(key: str) -> bytes:
    return client().get_object(Bucket=_bucket(), Key=key)["Body"].read()
