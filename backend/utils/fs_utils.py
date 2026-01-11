from pathlib import Path
from models.fs import FsEntry

IMG_EXTS = {".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff"}

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMG_EXTS

def find_preview_image(path: Path, depth: int = 0) -> str | None:
    if depth > 2:  # Limit recursion depth for performance
        return None
        
    if path.is_file():
        return str(path) if is_image(path) else None
    
    try:
        # 1. First look for images in current directory
        for entry in path.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_file() and is_image(entry):
                return str(entry)
        
        # 2. If no images, look in subdirectories
        for entry in path.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                res = find_preview_image(entry, depth + 1)
                if res:
                    return res
    except Exception:
        pass
    return None

def list_directory(path: Path) -> list[FsEntry]:
    entries: list[FsEntry] = []
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        try:
            st = entry.stat()
            is_dir = entry.is_dir()
            entries.append(FsEntry(
                name=entry.name,
                path=str(entry),
                type="directory" if is_dir else "file",
                size=None if is_dir else int(st.st_size),
                mtime=float(st.st_mtime),
                preview_path=find_preview_image(entry)
            ))
        except Exception:
            continue
    return sorted(entries, key=lambda e: (e.type != "directory", e.name.lower()))
