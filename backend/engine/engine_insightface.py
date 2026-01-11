import numpy as np
import cv2
from insightface.app import FaceAnalysis

app = None

def init_engine():
    global app
    if app is None:
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))

def extract_embeddings(image_path: str):
    import PIL.Image
    img = np.array(PIL.Image.open(image_path).convert("RGB"))
    faces = app.get(img)
    result = []
    for face in faces:
        result.append({
            "embedding": face.embedding.tolist(),
            "bbox": face.bbox.tolist(),
        })
    return result
