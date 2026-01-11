from __future__ import annotations
from pathlib import Path
import os

def list_roots() -> list[str]:
    if os.name == "nt":
        return _windows_drives()
    roots = ["/", str(Path.home())]
    vol = Path("/Volumes")
    if vol.exists():
        roots.append(str(vol))
        for p in vol.iterdir():
            if p.is_dir():
                roots.append(str(p))
    return sorted(set(roots))

def _windows_drives() -> list[str]:
    import string
    from ctypes import windll
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if bitmask & (1 << i):
            drives.append(f"{letter}:/")
    return drives
