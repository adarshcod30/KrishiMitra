"""Out-of-band model retraining.

Retraining fits eight candidate estimators and writes ~173 MB of artifacts; on
this dataset it takes 31-35 s of pegged CPU. Doing that inside a request handler
blocks a worker for the whole duration, so ``POST /retrain`` only *queues* the
job here and returns immediately. Exactly one job may be in flight at a time.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from agrotech_ml.core.settings import AppSettings
from agrotech_ml.models.schemas import RetrainStatus

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_status = RetrainStatus(status="idle")


class RetrainAlreadyRunning(RuntimeError):
    """A retrain job is already queued or running."""


def current_status() -> RetrainStatus:
    with _lock:
        return _status.model_copy(deep=True)


def is_busy() -> bool:
    with _lock:
        return _status.status in {"queued", "running"}


def queue_job() -> str:
    """Reserve the single retrain slot and return the new job id."""
    global _status
    with _lock:
        if _status.status in {"queued", "running"}:
            raise RetrainAlreadyRunning(
                f"Retrain job {_status.job_id} is already {_status.status}"
            )
        job_id = str(uuid4())
        _status = RetrainStatus(
            status="queued",
            job_id=job_id,
            started_at=None,
            finished_at=None,
            duration_seconds=None,
            detail="Queued",
            best_model=None,
        )
    return job_id


def run_job(settings: AppSettings, job_id: str) -> None:
    """Execute the reserved job. Intended for ``BackgroundTasks``."""
    global _status
    started = datetime.now(UTC)
    clock = time.perf_counter()

    with _lock:
        if _status.job_id != job_id:
            logger.warning("Retrain job %s was superseded before it started", job_id)
            return
        _status = _status.model_copy(update={"status": "running", "started_at": started, "detail": "Training"})

    try:
        from agrotech_ml.services.inference import clear_artifact_cache
        from agrotech_ml.services.training import train_models

        metadata = train_models(settings)
        clear_artifact_cache()
    except Exception as exc:  # noqa: BLE001 - surfaced through the status endpoint
        logger.exception("Retrain job %s failed", job_id)
        with _lock:
            _status = _status.model_copy(
                update={
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "duration_seconds": round(time.perf_counter() - clock, 2),
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
        return

    with _lock:
        _status = _status.model_copy(
            update={
                "status": "succeeded",
                "finished_at": datetime.now(UTC),
                "duration_seconds": round(time.perf_counter() - clock, 2),
                "detail": f"Trained on {metadata.dataset_rows} rows",
                "best_model": metadata.best_model,
            }
        )
    logger.info("Retrain job %s finished; best model %s", job_id, metadata.best_model)


def reset_for_tests() -> None:  # pragma: no cover - test helper
    global _status
    with _lock:
        _status = RetrainStatus(status="idle")


__all__ = [
    "RetrainAlreadyRunning",
    "current_status",
    "is_busy",
    "queue_job",
    "reset_for_tests",
    "run_job",
]
