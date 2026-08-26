"""Optional Google Cloud integrations.

Nothing in this package imports ``google-cloud-storage`` at module scope, so the
service keeps working with the cloud extra uninstalled. Every helper is a no-op
(or raises a clear, actionable error) when the corresponding setting is unset.
"""

from agrotech_ml.cloud.models_sync import sync_models
from agrotech_ml.cloud.storage_gcs import (
    download_prefix,
    is_gcs_available,
    parse_gcs_uri,
    public_url,
    signed_url,
    upload_bytes,
)

__all__ = [
    "download_prefix",
    "is_gcs_available",
    "parse_gcs_uri",
    "public_url",
    "signed_url",
    "sync_models",
    "upload_bytes",
]
