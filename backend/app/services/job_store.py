from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.schemas import EventMessage, JobStatus, SweepJob
from app.services.persistence import SQLitePersistence


@dataclass
class JobRuntimeState:
    cancel_requested: bool = False


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._lock = threading.RLock()
        self._persistence = SQLitePersistence(db_path=db_path)
        self._jobs: dict[str, SweepJob] = {}
        self._runtime: dict[str, JobRuntimeState] = {}
        self._load_jobs_from_db()

    def _load_jobs_from_db(self) -> None:
        jobs = self._persistence.list_jobs()
        for job in jobs:
            if not (job.run_name or "").strip():
                try:
                    parent_name = Path(job.output_directory).resolve().parent.name
                    job.run_name = parent_name if parent_name else job.job_id
                except Exception:
                    job.run_name = job.job_id
            if job.status == JobStatus.running:
                job.status = JobStatus.draft
                job.warnings.append(
                    "Recovered from persistent storage while previously running. "
                    "Use resume endpoint to continue pending runs."
                )
            self._jobs[job.job_id] = job
            self._runtime[job.job_id] = JobRuntimeState()
            self._persistence.upsert_job(job)

    def create(self, job: SweepJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = copy.deepcopy(job)
            self._runtime[job.job_id] = JobRuntimeState()
            self._persistence.upsert_job(job)
            self._append_event_locked(
                job.job_id,
                "job_created",
                {"status": job.status, "planned_runs": job.planned_run_count},
            )

    def list_jobs(self) -> list[SweepJob]:
        with self._lock:
            return [copy.deepcopy(job) for job in self._jobs.values()]

    def get(self, job_id: str) -> SweepJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def update(self, job: SweepJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = copy.deepcopy(job)
            self._persistence.upsert_job(job)

    def request_cancel(self, job_id: str) -> bool:
        with self._lock:
            state = self._runtime.get(job_id)
            if not state:
                return False
            state.cancel_requested = True
            self._append_event_locked(job_id, "cancel_requested", {})
            return True

    def clear_cancel(self, job_id: str) -> None:
        with self._lock:
            state = self._runtime.get(job_id)
            if state:
                state.cancel_requested = False

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            state = self._runtime.get(job_id)
            return bool(state and state.cancel_requested)

    def append_event(self, job_id: str, event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._append_event_locked(job_id, event, payload)

    def _append_event_locked(self, job_id: str, event: str, payload: dict[str, Any]) -> None:
        event_message = EventMessage(
            event=event,
            timestamp=datetime.utcnow(),
            payload=payload,
        )
        self._persistence.append_event(job_id=job_id, event=event_message)

    def get_events_since(self, job_id: str, cursor: int) -> tuple[list[EventMessage], int]:
        with self._lock:
            persisted, new_cursor = self._persistence.get_events_since(job_id, cursor)
            events = [item.event for item in persisted]
            return events, new_cursor


job_store = JobStore(
    db_path=settings.resolved_app_data_dir() / "jobs.db",
)
