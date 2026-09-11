import cv2
import numpy as np
import requests

def download_image(url: str) -> np.ndarray:
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Referer': 'https://www.facebook.com/'
    }
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def detect_and_remove_watermarks(img: np.ndarray) -> np.ndarray:
    """
    Intelligently inspects image for watermarks, channel logos, text stamps,
    and semi-transparent overlays, and seamlessly inpaints them using Telea algorithm.
    """
    if img is None:
        return None

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = np.zeros((h, w), dtype=np.uint8)

    # 1. Gradient edge detection for high-frequency text / watermark strokes
    grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
    abs_grad_x = cv2.convertScaleAbs(grad_x)
    abs_grad_y = cv2.convertScaleAbs(grad_y)
    grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

    # Otsu thresholding for edge regions
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Morphological horizontal closing to group letters into words
    kernel_text = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_text)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    watermark_detected = False

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / float(ch + 1e-5)
        area = cw * ch

        # Watermark heuristics: aspect ratio > 1.2, height between 8 and 70px, area < 4% of total
        if 1.2 <= aspect <= 15.0 and 8 <= ch <= 70 and 80 <= area <= (h * w * 0.04):
            # Check edge density inside region
            roi_grad = grad[y:y+ch, x:x+cw]
            density = np.count_nonzero(roi_grad > 40) / float(area + 1e-5)

            # Target corner logos, watermark stamps, and semi-transparent badges
            is_corner = (x < w * 0.35 or x > w * 0.65) or (y < h * 0.35 or y > h * 0.65)
            if density > 0.22 and (is_corner or aspect > 2.5):
                cv2.rectangle(mask, (max(0, x - 2), max(0, y - 2)), (min(w, x + cw + 2), min(h, y + ch + 2)), 255, -1)
                watermark_detected = True

    if watermark_detected and np.count_nonzero(mask) > 0:
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated_mask = cv2.dilate(mask, kernel_dilate, iterations=1)
        cleaned = cv2.inpaint(img, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        return cleaned

    return img

def erase_text_and_watermarks(img: np.ndarray) -> np.ndarray:
    return detect_and_remove_watermarks(img)

def apply_cinematic_grade(img: np.ndarray) -> np.ndarray:
    if img is None:
        return None
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    merged = cv2.merge((cl, a, b))
    graded = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    graded = cv2.convertScaleAbs(graded, alpha=1.05, beta=2)
    return graded
