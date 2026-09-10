import cv2
import numpy as np
import requests
from io import BytesIO
from PIL import Image

def download_image(url: str) -> np.ndarray:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def erase_text_and_watermarks(img: np.ndarray) -> np.ndarray:
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)
        results = reader.readtext(img)
    except Exception:
        results = []

    h, w, _ = img.shape
    mask = np.zeros((h, w), dtype=np.uint8)

    # Inpaint detected OCR text regions
    for bbox, text, conf in results:
        if conf > 0.25:
            pts = np.array(bbox, dtype=np.int32)
            cv2.fillPoly(mask, [pts], 255)

    # Inpaint default lower third watermarks / captions
    lower_crop_y = int(h * 0.72)
    cv2.rectangle(mask, (0, lower_crop_y), (w, h), 255, -1)

    # Inpaint top right corner badges
    badge_w = int(w * 0.25)
    badge_h = int(h * 0.15)
    cv2.rectangle(mask, (w - badge_w, 0), (w, badge_h), 255, -1)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask = cv2.dilate(mask, kernel, iterations=2)
    return cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)

def apply_cinematic_grade(img: np.ndarray, clahe_clip: float = 2.2) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    cl = clahe.apply(l)

    # Subtle cinematic warm push on highlights
    a = cv2.add(a, 2)
    b = cv2.add(b, 4)

    merged = cv2.merge((cl, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
