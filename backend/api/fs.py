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
from models.fs import MoveRequest, CreateFoldersRequest, UpdateCountsRequest

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

@router.post("/copy")
def copy_file(req: MoveRequest):
    src = resolve_path(req.src)
    dst = resolve_path(req.dst)
    
    if not src.exists():
        raise HTTPException(status_code=404, detail="Исходный файл не найден")
    
    # If dst is a directory, copy src into it
    if dst.is_dir():
        dst = dst / src.name
        
    try:
        shutil.copy2(str(src), str(dst))
        return {"ok": True, "new_path": str(dst)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка копирования: {str(e)}")

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

    try:
        with Image.open(p) as im:
            im = im.convert("RGB")

            # Calculate new size maintaining aspect ratio
            width, height = im.size
            if width > height:
                new_width = size
                new_height = int(height * size / width)
            else:
                new_height = size
                new_width = int(width * size / height)

            # Use high-quality resize with Lanczos filter
            im = im.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create square canvas if needed
            if new_width != size or new_height != size:
                square_img = Image.new('RGB', (size, size), (255, 255, 255))
                # Center the image
                x_offset = (size - new_width) // 2
                y_offset = (size - new_height) // 2
                square_img.paste(im, (x_offset, y_offset))
                im = square_img

            buf = io.BytesIO()
            # High quality JPEG with better compression settings
            im.save(buf, format="JPEG", quality=95, optimize=True, progressive=True)
            data = buf.getvalue()
    except Exception as e:
        # If image processing fails, return a placeholder or error
        print(f"Error processing image {p}: {e}")
        # Return a simple 1x1 pixel transparent image
        buf = io.BytesIO()
        placeholder = Image.new('RGB', (1, 1), color=(200, 200, 200))
        placeholder.save(buf, format="JPEG", quality=80)
        data = buf.getvalue()

    _preview_cache.put(key, data)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control":"no-store"})

@router.post("/create-folders")
def create_folders(req: CreateFoldersRequest):
    """Создает 2 новые папки с продолжением нумерации"""
    root = resolve_path(req.path)
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Папка не найдена")
    
    import re
    # Находим все числовые папки
    numeric_folders = []
    for item in root.iterdir():
        if not item.is_dir():
            continue
        # Обрабатываем форматы: "22", "22 (15)", "22 (15)_1"
        match = re.match(r'^(\d+)', item.name)
        if match:
            num = int(match.group(1))
            numeric_folders.append(num)
    
    # Определяем следующий номер
    next_num = max(numeric_folders, default=0) + 1
    
    created = []
    for i in range(2):
        folder_name = str(next_num + i)
        folder_path = root / folder_name
        if folder_path.exists():
            raise HTTPException(status_code=400, detail=f"Папка {folder_name} уже существует")
        folder_path.mkdir(parents=True, exist_ok=True)
        created.append(folder_name)
    
    return {"success": True, "created": created, "message": f"Созданы папки: {', '.join(created)}"}

@router.post("/update-counts")
def update_counts(req: UpdateCountsRequest):
    """Обновляет счетчики файлов в названиях папок"""
    root = resolve_path(req.path)
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Папка не найдена")
    
    import re
    updated = []
    
    for item in root.iterdir():
        if not item.is_dir():
            continue
        
        # Извлекаем базовый номер из имени папки
        match = re.match(r'^(\d+)', item.name)
        if not match:
            continue
        
        base_num = int(match.group(1))
        # Считаем файлы в папке
        file_count = len([f for f in item.iterdir() if f.is_file()])
        
        # Формируем новое имя
        new_name = f"{base_num} ({file_count})"
        new_path = root / new_name
        
        # Если имя уже занято (не этой же папкой), добавляем суффикс
        if new_path.exists() and new_path != item:
            counter = 1
            while new_path.exists():
                new_name = f"{base_num} ({file_count})_{counter}"
                new_path = root / new_name
                counter += 1
        
        # Переименовываем только если имя изменилось
        if item.name != new_name:
            try:
                item.rename(new_path)
                updated.append({"old": item.name, "new": new_name})
            except Exception as e:
                print(f"Failed to rename {item.name}: {e}")
    
    return {"success": True, "updated": updated, "message": f"Обновлено папок: {len(updated)}"}
