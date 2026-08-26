"""Optional S3-compatible object storage integration.

Nothing in this package imports ``boto3`` at module scope, so the service keeps
working with the ``s3`` extra uninstalled. Every helper raises a clear,
actionable error when it is called without a complete ``AGROTECH_S3_*``
configuration; with those settings unset the upload path never gets here and
files are written to the local filesystem instead.
"""

from agrotech_ml.cloud.storage_s3 import (
    S3NotConfigured,
    build_object_name,
    download_url,
    is_s3_available,
    presigned_url,
    public_url,
    s3_uri,
    upload_bytes,
)

__all__ = [
    "S3NotConfigured",
    "build_object_name",
    "download_url",
    "is_s3_available",
    "presigned_url",
    "public_url",
    "s3_uri",
    "upload_bytes",
]
