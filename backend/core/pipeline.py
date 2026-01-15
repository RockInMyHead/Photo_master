# backend/core/pipeline.py
import json
import numpy as np
import asyncio
import shutil
from datetime import datetime
from typing import Callable, Dict, List, Tuple, Optional
from pathlib import Path
from collections import defaultdict

from utils.fs_utils import IMG_EXTS
from core.distributor import distribute_plan
from core.insightface_engine import init_engine, extract_faces_batch, FaceRecord
from core.quality_cluster import cluster_quality

def _l2norm_rows(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    return X / n

def apply_confidence_gating(
    embeddings: np.ndarray,             # (N, D) L2-normed
    labels: List[int],                  # -1 or 1..K (или 0..K-1 — неважно, главное не -1)
    *,
    keep_sim: float = 0.48,             # порог "лицо уверенно в своём кластере"
    min_cluster_size: int = 3,          # всё, что меньше — подозрительно
    small_cluster_keep_sim: float = 0.54,  # более строгий порог для маленьких кластеров
    min_cluster_mean_sim: float = 0.50,    # средняя плотность кластера к центроиду
) -> Tuple[List[int], Dict[int, Dict[str, float]]]:
    """
    Возвращает новые labels и метрики по кластерам.
    Логика:
      - если sim(face, centroid(label)) < keep_sim -> label=-1
      - если кластер маленький и не плотный -> все его элементы label=-1
    """
    labels = list(labels)
    n = embeddings.shape[0]
    if n == 0:
        return labels, {}

    # собрать индексы по кластерам (игнорируем -1)
    by_cluster = defaultdict(list)
    for i, lbl in enumerate(labels):
        if lbl != -1:
            by_cluster[lbl].append(i)

    if not by_cluster:
        return labels, {}

    # центроиды
    centroids: Dict[int, np.ndarray] = {}
    for lbl, idxs in by_cluster.items():
        C = embeddings[idxs].mean(axis=0)
        C = C / (np.linalg.norm(C) + 1e-12)
        centroids[lbl] = C

    # sim каждого лица к центроиду своего кластера
    sim_to_own = np.full((n,), -1.0, dtype=np.float32)
    for lbl, idxs in by_cluster.items():
        C = centroids[lbl]
        sims = embeddings[idxs] @ C
        sim_to_own[idxs] = sims

    # метрики кластеров
    metrics = {}
    for lbl, idxs in by_cluster.items():
        mean_sim = float(sim_to_own[idxs].mean()) if idxs else 0.0
        min_sim = float(sim_to_own[idxs].min()) if idxs else 0.0
        metrics[lbl] = {
            "size": float(len(idxs)),
            "mean_sim": mean_sim,
            "min_sim": min_sim,
        }

    # 1) выброс лиц с низкой уверенностью
    for i, lbl in enumerate(labels):
        if lbl == -1:
            continue
        thr = small_cluster_keep_sim if len(by_cluster[lbl]) < min_cluster_size else keep_sim
        if sim_to_own[i] < thr:
            labels[i] = -1

    # 2) выброс маленьких/рыхлых кластеров целиком
    # пересобираем after face-level filtering
    by_cluster2 = defaultdict(list)
    for i, lbl in enumerate(labels):
        if lbl != -1:
            by_cluster2[lbl].append(i)

    for lbl, idxs in by_cluster2.items():
        if len(idxs) < min_cluster_size:
            # кластер маленький — оставляем только если он очень плотный
            mean_sim = float((embeddings[idxs] @ centroids[lbl]).mean())
            if mean_sim < min_cluster_mean_sim:
                for i in idxs:
                    labels[i] = -1

    return labels, metrics

def save_cluster_index(root: Path, face_recs: List[FaceRecord], labels: List[int]) -> None:
    # labels: 1..N и -1
    clusters: dict[str, list[np.ndarray]] = {}
    for fr, lbl in zip(face_recs, labels):
        if lbl == -1:
            continue
        clusters.setdefault(str(lbl), []).append(fr.embedding)

    out = {
        "version": 1,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "dim": int(face_recs[0].embedding.shape[0]) if face_recs else 0,
        "clusters": {},
    }

    for cid, embs in clusters.items():
        M = np.stack(embs, axis=0).mean(axis=0)
        M = M / (np.linalg.norm(M) + 1e-12)
        out["clusters"][cid] = {
            "centroid": M.astype(np.float32).tolist(),
            "n_faces": len(embs),
        }

    idx_dir = root / ".face_index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    (idx_dir / "centroids.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

def collect_images(folder: Path) -> List[Path]:
    import os
    # Список имен папок, которые нужно полностью пропускать
    SKIP_FOLDERS = {
        "общие", "shared", "public", "system", "библиотека", "library",
        "temp", "tmp", "cache", "logs", "thumbnails", "previews"
    }

    images = []
    for root, dirs, files in os.walk(folder):
        # Фильтруем папки: исключаем скрытые (.), SKIP_FOLDERS
        dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in SKIP_FOLDERS]

        for file in files:
            # Исключаем скрытые файлы
            if file.startswith('.'):
                continue

            p = Path(root) / file
            if p.suffix.lower() in IMG_EXTS:
                images.append(p)

    return images

