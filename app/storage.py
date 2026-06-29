import os
import logging
import asyncio
import boto3
from botocore.exceptions import ClientError

_s3_client = None
_bucket = None
_region = None


def _init():
    """Lazy-initialize S3 client and cache config."""
    global _s3_client, _bucket, _region
    if _s3_client is None:
        _region = os.getenv("AWS_REGION", "us-east-1")
        _bucket = os.getenv("S3_AVATAR_BUCKET")
        _s3_client = boto3.client("s3", region_name=_region)


async def upload_avatar(user_id: int, file_bytes: bytes, suffix: str = "") -> str:
    """Upload avatar bytes to S3 as avatars/{user_id}{suffix}.jpg. Overwrites any existing file at that key."""
    _init()
    key = f"avatars/{user_id}{suffix}.jpg"

    def _upload():
        _s3_client.put_object(
            Bucket=_bucket,
            Key=key,
            Body=file_bytes,
            ContentType="image/jpeg",
        )

    await asyncio.to_thread(_upload)
    return f"https://{_bucket}.s3.{_region}.amazonaws.com/{key}"


async def delete_avatar(user_id: int) -> None:
    """Delete a user's avatar from S3."""
    _init()
    key = f"avatars/{user_id}.jpg"

    def _delete():
        try:
            _s3_client.delete_object(Bucket=_bucket, Key=key)
        except ClientError:
            logging.warning("Failed to delete S3 object %s", key, exc_info=True)

    await asyncio.to_thread(_delete)
