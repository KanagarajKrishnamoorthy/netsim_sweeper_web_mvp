from __future__ import annotations

import os
from pathlib import Path

from app.models.schemas import PathValidationResult


def validate_scenario_folder(path_text: str) -> PathValidationResult:
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        return PathValidationResult(path=str(path), exists=False, valid=False, message="Folder does not exist.")
    if not path.is_dir():
        return PathValidationResult(path=str(path), exists=True, valid=False, message="Path is not a folder.")
    config = path / "Configuration.netsim"
    if config.exists():
        return PathValidationResult(
            path=str(path),
            exists=True,
            valid=True,
            message="Valid scenario folder. Configuration.netsim found directly in selected folder.",
        )
    return PathValidationResult(
        path=str(path),
        exists=True,
        valid=False,
        message="Configuration.netsim not found directly in selected folder (subfolder matches are not accepted).",
    )


def validate_netsim_bin_folder(path_text: str) -> PathValidationResult:
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        return PathValidationResult(path=str(path), exists=False, valid=False, message="Path does not exist.")
    if path.is_file():
        if path.name.lower() == "netsimcore.exe":
            return PathValidationResult(
                path=str(path),
                exists=True,
                valid=True,
                message="Valid NetSimCore executable path selected.",
            )
        return PathValidationResult(
            path=str(path),
            exists=True,
            valid=False,
            message="Selected file is not NetSimCore.exe.",
        )

    if not path.is_dir():
        return PathValidationResult(path=str(path), exists=True, valid=False, message="Path is not a file/folder.")

    core_a = path / "NetSimcore.exe"
    core_b = path / "NetSimCore.exe"
    if core_a.exists() or core_b.exists():
        return PathValidationResult(
            path=str(path),
            exists=True,
            valid=True,
            message="Valid NetSim folder. NetSimCore.exe found directly in selected folder.",
        )
    return PathValidationResult(
        path=str(path),
        exists=True,
        valid=False,
        message="NetSimCore.exe not found directly in selected folder (subfolder matches are not accepted).",
    )


def validate_output_root(path_text: str) -> PathValidationResult:
    path = Path(path_text).expanduser().resolve()
    if path.exists() and path.is_file():
        return PathValidationResult(path=str(path), exists=True, valid=False, message="Path is a file, not a folder.")
    if path.exists() and path.is_dir():
        return PathValidationResult(path=str(path), exists=True, valid=True, message="Existing output root is valid.")
    try:
        path.mkdir(parents=True, exist_ok=True)
        return PathValidationResult(
            path=str(path),
            exists=path.exists(),
            valid=True,
            message="Output root does not exist yet; it can be created.",
        )
    except OSError as exc:
        return PathValidationResult(
            path=str(path),
            exists=False,
            valid=False,
            message=f"Output root is not writable/creatable: {exc}",
        )
