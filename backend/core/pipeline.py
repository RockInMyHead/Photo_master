# backend/core/pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Callable, Dict, List
import asyncio

from utils.fs_utils import IMG_EXTS
from core.distributor import distribute_plan
from core.insightface_engine import init_engine, extract_faces_batch, FaceRecord
from core.quality_cluster import cluster_quality

def collect_images(folder: Path) -> List[Path]:
    import os
    # Список имен папок, которые нужно полностью пропускать
    SKIP_FOLDERS = {
        "общие", "shared", "public", "system", "библиотека", "library",
        "temp", "tmp", "cache", "logs", "thumbnails", "previews"
    }

    images = []
    for root, dirs, files in os.walk(folder):
        # Фильтруем папки: исключаем скрытые (.), SKIP_FOLDERS и цифровые кластеры (папки 1, 2, 3...)
        # Это предотвращает повторную обработку уже отсортированных фото.
        dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in SKIP_FOLDERS and not d.isdigit()]

        for file in files:
            # Исключаем скрытые файлы
            if file.startswith('.'):
                continue

            p = Path(root) / file
            if p.suffix.lower() in IMG_EXTS:
                images.append(p)

    return images

def build_plan_from_faces(faces: List[FaceRecord], labels: List[int]) -> List[Dict]:
    image_to_clusters: Dict[str, set[int]] = {}
    for fr, lbl in zip(faces, labels):
        image_to_clusters.setdefault(fr.image_path, set())
        if lbl != -1:
            image_to_clusters[fr.image_path].add(int(lbl))
    return [{"path": img, "clusters": sorted(list(cset))} for img, cset in image_to_clusters.items()]

def create_empty_folders(root: Path) -> None:
    """Создает 2 пустые папки с учетом нумерации существующих папок"""
    # Находим все папки с числовыми именами
    numeric_folders = []
    for item in root.iterdir():
        if item.is_dir() and item.name.isdigit():
            try:
                numeric_folders.append(int(item.name))
            except ValueError:
                continue
    
    # Находим максимальный номер
    max_num = max(numeric_folders) if numeric_folders else 0
    
    # Создаем 2 пустые папки
    for i in range(1, 3):
        folder_num = max_num + i
        folder_path = root / str(folder_num)
        folder_path.mkdir(exist_ok=True)
        print(f"Created empty folder: {folder_path}")

async def process_folder(
    path: Path,
    *,
    joint_mode: str,
    singletons: bool,
    progress: Callable[[int, str], None],
) -> Dict:
    # Консервативные параметры (качество)
    link_sim = 0.62
    merge_sim = 0.74
    assign_sim = 0.68
    min_intra_sim = 0.55

    progress(2, "Подготовка")
    progress(3, "Сканирование файлов")
    images = collect_images(path)
    if not images:
        progress(100, "Нет изображений")
        return {"moved": 0, "copied": 0, "clusters": 0, "no_faces": 0, "unreadable": 0}

    progress(8, "Инициализация модели")
    await asyncio.to_thread(init_engine, det_size=(1280, 1280), det_thresh=0.65)

    progress(25, "Детект лиц и эмбеддинги")
    try:
        print(f"Starting face extraction for {len(images)} images")
        # Process images in batches to avoid blocking too long
        batch_size = 5
        face_recs = []
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            print(f"Processing batch {i//batch_size + 1}/{(len(images) + batch_size - 1)//batch_size}: {len(batch)} images")

            batch_faces = await asyncio.to_thread(
                extract_faces_batch,
                [str(p) for p in batch],
                min_face_px=40,
            )
            face_recs.extend(batch_faces)
            print(f"Batch completed: {len(batch_faces)} faces found")

            # Update progress within face detection
            progress_pct = 25 + int(30 * (i + len(batch)) / len(images))
            progress(progress_pct, f"Обработка лиц: {i + len(batch)}/{len(images)} изображений")

        print(f"Total extracted {len(face_recs)} face records from {len(images)} images")
    except Exception as e:
        print(f"Error in face extraction: {e}")
        import traceback
        traceback.print_exc()
        raise

    with_faces = set(fr.image_path for fr in face_recs)
    no_face_imgs = [p for p in images if str(p) not in with_faces]

    if len(face_recs) == 0:
        progress(100, "Лиц не найдено")
        return {"moved": 0, "copied": 0, "clusters": 0, "no_faces": len(images), "unreadable": 0}

    progress(55, "Кластеризация: Agglomerative + merge + reassignment")
    embs = [fr.embedding for fr in face_recs]
    print(f"Got {len(embs)} embeddings, type of first: {type(embs[0]) if embs else 'None'}")
    if len(embs) == 0:
        progress(100, "Нет эмбеддингов для кластеризации")
        return {"moved": 0, "copied": 0, "clusters": 0, "no_faces": len(no_face_imgs), "unreadable": 0}

    # Convert numpy arrays to lists for cluster_quality function
    embs_lists = []
    for emb in embs:
        if hasattr(emb, 'tolist'):
            embs_lists.append(emb.tolist())
        elif isinstance(emb, list):
            embs_lists.append(emb)
        else:
            embs_lists.append(list(emb))
    print(f"Converted to {len(embs_lists)} embedding lists, type of first: {type(embs_lists[0]) if embs_lists else 'None'}")

    try:
        print(f"Starting clustering with {len(embs_lists)} embeddings")
        labels0, _out_idx = await asyncio.to_thread(
            cluster_quality,
            embs_lists,
            link_sim=link_sim,
            merge_sim=merge_sim,
            assign_sim=assign_sim,
            min_intra_sim=min_intra_sim,
        )
        print(f"Clustering completed: {len(set(labels0))} clusters, {len(_out_idx)} outliers")
    except Exception as e:
        print(f"Error in clustering: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Папки 1..N
    uniq = sorted(set([x for x in labels0 if x != -1]))
    remap = {old: i + 1 for i, old in enumerate(uniq)}
    labels = [(remap[x] if x != -1 else -1) for x in labels0]

    progress(75, "План раскладки")
    plan = build_plan_from_faces(face_recs, labels)

    # Фото без лиц => clusters=[]
    for p in no_face_imgs:
        plan.append({"path": str(p), "clusters": []})

    progress(90, "Распределение по папкам")
    stats = await asyncio.to_thread(
        distribute_plan,
        plan,
        path,
        joint_mode=joint_mode,
        singletons=singletons,
    )

    # Создаем 2 пустые папки с учетом нумерации
    progress(95, "Создание пустых папок")
    await asyncio.to_thread(create_empty_folders, path)

    progress(100, "Готово")
    return {**stats, "no_faces": len(no_face_imgs), "unreadable": 0}
