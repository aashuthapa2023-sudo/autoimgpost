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
    and semi-transparent overlays, while strictly preserving human faces using
    Haar cascade detection, and seamlessly inpaints watermarks using Telea algorithm.
    """
    if img is None:
        return None

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Face detection mask to strictly prevent inpainting over human faces
    face_mask = np.zeros((h, w), dtype=np.uint8)
    try:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(50, 50))
        for (fx, fy, fw, fh) in faces:
            # Expand face bounds by 25% for hair, forehead, and neck protection
            pad_x = int(fw * 0.25)
            pad_y = int(fh * 0.25)
            x1 = max(0, fx - pad_x)
            y1 = max(0, fy - pad_y)
            x2 = min(w, fx + fw + pad_x)
            y2 = min(h, fy + fh + pad_y)
            cv2.rectangle(face_mask, (x1, y1), (x2, y2), 255, -1)
    except Exception:
        pass

    # 2. Gradient edge detection for high-frequency text / watermark strokes
    mask = np.zeros((h, w), dtype=np.uint8)
    grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
    abs_grad_x = cv2.convertScaleAbs(grad_x)
    abs_grad_y = cv2.convertScaleAbs(grad_y)
    grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

    # Otsu thresholding for edge regions
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Morphological horizontal closing to group letters into words
    kernel_text = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_text)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    watermark_detected = False

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / float(ch + 1e-5)
        area = cw * ch

        # Strictly ignore any region that overlaps with human faces
        if np.any(face_mask[y:y+ch, x:x+cw] > 0):
            continue

        # Watermark / overlay text criteria: perimeter regions (within 22% of edges) or small badge stamps
        is_edge_or_banner = (x < w * 0.22 or x + cw > w * 0.78 or y < h * 0.22 or y + ch > h * 0.60)
        if is_edge_or_banner and 1.1 <= aspect <= 18.0 and 8 <= ch <= 80 and area <= (h * w * 0.04):
            roi_grad = grad[y:y+ch, x:x+cw]
            density = np.count_nonzero(roi_grad > 38) / float(area + 1e-5)
            if density > 0.20:
                cv2.rectangle(mask, (max(0, x - 3), max(0, y - 3)), (min(w, x + cw + 3), min(h, y + ch + 3)), 255, -1)
                watermark_detected = True

    # 3. Detect high-contrast colored badges (e.g. Red 'NEWS', yellow badges) outside faces
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask_r1 = cv2.inRange(hsv, np.array([0, 110, 90]), np.array([12, 255, 255]))
        mask_r2 = cv2.inRange(hsv, np.array([168, 110, 90]), np.array([180, 255, 255]))
        mask_colored = cv2.bitwise_or(mask_r1, mask_r2)
        cnts_badge, _ = cv2.findContours(mask_colored, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for bcnt in cnts_badge:
            bx, by, bw, bh = cv2.boundingRect(bcnt)
            b_area = bw * bh
            if not np.any(face_mask[by:by+bh, bx:bx+bw] > 0) and 25 <= bw <= 350 and 12 <= bh <= 100 and b_area < (h * w * 0.03):
                cv2.rectangle(mask, (max(0, bx - 3), max(0, by - 3)), (min(w, bx + bw + 3), min(h, by + bh + 3)), 255, -1)
                watermark_detected = True
    except Exception:
        pass

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
