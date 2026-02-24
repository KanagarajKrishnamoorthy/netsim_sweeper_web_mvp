from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _default_app_data_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / "NetSimSweeper"
    return (_runtime_root() / "data").resolve()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("NETSIM_SWEEPER_HOST", "127.0.0.1")
    port: int = _int_env("NETSIM_SWEEPER_PORT", 8090)
    max_runs: int = _int_env("NETSIM_SWEEPER_MAX_RUNS", 2000)
    default_output_root: str = os.getenv("NETSIM_SWEEPER_DEFAULT_OUTPUT_ROOT", "")
    app_data_dir: str = os.getenv("NETSIM_SWEEPER_APPDATA_DIR", "")
    frontend_dist_dir: str = os.getenv("NETSIM_SWEEPER_FRONTEND_DIST", "")

    def runtime_root(self) -> Path:
        return _runtime_root()

    def resolved_app_data_dir(self) -> Path:
        if self.app_data_dir.strip():
            return Path(self.app_data_dir).expanduser().resolve()
        return _default_app_data_dir()

    def resolved_default_output_root(self) -> Path:
        if self.default_output_root.strip():
            return Path(self.default_output_root).expanduser().resolve()
        docs = Path.home() / "Documents"
        return (docs / "NetSim Multi-Parameter Sweeper").resolve()

    def resolved_frontend_dist_dir(self) -> Path | None:
        if self.frontend_dist_dir.strip():
            path = Path(self.frontend_dist_dir).expanduser().resolve()
            return path if path.exists() else None

        candidates = [
            self.runtime_root() / "frontend_dist",
            self.runtime_root() / "_internal" / "frontend_dist",
            self.runtime_root().parent / "frontend" / "dist",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None


settings = Settings()