def build_plan_from_faces(faces: List[FaceRecord], labels: List[int], confidences: Optional[List[float]]) -> List[Dict]:
    image_to_clusters: Dict[str, set[int]] = {}
    image_to_confidence: Dict[str, float] = {}

    if confidences is not None:
        # Используем предоставленные confidences
        for fr, lbl, conf in zip(faces, labels, confidences):
            image_to_clusters.setdefault(fr.image_path, set())
            # Track max confidence for image (in case multiple faces)
            if fr.image_path not in image_to_confidence:
                image_to_confidence[fr.image_path] = conf
            else:
                image_to_confidence[fr.image_path] = max(image_to_confidence[fr.image_path], conf)

            if lbl != -1:
                image_to_clusters[fr.image_path].add(int(lbl))
    else:
        # Рассчитываем confidence заново для текущих labels
        # Группируем лица по кластерам
        by_cluster = defaultdict(list)
        for i, (fr, lbl) in enumerate(zip(faces, labels)):
            if lbl != -1:
                by_cluster[lbl].append((i, fr))

        # Рассчитываем центроиды и confidence
        embeddings = np.asarray([fr.embedding for fr in faces], dtype=np.float32)
        embeddings = _l2norm_rows(embeddings)

        for lbl, face_list in by_cluster.items():
            if not face_list:
                continue
            # Центроид кластера
            idxs = [i for i, _ in face_list]
            centroid = embeddings[idxs].mean(axis=0)
            centroid = centroid / (np.linalg.norm(centroid) + 1e-12)

            # Confidence для каждого лица в кластере
            for i, fr in face_list:
                conf = float(embeddings[i] @ centroid)
                image_path = fr.image_path

                if image_path not in image_to_confidence:
                    image_to_confidence[image_path] = conf
                else:
                    image_to_confidence[image_path] = max(image_to_confidence[image_path], conf)

                image_to_clusters.setdefault(image_path, set()).add(int(lbl))

    # Все фото с лицами, даже если не попали в кластеры
    plan = []
    for img, cset in image_to_clusters.items():
        clusters = sorted(list(cset))
        confidence = image_to_confidence.get(img, 0.0)
        plan.append({"path": img, "clusters": clusters, "confidence": confidence})

    return plan

def rename_cluster_folders(root: Path) -> None:
    """Переименовывает папки кластеров, добавляя количество файлов в скобках"""
    import os

    # Находим все папки с числовыми именами (кластеры)
    cluster_folders = []
    for item in root.iterdir():
        if item.is_dir() and item.name.isdigit():
            try:
                cluster_num = int(item.name)
                # Считаем количество файлов в папке
                file_count = len([f for f in item.iterdir() if f.is_file()])
                if file_count > 0:  # Только если есть файлы
                    cluster_folders.append((cluster_num, item, file_count))
            except ValueError:
                continue

    # Сортируем по номеру кластера
    cluster_folders.sort(key=lambda x: x[0])

    # Переименовываем папки, добавляя количество файлов
    for cluster_num, folder_path, file_count in cluster_folders:
        new_name = f"{cluster_num} ({file_count})"
        new_path = folder_path.parent / new_name

        # Проверяем, не существует ли уже такая папка
        counter = 1
        while new_path.exists():
            new_name = f"{cluster_num} ({file_count})_{counter}"
            new_path = folder_path.parent / new_name
            counter += 1

        try:
            folder_path.rename(new_path)
            print(f"Renamed folder: {folder_path.name} -> {new_name}")
        except Exception as e:
            print(f"Failed to rename {folder_path.name}: {e}")

