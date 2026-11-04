"""Resolve the GUI and headless Houdini executables from the same installation."""
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Installation:
    gui: Path
    hython: Path
    source: str
    warning: str = ""


def _pair(gui, source, fallback_version=""):
    gui = Path(gui).expanduser().resolve()
    hython = gui.with_name("hython.exe")
    if not gui.is_file() or not hython.is_file():
        raise FileNotFoundError(f"{source} must select an installation with both houdini.exe and hython.exe: {gui}")
    warning = f"auto-selected Houdini {fallback_version}" if fallback_version else ""
    return Installation(gui, hython, source, warning)


def discover(executable=None, *, visible_versions=None, program_files=None):
    if executable or os.environ.get("HOUDINI_EXE"):
        return _pair(executable or os.environ["HOUDINI_EXE"], "explicit executable")
    if os.environ.get("HFS"):
        return _pair(Path(os.environ["HFS"]) / "bin" / "houdini.exe", "HFS")
    if visible_versions is None:
        from .window import registered
        from .storage import home
        sessions = list(registered(home()))
        primary = [s["version"] for path, s in sessions if path == home()]
        visible_versions = primary or [s["version"] for _, s in sessions]
    base = Path(program_files or os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", "C:/Program Files")) / "Side Effects Software"
    candidates = {}
    for path in base.glob("Houdini *"):
        match = re.fullmatch(r"Houdini (\d+(?:\.\d+)+)", path.name)
        if match and all((path / "bin" / exe).is_file() for exe in ("houdini.exe", "hython.exe")):
            candidates[match.group(1)] = path / "bin" / "houdini.exe"
    versions = set(visible_versions)
    if len(versions) > 1:
        raise ValueError("Multiple managed Houdini versions are live; choose one using HOUDINI_EXE or HFS")
    if versions:
        version = versions.pop()
        if version not in candidates:
            raise FileNotFoundError(f"Cannot locate managed GUI version {version} under {base}; set HOUDINI_EXE or HFS")
        return _pair(candidates[version], "managed GUI")
    if not candidates:
        raise FileNotFoundError(f"No Houdini installation found under {base}; set HOUDINI_EXE or HFS")
    version = max(candidates, key=lambda v: tuple(map(int, v.split("."))))
    return _pair(candidates[version], "installed fallback", version)
