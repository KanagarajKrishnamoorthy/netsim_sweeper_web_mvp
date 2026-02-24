from __future__ import annotations

import os
import threading
import time
from typing import Any

from app.models.schemas import JobStatus
from app.services.job_store import job_store


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class RuntimeGuard:
    def __init__(self) -> None:
        self._enabled = _bool_env("NETSIM_SWEEPER_AUTO_SHUTDOWN_ON_UI_CLOSE", False)
        self._heartbeat_ttl_seconds = max(_int_env("NETSIM_SWEEPER_UI_HEARTBEAT_TTL_SECONDS", 25), 5)
        self._idle_grace_seconds = max(_int_env("NETSIM_SWEEPER_IDLE_SHUTDOWN_GRACE_SECONDS", 45), 10)
        self._check_interval_seconds = 2
        self._started_at = time.monotonic()
        self._ever_had_ui_session = False
        self._session_seen_at: dict[str, float] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._watch_loop, name="netsim-runtime-guard", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)

    def heartbeat(self, session_id: str) -> dict[str, Any]:
        if not session_id.strip():
            return {"ok": False, "active_sessions": self.active_session_count(), "message": "session_id is empty"}
        with self._lock:
            self._ever_had_ui_session = True
            self._session_seen_at[session_id.strip()] = time.monotonic()
            self._cleanup_stale_sessions_locked()
            active = len(self._session_seen_at)
        return {"ok": True, "active_sessions": active}

    def disconnect(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            self._session_seen_at.pop(session_id.strip(), None)
            self._cleanup_stale_sessions_locked()
            active = len(self._session_seen_at)
        return {"ok": True, "active_sessions": active}

    def active_session_count(self) -> int:
        with self._lock:
            self._cleanup_stale_sessions_locked()
            return len(self._session_seen_at)

    def _cleanup_stale_sessions_locked(self) -> None:
        now = time.monotonic()
        stale_ids = [
            session_id
            for session_id, seen_at in self._session_seen_at.items()
            if now - seen_at > self._heartbeat_ttl_seconds
        ]
        for session_id in stale_ids:
            self._session_seen_at.pop(session_id, None)

    def _within_startup_grace(self) -> bool:
        with self._lock:
            if self._ever_had_ui_session:
                return False
        return time.monotonic() - self._started_at < self._idle_grace_seconds

    def _has_running_jobs(self) -> bool:
        for job in job_store.list_jobs():
            if job.status == JobStatus.running:
                return True
        return False

    def _watch_loop(self) -> None:
        while not self._stop_event.wait(self._check_interval_seconds):
            # Keep startup grace only until the first UI session connects.
            if self._within_startup_grace():
                continue
            if self._has_running_jobs():
                continue
            if self.active_session_count() > 0:
                continue
            os._exit(0)


runtime_guard = RuntimeGuard()
