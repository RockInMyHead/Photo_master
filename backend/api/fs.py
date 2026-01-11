from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pathlib import Path
import io
import shutil
from PIL import Image

from utils.paths import resolve_path
from utils.fs_utils import list_directory, is_image
from utils.preview_cache import PreviewCache, CacheKey
from settings import settings
from utils.roots import list_roots
from models.fs import MoveRequest

router = APIRouter()
_preview_cache = PreviewCache(max_items=settings.PREVIEW_CACHE_MAX_ITEMS)

@router.get("/roots", response_model=list[str])
def roots():
    return list_roots()

@router.get("/list")
def list_folder(path: str = Query(...)):
    p = resolve_path(path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Папка не найдена")
    return list_directory(p)

@router.post("/move")
def move_file(req: MoveRequest):
    src = resolve_path(req.src)
    dst = resolve_path(req.dst)
    
    if not src.exists():
        raise HTTPException(status_code=404, detail="Исходный файл не найден")
    
    # If dst is a directory, move src into it
    if dst.is_dir():
        dst = dst / src.name
        
    try:
        shutil.move(str(src), str(dst))
        return {"ok": True, "new_path": str(dst)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка перемещения: {str(e)}")

@router.post("/rename")
def rename_file(path: str = Query(...), new_name: str = Query(...)):
    p = resolve_path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Файл или папка не найдены")
    
    new_p = p.parent / new_name
    if new_p.exists():
        raise HTTPException(status_code=400, detail="Файл с таким именем уже существует")
        
    try:
        p.rename(new_p)
        return {"ok": True, "new_path": str(new_p)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка переименования: {str(e)}")

@router.get("/preview")
def preview(path: str = Query(...), size: int = 256):
    p = resolve_path(path)
    if not p.exists() or not p.is_file() or not is_image(p):
        raise HTTPException(status_code=404, detail="Файл не найден или не изображение")

    st = p.stat()
    key = CacheKey(path=str(p), mtime=float(st.st_mtime), size=int(size))
    cached = _preview_cache.get(key)
    if cached is not None:
        return Response(content=cached, media_type="image/jpeg", headers={"Cache-Control":"no-store"})

    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80, optimize=True)
        data = buf.getvalue()

    _preview_cache.put(key, data)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control":"no-store"})
