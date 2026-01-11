from collections import defaultdict

def build_plan(image_faces: list[dict], labels: list[int]):
    cluster_map = defaultdict(list)
    for img, faces in zip(image_faces, labels):
        img_path = img["path"]
        if isinstance(faces, list):
            cluster_map[img_path] = [l for l in faces if l != -1]
        else:
            cluster_map[img_path] = [faces] if faces != -1 else []
    return [{"path": path, "clusters": clist} for path, clist in cluster_map.items()]
