from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Callable

from app.core.config import settings
from app.models.schemas import LicenseMode, SessionConfig
from app.services.file_plan import build_copy_plan


def _timestamp_suffix() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _license_arg(session: SessionConfig) -> str:
    if session.license.mode == LicenseMode.license_server:
        return str(session.license.license_server)
    return str(session.license.license_file_path)


def resolve_netsimcore_path(path_text: str) -> tuple[Path, Path]:
    raw = Path(path_text).expanduser().resolve()
    if raw.exists() and raw.is_file():
        if raw.name.lower() != "netsimcore.exe":
            raise RuntimeError(f"Selected executable is not NetSimCore.exe: {raw}")
        return raw, raw.parent

    if raw.exists() and raw.is_dir():
        direct_a = raw / "NetSimcore.exe"
        direct_b = raw / "NetSimCore.exe"
        if direct_a.exists():
            return direct_a.resolve(), raw
        if direct_b.exists():
            return direct_b.resolve(), raw
        raise RuntimeError(f"NetSimCore.exe not found directly in folder: {raw}")

    raise RuntimeError(f"NetSim path does not exist: {raw}")


def _windows_hidden_process_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def run_netsim_once(
    session: SessionConfig,
    io_dir: Path,
    on_console: Callable[[str], None] | None = None,
) -> Path:
    netsimcore, netsim_bin = resolve_netsimcore_path(session.netsim_bin_path)
    if not io_dir.exists():
        raise RuntimeError(f"IO path does not exist: {io_dir}")
    if not (io_dir / "Configuration.netsim").exists():
        raise RuntimeError(f"Configuration.netsim missing in IO path: {io_dir}")

    env = os.environ.copy()
    env["NETSIM_AUTO"] = "1"
    command = [
        str(netsimcore),
        "-apppath",
        str(netsim_bin),
        "-iopath",
        str(io_dir),
        "-license",
        _license_arg(session),
    ]
    hidden_process_kwargs = _windows_hidden_process_kwargs()
    if on_console is None:
        subprocess.run(
            command,
            cwd=str(netsim_bin),
            env=env,
            check=True,
            **hidden_process_kwargs,
        )
    else:
        process = subprocess.Popen(
            command,
            cwd=str(netsim_bin),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **hidden_process_kwargs,
        )
        assert process.stdout is not None
        for line in process.stdout:
            on_console(line.rstrip("\n"))
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"NetSim process failed with exit code {return_code}")

    metrics_path = io_dir / "Metrics.xml"
    if not metrics_path.exists():
        raise RuntimeError("NetSim run completed but Metrics.xml was not generated.")
    return metrics_path


def _copy_inputs_for_bootstrap(scenario_dir: Path, dst: Path) -> None:
    copy_items, _ = build_copy_plan(
        scenario_directory=scenario_dir,
        include_patterns=[],
        exclude_patterns=[],
    )
    for item in copy_items:
        src = scenario_dir / item.relative_path
        target = dst / item.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def generate_bootstrap_metrics(
    configuration_path: Path,
    session: SessionConfig,
    persist_generated_metrics: bool = False,
    temp_root: Path | None = None,
) -> Path:
    scenario_dir = configuration_path.parent
    root = (
        temp_root
        if temp_root is not None
        else settings.resolved_app_data_dir() / "bootstrap_runs"
    )
    workspace = root / f"{_timestamp_suffix()}_{uuid.uuid4().hex[:8]}"
    io_dir = workspace / "io"
    io_dir.mkdir(parents=True, exist_ok=True)

    _copy_inputs_for_bootstrap(scenario_dir, io_dir)
    if not (io_dir / "Configuration.netsim").exists():
        shutil.copy2(configuration_path, io_dir / "Configuration.netsim")

    metrics_path = run_netsim_once(session=session, io_dir=io_dir)

    if persist_generated_metrics:
        persisted = scenario_dir / "Metrics.xml"
        shutil.copy2(metrics_path, persisted)
        return persisted
    return metrics_path
