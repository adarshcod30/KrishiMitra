"""S3-compatible object storage helpers.

Everything goes through an explicit ``endpoint_url``, so the same code drives
Cloudflare R2, Supabase Storage, Backblaze B2, MinIO and AWS S3 itself.

``boto3`` is an OPTIONAL dependency (``pip install 'agrotech-ml[s3]'``). This
module must therefore import cleanly without it: the import is deferred to call
time and turned into a clear, actionable error. When the ``AGROTECH_S3_*``
settings are not fully configured, callers never reach this module at all and
uploads stay on the local filesystem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from agrotech_ml.core.settings import AppSettings

DEFAULT_EXPIRY_SECONDS = 3600

_INSTALL_HINT = (
    "boto3 is not installed. Install the S3 extra: pip install 'agrotech-ml[s3]'"
)


class S3NotConfigured(RuntimeError):
    """Raised when an S3 helper is called without a complete configuration."""


def is_s3_available() -> bool:
    """True when the optional boto3 client library can be imported."""
    try:
        import boto3  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def build_object_name(prefix: str, name: str) -> str:
    """Join a (possibly empty) prefix and an object name with a single slash."""
    clean_prefix = (prefix or "").strip("/")
    clean_name = (name or "").lstrip("/")
    return f"{clean_prefix}/{clean_name}" if clean_prefix else clean_name


def s3_uri(bucket: str, object_name: str) -> str:
    return f"s3://{bucket}/{object_name.lstrip('/')}"


def _require_config(settings: "AppSettings") -> None:
    if not settings.uploads_to_s3:
        raise S3NotConfigured(
            "S3 uploads are not configured. Set AGROTECH_S3_ENDPOINT_URL, "
            "AGROTECH_S3_BUCKET, AGROTECH_S3_ACCESS_KEY_ID and "
            "AGROTECH_S3_SECRET_ACCESS_KEY, or leave them unset to store "
            "uploads on the local filesystem."
        )


def client(settings: "AppSettings") -> Any:
    """Build an S3 client bound to the configured endpoint.

    Path-style addressing is forced because virtual-host style is not supported
    by every S3-compatible backend (MinIO and Supabase in particular), and
    SigV4 is required by R2/B2.
    """
    _require_config(settings)
    try:
        import boto3
        from botocore.config import Config
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(_INSTALL_HINT) from exc

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region or "auto",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def public_url(settings: "AppSettings", object_name: str) -> str | None:
    """Stable URL for an object, when the bucket is fronted by a public base URL."""
    base = (settings.s3_public_base_url or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/{object_name.lstrip('/')}"


def upload_bytes(
    settings: "AppSettings",
    object_name: str,
    data: bytes,
    *,
    content_type: str | None = None,
    content_disposition: str | None = None,
) -> str:
    """Upload ``data`` and return a location string for the stored object.

    ``content_disposition`` is stored on the object so that even a directly
    public URL serves the file as an inert download rather than inline.
    """
    _require_config(settings)
    bucket = settings.s3_bucket or ""
    key = object_name.lstrip("/")

    extra: dict[str, Any] = {}
    if content_type:
        extra["ContentType"] = content_type
    if content_disposition:
        extra["ContentDisposition"] = content_disposition

    client(settings).put_object(Bucket=bucket, Key=key, Body=data, **extra)
    return public_url(settings, key) or s3_uri(bucket, key)


def presigned_url(
    settings: "AppSettings",
    object_name: str,
    *,
    expires_seconds: int = DEFAULT_EXPIRY_SECONDS,
    content_type: str | None = None,
    content_disposition: str | None = None,
) -> str:
    """Time-limited download URL for a private object.

    The response headers are pinned on the URL itself so the object is served
    with the content type this service validated at upload time, as an
    attachment, regardless of what metadata the bucket holds.
    """
    _require_config(settings)
    params: dict[str, Any] = {
        "Bucket": settings.s3_bucket or "",
        "Key": object_name.lstrip("/"),
    }
    if content_type:
        params["ResponseContentType"] = content_type
    if content_disposition:
        params["ResponseContentDisposition"] = content_disposition

    return client(settings).generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=int(expires_seconds),
    )


def download_url(
    settings: "AppSettings",
    object_name: str,
    *,
    expires_seconds: int = DEFAULT_EXPIRY_SECONDS,
    content_type: str | None = None,
    content_disposition: str | None = None,
) -> str:
    """Public URL when one is configured, otherwise a presigned URL."""
    direct = public_url(settings, object_name)
    if direct:
        return direct
    return presigned_url(
        settings,
        object_name,
        expires_seconds=expires_seconds,
        content_type=content_type,
        content_disposition=content_disposition,
    )


__all__ = [
    "DEFAULT_EXPIRY_SECONDS",
    "S3NotConfigured",
    "build_object_name",
    "client",
    "download_url",
    "is_s3_available",
    "presigned_url",
    "public_url",
    "s3_uri",
    "upload_bytes",
]
