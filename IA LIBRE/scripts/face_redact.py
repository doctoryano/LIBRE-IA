#!/usr/bin/env python3
"""
scripts/face_redact.py

Face detection + redaction utilities.

Funciones públicas:
- detect_faces(image_bytes: bytes, conf_thresh: float = 0.35) -> List[(x1,y1,x2,y2,conf)]
- redact_faces(image_bytes: bytes, method='blur', conf_thresh=0.5) -> (redacted_bytes, rects_list)

Notas:
- Trabaja en memoria, no guarda archivos (privacidad).
- Usa OpenCV DNN res10 SSD si los pesos/prototxt están presentes en data/models/face_detector/,
  y cae a Haar cascade si no están.
- Métodos de redacción: blur, pixelate, blackbox
"""
from __future__ import annotations
import io
import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parent.parent
DETECTOR_DIR = ROOT / "data" / "models" / "face_detector"
DETECTOR_DIR.mkdir(parents=True, exist_ok=True)

# Default filenames (operator should populate these via fetch script)
DNN_PROTO = DETECTOR_DIR / "deploy.prototxt"
DNN_MODEL = DETECTOR_DIR / "res10_300x300_ssd_iter_140000_fp16.caffemodel"

HAAR_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

def _load_dnn_net():
    if DNN_PROTO.exists() and DNN_MODEL.exists():
        try:
            net = cv2.dnn.readNetFromCaffe(str(DNN_PROTO), str(DNN_MODEL))
            return net
        except Exception:
            return None
    return None

def _detect_faces_dnn(net, image, conf_thresh=0.35):
    h, w = image.shape[:2]
    blob = cv2.dnn.blobFromImage(cv2.resize(image, (300, 300)), 1.0,
                                 (300, 300), (104.0, 177.0, 123.0))
    net.setInput(blob)
    detections = net.forward()
    rects = []
    for i in range(detections.shape[2]):
        conf = float(detections[0, 0, i, 2])
        if conf > conf_thresh:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)
            rects.append((int(x1), int(y1), int(x2), int(y2), float(conf)))
    return rects

def _detect_faces_haar(image, conf_thresh=0.35):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(HAAR_PATH)
    rects_raw = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    rects = []
    for (x, y, w, h) in rects_raw:
        rects.append((int(x), int(y), int(x + w), int(y + h), 1.0))
    return rects

def detect_faces(image_bytes: bytes, conf_thresh: float = 0.35) -> List[Tuple[int,int,int,int,float]]:
    """
    Detect faces and return list of rectangles (x1,y1,x2,y2,confidence).
    Does not modify image; does not persist files.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image bytes")
    net = _load_dnn_net()
    if net is not None:
        return _detect_faces_dnn(net, img, conf_thresh=conf_thresh)
    else:
        return _detect_faces_haar(img, conf_thresh=conf_thresh)

def _pixelate_region(img, x1, y1, x2, y2, blocks=12):
    region = img[y1:y2, x1:x2]
    if region.size == 0:
        return img
    h, w = region.shape[:2]
    small = cv2.resize(region, (max(1, blocks), max(1, blocks)), interpolation=cv2.INTER_LINEAR)
    pixelated = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    img[y1:y2, x1:x2] = pixelated
    return img

def _blur_region(img, x1, y1, x2, y2, ksize=35):
    region = img[y1:y2, x1:x2]
    if region.size == 0:
        return img
    k = ksize if ksize % 2 == 1 else ksize + 1
    blurred = cv2.GaussianBlur(region, (k, k), 0)
    img[y1:y2, x1:x2] = blurred
    return img

def _blackbox_region(img, x1, y1, x2, y2, color=(0, 0, 0)):
    img[y1:y2, x1:x2] = color
    return img

def redact_faces(image_bytes: bytes, method: str = "blur", conf_thresh: float = 0.35) -> (bytes, List[Tuple[int,int,int,int,float]]):
    """
    Redacts faces and returns (redacted_image_bytes, rects_list).
    rects_list: [(x1,y1,x2,y2,conf), ...]
    method: 'blur' | 'pixelate' | 'blackbox'
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid image bytes")

    net = _load_dnn_net()
    if net is not None:
        rects = _detect_faces_dnn(net, img, conf_thresh=conf_thresh)
    else:
        rects = _detect_faces_haar(img, conf_thresh=conf_thresh)

    # If no faces detected, return original encoded JPEG
    if not rects:
        _, outbuf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        return outbuf.tobytes(), []

    # Apply redaction
    for (x1, y1, x2, y2, conf) in rects:
        pad_x = int((x2 - x1) * 0.12)
        pad_y = int((y2 - y1) * 0.12)
        x1e = max(0, x1 - pad_x); y1e = max(0, y1 - pad_y)
        x2e = min(img.shape[1] - 1, x2 + pad_x); y2e = min(img.shape[0] - 1, y2 + pad_y)
        if method == "pixelate":
            img = _pixelate_region(img, x1e, y1e, x2e, y2e, blocks=12)
        elif method == "blackbox":
            img = _blackbox_region(img, x1e, y1e, x2e, y2e, color=(0, 0, 0))
        else:
            img = _blur_region(img, x1e, y1e, x2e, y2e, ksize=35)

    _, outbuf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return outbuf.tobytes(), rects