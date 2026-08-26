"""Safe handling of farmer-submitted files.

Two rules drive everything here:

1. **Never trust the client filename.** The stored name is a fresh UUID plus an
   extension derived from the *validated* content type, so an attacker cannot
   choose the extension the file is later served under.
2. **Never accept an unbounded body.** The upload is streamed in fixed chunks
   and aborted the moment it crosses ``settings.max_upload_size_bytes``, so a
   multi-gigabyte POST cannot exhaust container memory or disk.

Combined with the allowlist check, this closes the stored-XSS hole where an
anonymous caller could upload ``payload.html`` and have the API origin serve it
back as ``text/html``.
"""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agrotech_ml.core.settings import AppSettings

CHUNK_SIZE = 64 * 1024

# Extension chosen from the validated content type, never from the upload name.
EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "text/csv": ".csv",
}

# Reverse map used when serving a stored file back. Anything not listed is
# served as an opaque download, so text/html can never be reconstructed.
CONTENT_TYPE_BY_EXTENSION: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
}

OCTET_STREAM = "application/octet-stream"

# UUID4 hex + dot + short alphanumeric extension. Anything else is not a name
# this service ever generated, so it cannot address a file on disk.
STORED_NAME_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\.[a-z0-9]{1,8})?$")

_UNSAFE_NAME_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


class UploadTooLarge(Exception):
    """The request body exceeded ``settings.max_upload_size_bytes``."""

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"Upload exceeds the {limit_bytes} byte limit")
        self.limit_bytes = limit_bytes


class UploadStorageUnavailable(Exception):
    """The configured object-storage backend could not accept the file.

    Raised instead of letting a missing ``google-cloud-storage`` install or a
    Cloud Storage outage surface as an opaque HTTP 500.
    """


class UnsupportedUploadType(Exception):
    """The declared content type is not on the allowlist."""

    def __init__(self, content_type: str, allowed: set[str]) -> None:
        super().__init__(
            f"Content type {content_type!r} is not allowed. "
            f"Allowed types: {', '.join(sorted(allowed))}"
        )
        self.content_type = content_type
        self.allowed = allowed


@dataclass(frozen=True)
class StoredUpload:
    stored_name: str
    content_type: str
    size_bytes: int
    original_filename: str
    location: str


def normalize_content_type(raw: str | None) -> str:
    """Lower-case the media type and drop any ``; charset=...`` parameters."""
    value = (raw or "").split(";", 1)[0].strip().lower()
    return value


def validate_content_type(settings: AppSettings, raw: str | None) -> str:
    content_type = normalize_content_type(raw)
    allowed = settings.allowed_upload_types_list
    if content_type not in allowed:
        raise UnsupportedUploadType(content_type or "<missing>", allowed)
    return content_type


def extension_for(content_type: str) -> str:
    known = EXTENSION_BY_CONTENT_TYPE.get(content_type)
    if known:
        return known
    guessed = mimetypes.guess_extension(content_type) or ""
    return guessed if re.fullmatch(r"\.[a-z0-9]{1,8}", guessed) else ".bin"


def content_type_for_stored_name(stored_name: str) -> str:
    return CONTENT_TYPE_BY_EXTENSION.get(Path(stored_name).suffix.lower(), OCTET_STREAM)


def sanitize_original_filename(raw: str | None) -> str:
    """Keep a display-only copy of the client name, stripped of path and control bytes."""
    name = Path(raw or "upload.bin").name
    name = _UNSAFE_NAME_CHARS_RE.sub("", name).strip()
    name = name.replace("\\", "").replace("/", "")
    return name[:180] or "upload.bin"


def is_valid_stored_name(stored_name: str) -> bool:
    return bool(STORED_NAME_RE.fullmatch(stored_name or ""))


def build_stored_name(content_type: str) -> str:
    return f"{uuid4()}{extension_for(content_type)}"


def gcs_object_name(settings: AppSettings, stored_name: str) -> str:
    from agrotech_ml.cloud.storage_gcs import build_object_name

    return build_object_name("uploads", stored_name)


async def store_upload(
    settings: AppSettings,
    upload,  # fastapi.UploadFile - typed loosely to keep this module import-light
) -> StoredUpload:
    """Validate, stream and persist an upload.

    Writes to ``AGROTECH_UPLOADS_GCS_BUCKET`` when it is configured, and to
    ``settings.uploads_dir`` otherwise. Raises :class:`UnsupportedUploadType`
    or :class:`UploadTooLarge` before any bytes are committed.
    """
    content_type = validate_content_type(settings, getattr(upload, "content_type", None))
    limit = int(settings.max_upload_size_bytes)
    stored_name = build_stored_name(content_type)
    original_filename = sanitize_original_filename(getattr(upload, "filename", None))

    if settings.uploads_to_gcs:
        payload = await _read_limited(upload, limit)
        object_name = gcs_object_name(settings, stored_name)
        try:
            from agrotech_ml.cloud.storage_gcs import upload_bytes

            location = upload_bytes(
                settings.uploads_gcs_bucket or "",
                object_name,
                payload,
                content_type=content_type,
                project=settings.google_cloud_project,
            )
        except Exception as exc:  # noqa: BLE001 - reported as 503, never a bare 500
            raise UploadStorageUnavailable(
                f"Could not store the upload in gs://{settings.uploads_gcs_bucket}: {exc}"
            ) from exc
        return StoredUpload(
            stored_name=stored_name,
            content_type=content_type,
            size_bytes=len(payload),
            original_filename=original_filename,
            location=location,
        )

    destination = settings.uploads_dir / stored_name
    total = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise UploadTooLarge(limit)
                handle.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    return StoredUpload(
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=total,
        original_filename=original_filename,
        location=str(destination),
    )


async def _read_limited(upload, limit: int) -> bytes:
    """Read at most ``limit`` bytes, raising as soon as the cap is passed."""
    buffer = bytearray()
    while True:
        chunk = await upload.read(CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise UploadTooLarge(limit)
    return bytes(buffer)


__all__ = [
    "CONTENT_TYPE_BY_EXTENSION",
    "OCTET_STREAM",
    "StoredUpload",
    "UnsupportedUploadType",
    "UploadStorageUnavailable",
    "UploadTooLarge",
    "build_stored_name",
    "content_type_for_stored_name",
    "extension_for",
    "gcs_object_name",
    "is_valid_stored_name",
    "normalize_content_type",
    "sanitize_original_filename",
    "store_upload",
    "validate_content_type",
]
