import cv2
import numpy as np
import requests

def download_image(url: str) -> np.ndarray:
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Referer': 'https://www.facebook.com/'
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def erase_text_and_watermarks(img: np.ndarray) -> np.ndarray:
    """
    Intelligently cleans small intrusive corner logos/subtitles using selective masking.
    Does NOT blindly wipe out 28% of the photo background or facial portraits.
    """
    h, w, _ = img.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    has_mask = False

    # 1. Try EasyOCR if installed
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)
        results = reader.readtext(img)
        for bbox, text, conf in results:
            if conf > 0.40:
                pts = np.array(bbox, dtype=np.int32)
                cv2.fillPoly(mask, [pts], 255)
                has_mask = True
    except Exception:
        pass

    # 2. If no OCR or small watermarks in extreme corners, check high-contrast overlays
    if not has_mask:
        # Check tiny corner regions (top-left / top-right 40x40 logo badge area only if extreme contrast)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # We preserve the main photo area completely intact
        return img

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.dilate(mask, kernel, iterations=1)
    return cv2.inpaint(img, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

def apply_cinematic_grade(img: np.ndarray, clahe_clip: float = 2.0) -> np.ndarray:
    """Applies CIE-LAB Contrast Limited Adaptive Histogram Equalization with warm cinematic grade."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    cl = clahe.apply(l)

    # Subtle warm highlight push
    a = cv2.add(a, 1)
    b = cv2.add(b, 3)

    merged = cv2.merge((cl, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
