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
from core.immich_client import ImmichClient, ImmichConfig

def _l2norm_rows(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    return X / n

def merge_clusters_by_centroids(X, labels, *, merge_centroid_sim=0.62, min_cross_sim=0.56, sample_k=30):
    """Merge clusters with similar centroids (for same person split across clusters)"""
    labels = np.asarray(labels, dtype=int)
    cl_ids = sorted({int(x) for x in labels if x != -1})
    if len(cl_ids) <= 1:
        return labels.tolist()

    # собрать индексы
    idxs = {c: np.where(labels == c)[0] for c in cl_ids}

    # центроиды
    centroids = {}
    for c in cl_ids:
        C = X[idxs[c]].mean(axis=0)
        C = C / (np.linalg.norm(C) + 1e-12)
        centroids[c] = C

    # DSU
    parent = {c: c for c in cl_ids}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def union(a,b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # проверка пар
    Cmat = np.stack([centroids[c] for c in cl_ids], axis=0)
    S = Cmat @ Cmat.T  # cosine sim

    for i, ci in enumerate(cl_ids):
        for j in range(i+1, len(cl_ids)):
            cj = cl_ids[j]
            if S[i, j] < merge_centroid_sim:
                continue

            # доп. защита: проверить "перекрёстную" близость на подвыборке лиц
            ai = idxs[ci]
            aj = idxs[cj]
            si = ai[:sample_k]
            sj = aj[:sample_k]
            if len(si) == 0 or len(sj) == 0:
                continue
            cross = X[si] @ X[sj].T
            if float(np.max(cross)) >= min_cross_sim:
                union(ci, cj)

    # применить union
    rep = {c: find(c) for c in cl_ids}
    out = labels.copy()
    for c in cl_ids:
        out[labels == c] = rep[c]
    return out.tolist()

def send_ambiguous_small_clusters_to_singletons(X, labels, *, gray_low=0.56, gray_high=0.62, small_ratio=0.35):
    """Send small clusters that are similar to larger ones to singletons (ambiguous cases)"""
    labels = np.asarray(labels, dtype=int)
    cl_ids = sorted({int(x) for x in labels if x != -1})
    if len(cl_ids) <= 1:
        return labels.tolist()

    idxs = {c: np.where(labels == c)[0] for c in cl_ids}
    cents = {}
    for c in cl_ids:
        C = X[idxs[c]].mean(axis=0)
        C = C / (np.linalg.norm(C) + 1e-12)
        cents[c] = C

    Cmat = np.stack([cents[c] for c in cl_ids], axis=0)
    S = Cmat @ Cmat.T
    np.fill_diagonal(S, -1)

    for i, ci in enumerate(cl_ids):
        j = int(np.argmax(S[i]))
        sim = float(S[i, j])
        cj = cl_ids[j]

        if gray_low <= sim < gray_high:
            si = len(idxs[ci])
            sj = len(idxs[cj])
            # если кластер заметно меньше похожего соседа — это кандидат на singletons/review
            if si <= max(2, int(sj * small_ratio)):
                labels[idxs[ci]] = -1

    return labels.tolist()

def remap_labels_keep_minus1(labels):
    """Remap cluster labels while preserving -1 (singletons)"""
    labels = list(labels)
    uniq = sorted({x for x in labels if x != -1})
    mp = {old: i+1 for i, old in enumerate(uniq)}
    return [(-1 if x == -1 else mp[x]) for x in labels]

def apply_confidence_gating(
    embeddings: np.ndarray,             # (N, D) L2-normed
    labels: List[int],                  # -1 or 1..K (или 0..K-1 — неважно, главное не -1)
    *,
    keep_sim: float = 0.60,             # повышенный порог - строже
    min_cluster_size: int = 3,          # всё, что меньше — подозрительно
    small_cluster_keep_sim: float = 0.67,  # строже для маленьких кластеров
    min_cluster_mean_sim: float = 0.62,    # повышенная плотность
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

def collect_images(folder: Path, include_shared: bool = False) -> List[Path]:
    import os
    # Список имен папок, которые нужно полностью пропускать
    SKIP_FOLDERS = {
        "общие", "shared", "public", "system", "библиотека", "library",
        "temp", "tmp", "cache", "logs", "thumbnails", "previews"
    }
    
    # Если include_shared=True, исключаем "общие" и "shared" из SKIP_FOLDERS
    if include_shared:
        SKIP_FOLDERS = SKIP_FOLDERS - {"общие", "shared"}

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
    image_to_faces: Dict[str, List[Tuple[FaceRecord, int, Optional[float]]]] = {}

    # Группируем лица по изображениям
    for i, (fr, lbl) in enumerate(zip(faces, labels)):
        conf = confidences[i] if confidences else None
        image_to_faces.setdefault(fr.image_path, []).append((fr, lbl, conf))

    plan = []
    for img_path, face_data in image_to_faces.items():
        face_labels = [lbl for _, lbl, _ in face_data]

        # Правило: если фото имеет лица в разных кластерах ИЛИ есть -1 -> singletons
        unique_labels = set(face_labels)
        has_minus1 = -1 in unique_labels
        multiple_clusters = len([l for l in unique_labels if l != -1]) > 1

        if has_minus1 or multiple_clusters:
            # Фото идет в singletons для ручной проверки
            plan.append({"path": img_path, "clusters": [], "confidence": 0.0})
        else:
            # Все лица в одном кластере - нормальное распределение
            cluster = list(unique_labels)[0] if unique_labels else -1
            confidence = max([c for _, _, c in face_data if c is not None], default=1.0)
            plan.append({"path": img_path, "clusters": [cluster] if cluster != -1 else [], "confidence": confidence})

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

async def _run_local_clustering(
    images: List[Path],
    progress: Callable[[int, str], None],
) -> Tuple[List, List[int], List[Path]]:
    """Извлечение лиц + кластеризация. Возвращает (face_recs, labels, no_face_imgs)."""
    link_sim, merge_sim, assign_sim = 0.45, 0.55, 0.55
    min_intra_sim, assign_margin = 0.40, 0.02

    await asyncio.to_thread(init_engine, det_size=(1280, 1280), det_thresh=0.65)
    progress(52, "Детект лиц и эмбеддинги")
    face_recs = []
    batch_size = 5
    for i in range(0, len(images), batch_size):
        batch = images[i:i + batch_size]
        batch_faces = await asyncio.to_thread(
            extract_faces_batch, [str(p) for p in batch], min_face_px=40
        )
        face_recs.extend(batch_faces)
        pct = 52 + int(15 * (i + len(batch)) / len(images))
        progress(pct, f"Обработка лиц: {i + len(batch)}/{len(images)}")

    with_faces = set(fr.image_path for fr in face_recs)
    no_face_imgs = [p for p in images if str(p) not in with_faces]

    if len(face_recs) == 0:
        return [], [], no_face_imgs

    progress(68, "Кластеризация")
    embs = [fr.embedding for fr in face_recs]
    embs_lists = [e.tolist() if hasattr(e, 'tolist') else list(e) for e in embs]

    labels0, _, _ = await asyncio.to_thread(
        cluster_quality, embs_lists,
        link_sim=link_sim, merge_sim=merge_sim, assign_sim=assign_sim,
        min_intra_sim=min_intra_sim, assign_margin=assign_margin,
    )
    X = np.asarray([fr.embedding for fr in face_recs], dtype=np.float32)
    X = _l2norm_rows(X)
    labels0, _ = apply_confidence_gating(
        X, labels0, keep_sim=0.55, min_cluster_size=3,
        small_cluster_keep_sim=0.62, min_cluster_mean_sim=0.58,
    )
    labels0 = merge_clusters_by_centroids(X, labels0, merge_centroid_sim=0.58, min_cross_sim=0.52)
    labels0 = send_ambiguous_small_clusters_to_singletons(X, labels0, gray_low=0.52, gray_high=0.58, small_ratio=0.40)
    labels = remap_labels_keep_minus1(labels0)
    return face_recs, labels, no_face_imgs


async def process_folder_local(
    path: Path,
    *,
    joint_mode: str,
    singletons: bool,
    progress: Callable[[int, str], None],
    include_shared: bool = False,
) -> Dict:
    """Локальная кластеризация с InsightFace + scikit-learn"""
    # АГРЕССИВНОЕ ОБЪЕДИНЕНИЕ: для лиц с сильными изменениями (борода, очки, прическа)
    link_sim = 0.45      # Очень низкий порог для связывания лиц
    merge_sim = 0.55     # Очень низкий порог для слияния кластеров (решает проблему разбиения на 2 папки)
    assign_sim = 0.55    # Низкий порог для назначения в кластер
    min_intra_sim = 0.40 # Минимум для удержания в кластере
    assign_margin = 0.02 # Минимальный отрыв от конкурента

    progress(2, "Подготовка")
    progress(3, "Сканирование файлов")
    images = collect_images(path, include_shared=include_shared)
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

        labels_before_gating = labels0.copy()
        labels0, cluster_metrics = apply_confidence_gating(
            X, labels0,
            keep_sim=0.55,              # чуть мягче, чтобы сохранить лица для мерджа
            min_cluster_size=3,          # кластеры меньше этого размера подозрительны
            small_cluster_keep_sim=0.62, # чуть мягче
            min_cluster_mean_sim=0.58,   # чуть мягче
        )

        print(f"Clustering stats:")
        print(f"  - Before gating: {len(set([l for l in labels_before_gating if l != -1]))} clusters")
        print(f"  - After gating: {len(set([l for l in labels0 if l != -1]))} clusters, {len([l for l in labels0 if l == -1])} faces marked as -1")

        # ДОБАВИТЬ: Merge кластеров по центроидам (для объединения одного человека)
        labels0 = merge_clusters_by_centroids(X, labels0, merge_centroid_sim=0.58, min_cross_sim=0.52)
        print(f"  - After centroid merge: {len(set([l for l in labels0 if l != -1]))} clusters")

        # ДОБАВИТЬ: Серые случаи - маленькие похожие кластеры в singletons
        labels0 = send_ambiguous_small_clusters_to_singletons(X, labels0, gray_low=0.52, gray_high=0.58, small_ratio=0.40)
        print(f"  - After ambiguous filtering: {len(set([l for l in labels0 if l != -1]))} clusters, {len([l for l in labels0 if l == -1])} total faces in singletons")
    except Exception as e:
        print(f"Error in clustering: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Папки 1..N (после всех стадий обработки) - сохраняем -1
    labels = remap_labels_keep_minus1(labels0)

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


async def process_folder_immich(
    path: Path,
    *,
    joint_mode: str,
    singletons: bool,
    progress: Callable[[int, str], None],
    include_shared: bool = False,
    immich_url: str = "",
    immich_api_key: str = "",
) -> Dict:
    """Immich: загрузка в библиотеку + локальная кластеризация (InsightFace) для качества"""
    progress(2, "Подготовка")
    progress(3, "Сканирование файлов")
    images = collect_images(path, include_shared=include_shared)
    if not images:
        progress(100, "Нет изображений")
        return {"moved": 0, "copied": 0, "clusters": 0, "no_faces": 0, "unreadable": 0}
    
    config = ImmichConfig(url=immich_url, api_key=immich_api_key)
    client = ImmichClient(config)
    
    try:
        if not await client.test_connection():
            raise Exception("Не удалось подключиться к Immich серверу")
        
        # 1. Загрузка в Immich + ожидание детекта лиц
        progress(10, "Загрузка в Immich")
        uploaded_paths = await client.upload_and_wait_for_faces(images, progress_callback=progress)
        uploaded_set = {str(p) for p in uploaded_paths}
        failed_upload = [p for p in images if str(p) not in uploaded_set]

        # 2. Локальная кластеризация (InsightFace) — качество как в local mode
        progress(50, "Локальная кластеризация (InsightFace)")
        face_recs, labels, no_face_imgs = await _run_local_clustering(uploaded_paths, progress)
        no_face_imgs = no_face_imgs + failed_upload

        if len(face_recs) == 0:
            progress(100, "Лиц не найдено")
            return {"moved": 0, "copied": 0, "clusters": 0, "no_faces": len(images), "unreadable": 0}
        
        # Сохраняем индекс кластеров
        progress(70, "Индекс кластеров")
        await asyncio.to_thread(save_cluster_index, path, face_recs, labels)
        
        # Создаем план распределения
        progress(75, "План раскладки")
        plan = build_plan_from_faces(face_recs, labels, None)
        
        # Фото без лиц
        for p in no_face_imgs:
            plan.append({"path": str(p), "clusters": [], "confidence": 0.0})
        
        # Распределение по папкам
        progress(90, "Распределение по папкам")
        stats = await asyncio.to_thread(
            distribute_plan,
            plan,
            path,
            joint_mode=joint_mode,
            singletons=singletons,
        )
        
        # Гарантируем создание singletons
        singletons_dir = path / "singletons"
        if singletons and not singletons_dir.exists():
            singletons_dir.mkdir(parents=True, exist_ok=True)
        
        # Переименовываем папки
        progress(95, "Переименование папок кластеров")
        await asyncio.to_thread(rename_cluster_folders, path)
        
        progress(100, "Готово")
        return {**stats, "no_faces": len(no_face_imgs), "unreadable": 0}
    
    finally:
        await client.close()


async def process_folder(
    path: Path,
    *,
    joint_mode: str,
    singletons: bool,
    progress: Callable[[int, str], None],
    include_shared: bool = False,
    clustering_engine: str = "local",
    immich_url: Optional[str] = None,
    immich_api_key: Optional[str] = None,
) -> Dict:
    """
    Главная функция обработки папки с поддержкой выбора движка кластеризации
    
    Args:
        clustering_engine: "local" или "immich"
        immich_url: URL Immich сервера (требуется для immich режима)
        immich_api_key: API ключ Immich (требуется для immich режима)
    """
    if clustering_engine == "immich":
        if not immich_url or not immich_api_key:
            raise ValueError("Для Immich режима требуются immich_url и immich_api_key")
        return await process_folder_immich(
            path,
            joint_mode=joint_mode,
            singletons=singletons,
            progress=progress,
            include_shared=include_shared,
            immich_url=immich_url,
            immich_api_key=immich_api_key,
        )
    else:
        return await process_folder_local(
            path,
            joint_mode=joint_mode,
            singletons=singletons,
            progress=progress,
            include_shared=include_shared,
        )
