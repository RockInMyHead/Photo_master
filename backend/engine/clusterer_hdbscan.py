import numpy as np
import hdbscan
from sklearn.preprocessing import normalize

def cluster_embeddings(embeddings: list[np.ndarray], min_cluster_size=2):
    if not embeddings:
        return []
    X = normalize(np.stack(embeddings))
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric='euclidean')
    labels = clusterer.fit_predict(X)
    return labels.tolist()
