"""Google Cloud Storage helpers.

``google-cloud-storage`` is an OPTIONAL dependency (``pip install
'agrotech-ml[cloud]'``). This module must therefore import cleanly without it —
the import is deferred to call time and turned into a clear error message.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

GCS_SCHEME = "gs://"
_INSTALL_HINT = (
    "google-cloud-storage is not installed. Install the cloud extra: "
    "pip install 'agrotech-ml[cloud]'"
)


def is_gcs_available() -> bool:
    """True when the optional GCS client library can be imported."""
    try:
        import google.cloud.storage  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _client(project: str | None = None) -> Any:
    try:
        from google.cloud import storage
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(_INSTALL_HINT) from exc
    return storage.Client(project=project) if project else storage.Client()


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Split ``gs://bucket/some/prefix`` into ``("bucket", "some/prefix")``."""
    value = (uri or "").strip()
    if not value.startswith(GCS_SCHEME):
        raise ValueError(f"Not a GCS URI (expected gs://bucket/prefix): {uri!r}")
    remainder = value[len(GCS_SCHEME) :].strip("/")
    if not remainder:
        raise ValueError(f"GCS URI is missing a bucket name: {uri!r}")
    bucket, _, prefix = remainder.partition("/")
    return bucket, prefix


def build_object_name(prefix: str, name: str) -> str:
    """Join a (possibly empty) prefix and an object name with a single slash."""
    clean_prefix = (prefix or "").strip("/")
    clean_name = (name or "").lstrip("/")
    return f"{clean_prefix}/{clean_name}" if clean_prefix else clean_name


def public_url(bucket: str, object_name: str) -> str:
    """URL for an object whose bucket/object grants public read."""
    return f"https://storage.googleapis.com/{bucket}/{object_name.lstrip('/')}"


def gs_uri(bucket: str, object_name: str) -> str:
    return f"{GCS_SCHEME}{bucket}/{object_name.lstrip('/')}"


def upload_bytes(
    bucket: str,
    object_name: str,
    data: bytes,
    *,
    content_type: str | None = None,
    project: str | None = None,
    make_public: bool = False,
) -> str:
    """Upload ``data`` and return the ``gs://`` URI of the stored object."""
    blob = _client(project).bucket(bucket).blob(object_name.lstrip("/"))
    blob.upload_from_string(data, content_type=content_type)
    if make_public:
        blob.make_public()
    return gs_uri(bucket, object_name)


def signed_url(
    bucket: str,
    object_name: str,
    *,
    expires_seconds: int = 3600,
    method: str = "GET",
    project: str | None = None,
) -> str:
    """Time-limited download URL for a private object."""
    blob = _client(project).bucket(bucket).blob(object_name.lstrip("/"))
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=expires_seconds),
        method=method,
    )


def download_prefix(
    uri: str,
    destination: Path,
    *,
    project: str | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Download every object under ``uri`` into ``destination``.

    Existing files are left alone unless ``overwrite`` is set, so restarts do not
    re-pull hundreds of megabytes of model artifacts.
    """
    bucket_name, prefix = parse_gcs_uri(uri)
    client = _client(project)
    bucket = client.bucket(bucket_name)
    destination.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    blobs: Iterable[Any] = client.list_blobs(bucket, prefix=prefix or None)
    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        relative = blob.name[len(prefix) :].lstrip("/") if prefix else blob.name
        if not relative:
            continue
        target = destination / relative
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        downloaded.append(target)
    return downloaded
