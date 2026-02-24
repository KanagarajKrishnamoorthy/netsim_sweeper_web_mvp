from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def _host() -> str:
    return os.getenv("NETSIM_SWEEPER_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _port() -> int:
    raw = os.getenv("NETSIM_SWEEPER_PORT", "8090").strip()
    try:
        return int(raw)
    except ValueError:
        return 8090


def _health_url() -> str:
    return f"http://{_host()}:{_port()}/api/health"


def _ui_url() -> str:
    return f"http://{_host()}:{_port()}/"


def _is_backend_alive() -> bool:
    try:
        with urllib.request.urlopen(_health_url(), timeout=1.2) as response:
            return response.status == 200
    except urllib.error.URLError:
        return False
    except Exception:
        return False


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _find_backend_exe(base_dir: Path) -> Path | None:
    candidates = [
        base_dir / "backend" / "NetSimSweeperBackend.exe",
        base_dir / "NetSimSweeperBackend" / "NetSimSweeperBackend.exe",
        base_dir / "NetSimSweeperBackend.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _start_backend(backend_exe: Path) -> None:
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    env = os.environ.copy()
    env["NETSIM_SWEEPER_AUTO_SHUTDOWN_ON_UI_CLOSE"] = "1"
    env.setdefault("NETSIM_SWEEPER_UI_HEARTBEAT_TTL_SECONDS", "25")
    env.setdefault("NETSIM_SWEEPER_IDLE_SHUTDOWN_GRACE_SECONDS", "45")
    subprocess.Popen(
        [str(backend_exe)],
        cwd=str(backend_exe.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags,
        close_fds=True,
    )


def _wait_for_backend(timeout_seconds: float = 30.0) -> bool:
    started = time.time()
    while time.time() - started < timeout_seconds:
        if _is_backend_alive():
            return True
        time.sleep(0.4)
    return False


def main() -> int:
    if _is_backend_alive():
        webbrowser.open(_ui_url())
        return 0

    backend_exe = _find_backend_exe(_runtime_base_dir())
    if backend_exe is None:
        print("NetSimSweeper backend executable not found.")
        print("Expected one of:")
        print(r"  .\backend\NetSimSweeperBackend.exe")
        print(r"  .\NetSimSweeperBackend\NetSimSweeperBackend.exe")
        return 2

    _start_backend(backend_exe)
    if not _wait_for_backend():
        print("NetSimSweeper backend did not become ready in time.")
        print(f"Try opening {_ui_url()} manually after a few seconds.")
        return 3

    webbrowser.open(_ui_url())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
