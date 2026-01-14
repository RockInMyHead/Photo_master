from fastapi import APIRouter, HTTPException, Query
from pathlib import Path
from typing import Optional
import json
import re
import numpy as np

from utils.paths import resolve_path
from utils.fs_utils import IMG_EXTS
from core.insightface_engine import extract_faces

router = APIRouter()

def _load_centroids(root: Path) -> dict:
    p = root / ".face_index" / "centroids.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Индекс кластеров не найден (.face_index/centroids.json)")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось прочитать индекс кластеров: {e}")

def _find_cluster_folder(root: Path, cid: str) -> Optional[Path]:
    # после rename папки выглядят как "3 (128)" или "3 (128)_1"
    pat = re.compile(rf"^{re.escape(cid)}\b")
    for p in root.iterdir():
        if p.is_dir() and (p.name == cid or pat.match(p.name)):
            return p
    return None

def _pick_example_image(folder: Path) -> Optional[str]:
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            return str(p)
    return None

@router.get("/candidates")
def candidates(
    root: str = Query(...),
    path: str = Query(...),
    top_k: int = Query(5, ge=1, le=20),
):
    root_p = resolve_path(root)
    img_p = resolve_path(path)

    if not root_p.exists() or not root_p.is_dir():
        raise HTTPException(status_code=404, detail="Корневая папка не найдена")
    if not img_p.exists() or not img_p.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    idx = _load_centroids(root_p)
    clusters = idx.get("clusters", {})
    if not clusters:
        raise HTTPException(status_code=400, detail="В индексе нет кластеров")

    # матрица центроидов
    cids = sorted(clusters.keys(), key=lambda x: int(x) if x.isdigit() else x)
    C = np.stack([np.asarray(clusters[c]["centroid"], dtype=np.float32) for c in cids], axis=0)  # (K, D)

    # извлекаем лица из изображения (может быть несколько)
    import cv2
    data = np.fromfile(str(img_p), dtype=np.uint8)
    img_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img_bgr is None:
        return {"root": str(root_p), "image_path": str(img_p), "faces": []}
    
    h, w = img_bgr.shape[:2]
    faces = extract_faces(str(img_p), min_face_px=40)
    if not faces:
        return {"root": str(root_p), "image_path": str(img_p), "faces": []}

    out_faces = []
    for fr in faces:
        emb = np.asarray(fr.embedding, dtype=np.float32).reshape(-1)
        sims = (C @ emb).astype(float)  # cosine similarity, т.к. всё L2-нормировано

        # top-k
        order = np.argsort(-sims)[:top_k]
        cand = []
        for j in order.tolist():
            cid = cids[j]
            folder = _find_cluster_folder(root_p, cid)
            if folder is None:
                continue
            example = _pick_example_image(folder)
            s = float(sims[j])
            cand.append({
                "cluster_id": int(cid) if cid.isdigit() else cid,
                "folder_name": folder.name,
                "folder_path": str(folder),
                "score": round(s, 4),
                "percent": round(s * 100.0, 1),
                "example_image": example,
            })

        # convert bbox to percentages
        x1, y1, x2, y2 = fr.bbox
        bbox_pct = [
            round(x1 / w * 100, 2),
            round(y1 / h * 100, 2),
            round(x2 / w * 100, 2),
            round(y2 / h * 100, 2)
        ]

        out_faces.append({
            "face_index": fr.face_index,
            "bbox": bbox_pct,
            "det_score": round(float(fr.det_score), 4),
            "candidates": cand,
        })

    return {"root": str(root_p), "image_path": str(img_p), "faces": out_faces}

