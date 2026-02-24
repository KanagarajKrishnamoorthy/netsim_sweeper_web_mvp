from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models.schemas import EventMessage, SweepJob


@dataclass(frozen=True)
class PersistedEvent:
    event_id: int
    event: EventMessage


class SQLitePersistence:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def _initialize_schema(self) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_events_job_id_event_id ON job_events(job_id, event_id)"
            )
            con.commit()

    def upsert_job(self, job: SweepJob) -> None:
        payload = job.model_dump_json()
        updated_at = datetime.utcnow().isoformat()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO jobs(job_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (job.job_id, payload, updated_at),
            )
            con.commit()

    def list_jobs(self) -> list[SweepJob]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT payload_json FROM jobs").fetchall()
        jobs: list[SweepJob] = []
        for row in rows:
            jobs.append(SweepJob.model_validate_json(row["payload_json"]))
        return jobs

    def get_job(self, job_id: str) -> SweepJob | None:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT payload_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return SweepJob.model_validate_json(row["payload_json"])

    def append_event(self, job_id: str, event: EventMessage) -> int:
        payload = event.model_dump_json()
        now = datetime.utcnow().isoformat()
        with self._lock, self._connect() as con:
            cur = con.execute(
                """
                INSERT INTO job_events(job_id, event_json, created_at)
                VALUES (?, ?, ?)
                """,
                (job_id, payload, now),
            )
            con.commit()
            return int(cur.lastrowid)

    def get_events_since(self, job_id: str, cursor: int) -> tuple[list[PersistedEvent], int]:
        with self._lock, self._connect() as con:
            rows = con.execute(
                """
                SELECT event_id, event_json
                FROM job_events
                WHERE job_id = ? AND event_id > ?
                ORDER BY event_id ASC
                """,
                (job_id, cursor),
            ).fetchall()
        persisted: list[PersistedEvent] = []
        max_cursor = cursor
        for row in rows:
            event_id = int(row["event_id"])
            event = EventMessage.model_validate_json(row["event_json"])
            persisted.append(PersistedEvent(event_id=event_id, event=event))
            max_cursor = max(max_cursor, event_id)
        return persisted, max_cursor

