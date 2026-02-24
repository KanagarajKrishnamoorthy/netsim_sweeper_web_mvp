from __future__ import annotations

from pathlib import Path


def select_directory(title: str | None = None, initial_path: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("Tkinter is not available on this runtime.") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            title=title or "Select Folder",
            initialdir=initial_path or str(Path.home()),
            mustexist=True,
        )
    finally:
        root.destroy()
    if not selected:
        return None
    return str(Path(selected).resolve())


def select_configuration_file(title: str | None = None, initial_path: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("Tkinter is not available on this runtime.") from exc

    initial_dir = Path.home()
    if initial_path:
        as_path = Path(initial_path).expanduser()
        if as_path.exists() and as_path.is_file():
            initial_dir = as_path.parent
        elif as_path.exists() and as_path.is_dir():
            initial_dir = as_path

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title=title or "Select Configuration.netsim",
            initialdir=str(initial_dir),
            filetypes=[("NetSim Configuration", "Configuration.netsim")],
        )
    finally:
        root.destroy()
    if not selected:
        return None
    resolved = Path(selected).resolve()
    if resolved.name != "Configuration.netsim":
        return None
    return str(resolved)


def select_netsimcore_file(title: str | None = None, initial_path: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("Tkinter is not available on this runtime.") from exc

    initial_dir = Path.home()
    if initial_path:
        as_path = Path(initial_path).expanduser()
        if as_path.exists() and as_path.is_file():
            initial_dir = as_path.parent
        elif as_path.exists() and as_path.is_dir():
            initial_dir = as_path

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title=title or "Select NetSimCore.exe",
            initialdir=str(initial_dir),
            filetypes=[("NetSim Core Executable", "NetSimCore.exe"), ("Executable", "*.exe")],
        )
    finally:
        root.destroy()
    if not selected:
        return None
    resolved = Path(selected).resolve()
    if resolved.name.lower() != "netsimcore.exe":
        return None
    return str(resolved)
