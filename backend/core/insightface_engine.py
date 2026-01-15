# backend/core/insightface_engine.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple, Optional
import numpy as np
import cv2

_APP = None

@dataclass
class FaceRecord:
    image_path: str
    face_index: int
    embedding: np.ndarray
    det_score: float
    bbox: Tuple[float, float, float, float]

def _l2norm(x: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(x))
    return x if n <= 1e-12 else (x / n)

def _tta_embedding(app, img_bgr, face) -> Optional[np.ndarray]:
    # recognition model доступен как app.models['recognition'] (dict taskname->model)
    rec = getattr(app, "models", {}).get("recognition")
    if rec is None or getattr(face, "kps", None) is None:
        return None

    from insightface.utils import face_align

    # выравнивание под ArcFace input
    aimg = face_align.norm_crop(img_bgr, landmark=face.kps, image_size=rec.input_size[0])
    aimg_f = cv2.flip(aimg, 1)

    feats = rec.get_feat([aimg, aimg_f])  # (2, D)
    emb = feats.mean(axis=0).astype(np.float32).reshape(-1)
    return _l2norm(emb)

def init_engine(*, det_size=(1280, 1280), det_thresh: float = 0.65) -> None:
    global _APP
    if _APP is not None:
        return
    from insightface.app import FaceAnalysis

    # quality-first: пробуем CUDA, но обязательно есть fallback на CPU
    try:
        _APP = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _APP.prepare(ctx_id=0, det_size=det_size, det_thresh=det_thresh)
    except Exception:
        _APP = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _APP.prepare(ctx_id=-1, det_size=det_size, det_thresh=det_thresh)

def extract_faces(image_path: str, *, min_face_px: int = 40) -> List[FaceRecord]:
    if _APP is None:
        init_engine()

    p = Path(image_path)

    # Важно: unicode-safe чтение на Windows
    try:
        data = np.fromfile(str(p), dtype=np.uint8)
        img_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return []

        # ВАЖНО: FaceAnalysis.get ожидает BGR (OpenCV), НЕ RGB
        faces = _APP.get(img_bgr)
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return []

    out: List[FaceRecord] = []
    for i, face in enumerate(faces):
        bbox = tuple(float(x) for x in face.bbox.tolist())
        x1, y1, x2, y2 = bbox
        if (x2 - x1) < min_face_px or (y2 - y1) < min_face_px:
            continue

        emb = _tta_embedding(_APP, img_bgr, face)
        if emb is None:
            emb = getattr(face, "normed_embedding", None)
            if emb is None:
                emb = getattr(face, "embedding", None)
            if emb is None:
                continue
            emb = _l2norm(np.asarray(emb, dtype=np.float32).reshape(-1))

        out.append(FaceRecord(
            image_path=str(p),
            face_index=i,
            embedding=emb,
            det_score=float(getattr(face, "det_score", 1.0)),
            bbox=bbox,
        ))
    return out

def extract_faces_batch(image_paths: Iterable[str], *, min_face_px: int = 40) -> List[FaceRecord]:
    recs: List[FaceRecord] = []
    for path in image_paths:
        recs.extend(extract_faces(path, min_face_px=min_face_px))
    return recs
