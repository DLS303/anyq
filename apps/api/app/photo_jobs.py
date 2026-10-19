"""Face and plate blur off the request worker.

OpenCV runs in a thread pool. The request records a photo_jobs row and waits
up to ANYQ_PHOTO_TIMEOUT seconds without blocking the event loop.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select

from app.media import ProcessedUpload, process_upload
from app.sql_backend import PhotoJob

PHOTO_POOL = ThreadPoolExecutor(max_workers=int(os.getenv("ANYQ_PHOTO_WORKERS", "2")), thread_name_prefix="photo")


def photo_timeout() -> float:
    return float(os.getenv("ANYQ_PHOTO_TIMEOUT", "20"))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _session():
    from app.store import store

    return store._sql.factory()


def create_job(*, job_id: str, owner_id: str, project_id: str | None, daily_log_id: str | None) -> None:
    with _session() as session:
        session.add(
            PhotoJob(
                id=job_id,
                status="pending",
                owner_id=owner_id,
                project_id=project_id,
                daily_log_id=daily_log_id,
                error="",
                created_at=_now(),
            )
        )
        session.commit()


def mark(job_id: str, status: str, **fields) -> None:
    with _session() as session:
        row = session.get(PhotoJob, job_id)
        if row is None:
            return
        row.status = status
        for key, value in fields.items():
            setattr(row, key, value)
        if status in {"done", "failed", "timeout"}:
            row.finished_at = _now()
        session.commit()


def get_job(job_id: str) -> dict | None:
    with _session() as session:
        row = session.get(PhotoJob, job_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "status": row.status,
            "owner_id": row.owner_id,
            "project_id": row.project_id,
            "daily_log_id": row.daily_log_id,
            "has_people": row.has_people,
            "has_plates": row.has_plates,
            "taken_at": row.taken_at,
            "error": row.error,
            "created_at": row.created_at,
            "finished_at": row.finished_at,
        }


def process_in_pool(raw: bytes, job_id: str) -> ProcessedUpload:
    """Run blur on a pool thread. The caller waits from the event loop."""
    mark(job_id, "running")
    try:
        return process_upload(raw)
    except Exception as exc:
        mark(job_id, "failed", error=str(exc)[:300])
        raise


def jobs_for_log(log_id: str) -> list[dict]:
    with _session() as session:
        rows = session.scalars(select(PhotoJob).where(PhotoJob.daily_log_id == log_id).order_by(PhotoJob.created_at)).all()
    return [
        {
            "id": row.id,
            "status": row.status,
            "has_people": row.has_people,
            "has_plates": row.has_plates,
            "taken_at": row.taken_at,
            "error": row.error,
        }
        for row in rows
    ]
