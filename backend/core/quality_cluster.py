# backend/core/quality_cluster.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np

def _l2norm_rows(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return X / n

class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.r = [0] * n
    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1

def cluster_quality(
    embeddings: List[np.ndarray],
    *,
    link_sim: float = 0.45,
    merge_sim: float = 0.55,
    assign_sim: float = 0.55,
    min_intra_sim: float = 0.40,
    assign_margin: float = 0.02,
) -> Tuple[List[int], List[int], List[float]]:
    n = len(embeddings)
    if n == 0:
        return [], [], []
    if n == 1:
        return [0], [], [1.0]

    # Convert to numpy array if needed
    X = _l2norm_rows(np.asarray(embeddings, dtype=np.float32))
    dist_thr = float(1.0 - link_sim)

    # 1) Agglomerative (cosine)
    try:
        from sklearn.cluster import AgglomerativeClustering
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=dist_thr,
            metric="cosine",
            linkage="average",
        )
        base = model.fit_predict(X).astype(int)
    except Exception:
        # fallback для старого sklearn API
        from sklearn.cluster import AgglomerativeClustering
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=dist_thr,
            affinity="cosine",
            linkage="average",
        )
        base = model.fit_predict(X).astype(int)

    uniq = sorted(set(int(x) for x in base.tolist()))
    remap = {k: i for i, k in enumerate(uniq)}
    labels = np.array([remap[int(x)] for x in base], dtype=int)

    def centroids(lbls: np.ndarray) -> Dict[int, np.ndarray]:
        c: Dict[int, np.ndarray] = {}
        for k in sorted(set(lbls.tolist())):
            idx = np.where(lbls == k)[0]
            v = X[idx].mean(axis=0)
            v = v / (np.linalg.norm(v) + 1e-12)
            c[k] = v
        return c

    # 2) Очистка кластера: выбрасываем точки с низкой похожестью к центроиду
    out = set()
    cents = centroids(labels)
    for k, cent in cents.items():
        idx = np.where(labels == k)[0]
        sims = X[idx] @ cent
        for ii, s in zip(idx.tolist(), sims.tolist()):
            if float(s) < min_intra_sim:
                out.add(ii)

    cleaned = labels.copy()
    for i in out:
        cleaned[i] = -1

    kept = [k for k in sorted(set(cleaned.tolist())) if k != -1]
    if not kept:
        return [-1] * n, sorted(list(out))

    # переиндексация после очистки
    old_to_new = {k: i for i, k in enumerate(kept)}
    tmp = np.array([old_to_new.get(int(x), -1) for x in cleaned], dtype=int)
    K = len(kept)

    # 3) Merge кластеров по похожести центроидов
    cents2 = {}
    for k in range(K):
        idx = np.where(tmp == k)[0]
        v = X[idx].mean(axis=0)
        v = v / (np.linalg.norm(v) + 1e-12)
        cents2[k] = v
    C = np.stack([cents2[k] for k in range(K)], axis=0)
    S = C @ C.T

    uf = UnionFind(K)
    for i in range(K):
        for j in range(i + 1, K):
            if float(S[i, j]) >= merge_sim:
                uf.union(i, j)

    roots = sorted(set(uf.find(i) for i in range(K)))
    root_to_id = {r: idx for idx, r in enumerate(roots)}
    merged_map = {i: root_to_id[uf.find(i)] for i in range(K)}

    merged = tmp.copy()
    for i in range(n):
        if merged[i] != -1:
            merged[i] = merged_map[int(merged[i])]

    # 4) Reassignment outliers к ближайшему центроиду, если уверенно
    K2 = len(set([x for x in merged.tolist() if x != -1]))
    cents3 = {}
    for k in range(K2):
        idx = np.where(merged == k)[0]
        v = X[idx].mean(axis=0)
        v = v / (np.linalg.norm(v) + 1e-12)
        cents3[k] = v
    C3 = np.stack([cents3[k] for k in range(K2)], axis=0)

    final = merged.copy()
    final_out = set()
    confidences = np.zeros(n, dtype=np.float32)  # confidence scores for each face
    
    # Calculate confidence for faces already in clusters
    for i in range(n):
        if final[i] != -1:
            # Face already in cluster - calculate similarity to centroid
            k = int(final[i])
            confidences[i] = float(C3[k] @ X[i])
    
    # Reassign outliers and calculate their confidence
    for i in range(n):
        if final[i] != -1:
            continue
        sims = C3 @ X[i]
        best_k = int(np.argmax(sims))
        best_s = float(sims[best_k])

        # NEW: second best for margin constraint
        if sims.shape[0] > 1:
            tmp_sims = sims.copy()
            tmp_sims[best_k] = -1.0
            second_s = float(np.max(tmp_sims))
        else:
            second_s = -1.0

        if best_s >= assign_sim and (best_s - second_s) >= assign_margin:
            final[i] = best_k
            confidences[i] = best_s
        else:
            final_out.add(i)
            confidences[i] = best_s  # still store confidence even if rejected

    return final.tolist(), sorted(list(final_out)), confidences.tolist()