async def process_folder(
    path: Path,
    *,
    joint_mode: str,
    singletons: bool,
    progress: Callable[[int, str], None],
) -> Dict:
    # АГРЕССИВНОЕ ОБЪЕДИНЕНИЕ: для лиц с сильными изменениями (борода, очки, прическа)
    link_sim = 0.45      # Очень низкий порог для связывания лиц
    merge_sim = 0.55     # Очень низкий порог для слияния кластеров (решает проблему разбиения на 2 папки)
    assign_sim = 0.55    # Низкий порог для назначения в кластер
    min_intra_sim = 0.40 # Минимум для удержания в кластере
    assign_margin = 0.02 # Минимальный отрыв от конкурента

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
        labels0, _out_idx, confidences0 = await asyncio.to_thread(
            cluster_quality,
            embs_lists,
            link_sim=link_sim,
            merge_sim=merge_sim,
            assign_sim=assign_sim,
            min_intra_sim=min_intra_sim,
            assign_margin=assign_margin,
        )
        print(f"Clustering completed: {len(set(labels0))} clusters, {len(_out_idx)} outliers")

        # Применяем confidence gating для фильтрации сомнительных лиц/кластеров
        X = np.asarray([fr.embedding for fr in face_recs], dtype=np.float32)
        X = _l2norm_rows(X)

        labels0, cluster_metrics = apply_confidence_gating(
            X, labels0,
            keep_sim=0.48,              # порог уверенности для лица в кластере
            min_cluster_size=3,          # кластеры меньше этого размера подозрительны
            small_cluster_keep_sim=0.54, # строже для маленьких кластеров
            min_cluster_mean_sim=0.50,   # минимальная плотность кластера
        )
        print(f"After confidence gating: {len(set([l for l in labels0 if l != -1]))} clusters, {len([l for l in labels0 if l == -1])} faces in singletons")
    except Exception as e:
        print(f"Error in clustering: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Папки 1..N (после confidence gating)
    uniq = sorted(set([x for x in labels0 if x != -1]))
    remap = {old: i + 1 for i, old in enumerate(uniq)}
    labels = [(remap[x] if x != -1 else -1) for x in labels0]

    progress(70, "Индекс кластеров")
    await asyncio.to_thread(save_cluster_index, path, face_recs, labels)

    progress(75, "План раскладки")
    # После confidence gating confidences0 больше не актуальны, поэтому передаем None
    # build_plan_from_faces сама рассчитает confidence для оставшихся кластеров
    plan = build_plan_from_faces(face_recs, labels, None)

    # Фото с лицами, но без кластеров (все лица outliers) => clusters=[]
    face_paths = set(fr.image_path for fr in face_recs)
    for item in plan:
        if not item["clusters"]:  # фото с лицом, но без кластеров
            pass  # уже в плане с пустыми clusters

    # Фото без лиц => clusters=[], confidence=0
    for p in no_face_imgs:
        plan.append({"path": str(p), "clusters": [], "confidence": 0.0})

    progress(90, "Распределение по папкам")
    stats = await asyncio.to_thread(
        distribute_plan,
        plan,
        path,
        joint_mode=joint_mode,
        singletons=singletons,
    )

    # Гарантируем создание singletons для тех, кто не прошел порог строгости
    singletons_dir = path / "singletons"
    if singletons and not singletons_dir.exists():
        singletons_dir.mkdir(parents=True, exist_ok=True)

    # Переименовываем папки кластеров, добавляя количество файлов
    progress(95, "Переименование папок кластеров")
    await asyncio.to_thread(rename_cluster_folders, path)

    progress(100, "Готово")
    return {**stats, "no_faces": len(no_face_imgs), "unreadable": 0}
