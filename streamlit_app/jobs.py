"""Small in-memory preview-job runner used by the single-user prototype.

This module deliberately has no FastAPI or Streamlit imports. It can be tested
as ordinary Python and replaced by PostgreSQL/Redis-backed jobs later.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4


class PreviewJobManager:
    """Run preview callables in background threads and expose snapshots.

    A job callable receives one callback:

    ``progress(stage_name, completed_count, total_count, stage_status)``.

    Example: while the second of four stages runs, the manager exposes
    ``current_stage=...``, ``completed=1``, ``total=4`` and ``progress=25``.
    """

    def __init__(self, max_workers: int = 2, retention_minutes: int = 30):
        """Create a bounded worker pool suitable for the one-user prototype."""
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="preview")
        self._retention = timedelta(minutes=retention_minutes)
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def submit(self, calculation) -> dict:
        """Create a PENDING job and schedule its calculation immediately."""
        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        with self._lock:
            self._remove_expired(now)
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "PENDING",
                "current_stage": None,
                "completed_stages": [],
                "completed": 0,
                "total": 0,
                "progress": 0,
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        self._executor.submit(self._run, job_id, calculation)
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        """Return an isolated snapshot so callers cannot mutate job state."""
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def _run(self, job_id: str, calculation) -> None:
        """Execute one calculation and capture either its result or error."""
        self._update(job_id, status="RUNNING")

        def progress(stage: str, completed: int, total: int, stage_status: str) -> None:
            """Translate pipeline callbacks into a poll-friendly job snapshot."""
            with self._lock:
                job = self._jobs[job_id]
                job["current_stage"] = stage
                job["completed"] = completed
                job["total"] = total
                job["progress"] = round((completed / total) * 100) if total else 0
                if stage_status == "COMPLETED" and stage not in job["completed_stages"]:
                    job["completed_stages"].append(stage)
                job["updated_at"] = datetime.now(timezone.utc)

        try:
            result = calculation(progress)
        except Exception as exc:  # The API returns this as job state, not a lost thread exception.
            self._update(job_id, status="FAILED", error=str(exc), progress=100)
            return
        self._update(
            job_id,
            status="COMPLETED",
            result=result,
            progress=100,
            current_stage=None,
        )

    def _update(self, job_id: str, **changes) -> None:
        """Apply one atomic state update under the manager lock."""
        with self._lock:
            self._jobs[job_id].update(changes)
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc)

    def _remove_expired(self, now: datetime) -> None:
        """Bound memory by deleting old terminal jobs when a new job arrives."""
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job["status"] in {"COMPLETED", "FAILED"}
            and now - job["updated_at"] > self._retention
        ]
        for job_id in expired:
            del self._jobs[job_id]
