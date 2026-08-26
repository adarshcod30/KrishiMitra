"""Pull model artifacts from Cloud Storage into the local artifacts directory.

Cloud Run containers start with an empty writable filesystem, so trained models
have to be fetched at boot. This is a no-op when ``AGROTECH_MODELS_GCS_URI`` is
unset, which is what keeps local development working with zero GCP config.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agrotech_ml.core.settings import AppSettings

logger = logging.getLogger(__name__)


def expected_model_filenames(settings: AppSettings) -> list[str]:
    return [
        settings.model_filename,
        settings.metadata_filename,
        settings.disease_model_filename,
        settings.fertilizer_model_filename,
        settings.irrigation_model_filename,
    ]


def models_already_present(settings: AppSettings) -> bool:
    return all(
        (settings.artifacts_dir / filename).exists()
        for filename in expected_model_filenames(settings)
    )


def sync_models(
    settings: AppSettings | None = None,
    *,
    force: bool = False,
    strict: bool = False,
) -> list[Path]:
    """Download model artifacts from ``AGROTECH_MODELS_GCS_URI``.

    Returns the list of files written (empty when nothing had to be done).

    * No URI configured -> no-op, returns ``[]``.
    * All expected artifacts already on disk and ``force`` is False -> no-op.
    * Download failure -> logged and swallowed unless ``strict`` is True, so a
      transient Cloud Storage error cannot wedge container startup.

    ``settings`` is normally passed in by ``get_settings()``; omit it only from
    call sites outside settings construction.
    """
    if settings is None:  # pragma: no cover - convenience path
        from agrotech_ml.core.settings import get_settings

        settings = get_settings()

    uri = (settings.models_gcs_uri or "").strip()
    if not uri:
        return []

    if not force and models_already_present(settings):
        logger.info("Model artifacts already present in %s, skipping GCS sync", settings.artifacts_dir)
        return []

    from agrotech_ml.cloud.storage_gcs import download_prefix

    try:
        downloaded = download_prefix(
            uri,
            settings.artifacts_dir,
            project=settings.google_cloud_project,
            overwrite=force,
        )
    except Exception as exc:  # noqa: BLE001 - startup must not hard-fail on GCS
        if strict:
            raise
        logger.warning("Could not sync model artifacts from %s: %s", uri, exc)
        return []

    logger.info("Synced %d model artifact(s) from %s into %s", len(downloaded), uri, settings.artifacts_dir)
    return downloaded
