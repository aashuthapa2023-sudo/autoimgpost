import cv2
import numpy as np
import requests
import urllib.parse

def download_image(url: str) -> np.ndarray:
    desktop_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://www.facebook.com/'
    }
    crawler_headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Referer': 'https://www.facebook.com/'
    }

    # Use crawler headers for lookaside to get direct 2048px master uncompressed image
    is_lookaside = "lookaside.fbsbx.com" in url

    # 1. If Facebook proxy URL, extract original full-resolution asset URL
    orig_url = None
    if "fbcdn.net" in url and "url=" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            orig_candidate = qs.get("url", [None])[0]
            if orig_candidate and orig_candidate.startswith("http"):
                orig_url = orig_candidate
        except Exception:
            pass

    # Download original uncompressed full-res image first
    if orig_url:
        try:
            resp_orig = requests.get(orig_url, headers=desktop_headers, timeout=18)
            if resp_orig.status_code == 200 and 'text/html' not in resp_orig.headers.get('Content-Type', ''):
                arr = np.asarray(bytearray(resp_orig.content), dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] >= 300 and img.shape[1] >= 400:
                    return img
        except Exception:
            pass

    # 2. Direct provided URL (use crawler headers for lookaside, desktop for others)
    target_headers = crawler_headers if is_lookaside else desktop_headers
    try:
        resp = requests.get(url, headers=target_headers, timeout=25)
        resp.raise_for_status()
        c_type = resp.headers.get('Content-Type', '')
        if 'text/html' in c_type:
            # If desktop header got redirected, retry with crawler header
            if not is_lookaside:
                resp_retry = requests.get(url, headers=crawler_headers, timeout=20)
                if resp_retry.status_code == 200 and 'text/html' not in resp_retry.headers.get('Content-Type', ''):
                    arr = np.asarray(bytearray(resp_retry.content), dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None and img.shape[0] >= 50 and img.shape[1] >= 50:
                        return img
            return None
        arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None and (img.shape[0] < 50 or img.shape[1] < 50):
            return None
        return img
    except Exception:
        return None

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

    # 1. Face & Skin detection masks to strictly prevent inpainting over human subjects
    face_mask = np.zeros((h, w), dtype=np.uint8)
    try:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(40, 40))
        for (fx, fy, fw, fh) in faces:
            # Expand face bounds by 35% for hair, forehead, and neck protection
            pad_x = int(fw * 0.35)
            pad_y = int(fh * 0.35)
            x1 = max(0, fx - pad_x)
            y1 = max(0, fy - pad_y)
            x2 = min(w, fx + fw + pad_x)
            y2 = min(h, fy + fh + pad_y)
            cv2.rectangle(face_mask, (x1, y1), (x2, y2), 255, -1)
    except Exception:
        pass

    # Human skin detection in HSV to protect faces, necks, arms, and subject bodies
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    skin_mask = cv2.inRange(hsv, np.array([0, 20, 50]), np.array([25, 255, 255]))
    kernel_skin = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    skin_mask = cv2.dilate(skin_mask, kernel_skin, iterations=2)

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

    # STRICT RULE: Only check strictly below the vertical center of the image
    y_center = int(h * 0.50)

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / float(ch + 1e-5)
        area = cw * ch

        # Strictly ignore any region above center of image (y < y_center)
        if y < y_center:
            continue

        # Strictly protect human subjects: NEVER touch faces or skin tones
        if np.any(face_mask[y:y+ch, x:x+cw] > 0):
            continue
        skin_overlap = np.count_nonzero(skin_mask[y:y+ch, x:x+cw] > 0) / float(area + 1e-5)
        if skin_overlap > 0.06:
            continue

        # Watermark / overlay text criteria strictly in lower half
        is_edge_or_banner = (x < w * 0.20 or x + cw > w * 0.80 or y + ch > h * 0.65)
        if is_edge_or_banner and 1.2 <= aspect <= 18.0 and 8 <= ch <= 75 and area <= (h * w * 0.035):
            roi_grad = grad[y:y+ch, x:x+cw]
            density = np.count_nonzero(roi_grad > 38) / float(area + 1e-5)
            if density > 0.22:
                cv2.rectangle(mask, (max(0, x - 2), max(0, y - 2)), (min(w, x + cw + 2), min(h, y + ch + 2)), 255, -1)
                watermark_detected = True

    # 3. Detect high-contrast colored badges (strictly below the center of the image)
    try:
        mask_r1 = cv2.inRange(hsv, np.array([0, 110, 90]), np.array([12, 255, 255]))
        mask_r2 = cv2.inRange(hsv, np.array([168, 110, 90]), np.array([180, 255, 255]))
        mask_colored = cv2.bitwise_or(mask_r1, mask_r2)
        cnts_badge, _ = cv2.findContours(mask_colored, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for bcnt in cnts_badge:
            bx, by, bw, bh = cv2.boundingRect(bcnt)
            if by < y_center:
                continue
            b_area = bw * bh
            if not np.any(face_mask[by:by+bh, bx:bx+bw] > 0) and np.count_nonzero(skin_mask[by:by+bh, bx:bx+bw] > 0) < (b_area * 0.06) and 25 <= bw <= 350 and 12 <= bh <= 100 and b_area < (h * w * 0.03):
                cv2.rectangle(mask, (max(0, bx - 2), max(0, by - 2)), (min(w, bx + bw + 2), min(h, by + bh + 2)), 255, -1)
                watermark_detected = True
    except Exception:
        pass

    # 4. Detect and inpaint top-left corner ND / NF logos (Netflix Daily / Netflix Fanatics)
    # Strictly isolated to top-left corner: x < 0.16 * w and y < 0.13 * h
    try:
        corner_h = int(h * 0.13)
        corner_w = int(w * 0.16)
        roi_corner = img[0:corner_h, 0:corner_w]
        cb, cg, cr = cv2.split(roi_corner)
        c_diff = cr.astype(np.int16) - np.maximum(cg, cb).astype(np.int16)
        # Saturated red logo pixels
        c_logo_pixels = ((cr > 125) & (c_diff > 65)).astype(np.uint8) * 255
        cnts_logo, _ = cv2.findContours(c_logo_pixels, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for lcnt in cnts_logo:
            lx, ly, lw, lh = cv2.boundingRect(lcnt)
            l_area = lw * lh
            if 8 <= lw <= 95 and 8 <= lh <= 90 and l_area >= 50:
                cv2.rectangle(mask, (max(0, lx - 3), max(0, ly - 3)), (min(corner_w, lx + lw + 3), min(corner_h, ly + lh + 3)), 255, -1)
                watermark_detected = True
    except Exception:
        pass

    if watermark_detected and np.count_nonzero(mask) > 0:
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated_mask = cv2.dilate(mask, kernel_dilate, iterations=1)
        cleaned = cv2.inpaint(img, dilated_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        return cleaned

    return img

def compute_image_dhash(img: np.ndarray, hash_size: int = 8) -> str:
    """Computes a 64-bit difference hash (dHash) as a 16-char hex string for visual deduplication."""
    if img is None:
        return ""
    try:
        resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        diff = gray[:, 1:] > gray[:, :-1]
        val = sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])
        return f"{val:016x}"
    except Exception:
        return ""

def clean_lower_half_text_and_badges(img: np.ndarray) -> np.ndarray:
    """
    Detects lower-half source badges (e.g. 'NEWS', 'EXCLUSIVE', 'REPORT') and wipes out
    all residual source headline text below the badge or in the lower 38% dark region to solid black.
    Strictly preserves human subjects, faces, and top-half artwork.
    """
    if img is None:
        return None
    h, w = img.shape[:2]
    out = img.copy()

    # 1. Search for top-most lower-half badge (NEWS / EXCLUSIVE / UPDATE pills)
    y_half = int(h * 0.50)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Red, Orange, Yellow, Crimson saturated badge detection
    mask_r1 = cv2.inRange(hsv, np.array([0, 110, 90]), np.array([25, 255, 255]))
    mask_r2 = cv2.inRange(hsv, np.array([165, 110, 90]), np.array([180, 255, 255]))
    badge_mask = cv2.bitwise_or(mask_r1, mask_r2)
    badge_mask[:y_half, :] = 0

    cnts, _ = cv2.findContours(badge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=lambda c: cv2.boundingRect(c)[1])
    found_badge_bottom = None

    for c in cnts:
        bx, by, bw, bh = cv2.boundingRect(c)
        if by >= y_half and 50 <= bw <= int(w * 0.45) and 18 <= bh <= int(h * 0.12):
            center_x = bx + bw / 2.0
            # Centered or near-centered banner
            if abs(center_x - (w / 2.0)) < (w * 0.35):
                found_badge_bottom = by + bh + 4
                break

    if found_badge_bottom:
        # All text below the source badge is wiped completely to pure black
        out[found_badge_bottom:, :] = 0
        return out

    # 2. If no prominent badge, detect if lower 38% is a dark banner with text edges
    lower_start_y = int(h * 0.62)
    roi = img[lower_start_y:, :]
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    dark_ratio = np.count_nonzero(gray_roi < 45) / float(gray_roi.size)
    edges = cv2.Canny(gray_roi, 50, 150)
    edge_ratio = np.count_nonzero(edges > 0) / float(edges.size)

    if dark_ratio > 0.55 and edge_ratio > 0.035:
        out[lower_start_y:, :] = 0

    return out

def erase_text_and_watermarks(img: np.ndarray) -> np.ndarray:
    cleaned = detect_and_remove_watermarks(img)
    cleaned = clean_lower_half_text_and_badges(cleaned)
    return cleaned

def validate_image_quality(img: np.ndarray, min_dim: int = 720, min_sharpness: float = 160.0) -> tuple:
    """
    Validates image resolution and clarity to strictly eliminate blurry or pixelated images:
    - Verifies dimensions are at least min_dim x min_dim (or sufficient HD area >= 518,400 px)
    - Verifies sharpness variance using Laplacian operator >= min_sharpness
    - Verifies color / contrast standard deviation >= 22 (rejects blank, washed out, or corrupted images)
    """
    if img is None:
        return False, "Image is None or corrupt"

    h, w = img.shape[:2]
    total_pixels = h * w
    # Strict resolution gate: short dimension >= 640px and total pixels >= 518,400 (e.g. 720x720)
    if min(w, h) < 640 or total_pixels < 518400:
        return False, f"Low resolution: {w}x{h}px ({total_pixels:,} pixels; minimum required is 640px short-edge & 518,400px area)"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if lap_var < min_sharpness:
        return False, f"Blurry image detected: Sharpness variance {lap_var:.1f} is below minimum threshold of {min_sharpness:.1f}"

    # Check contrast / std deviation
    std_dev = float(np.std(gray))
    if std_dev < 22.0:
        return False, f"Insufficient contrast / washed out: std dev {std_dev:.1f} < 22.0"

    return True, f"Passed HD quality check (Resolution: {w}x{h}px, Sharpness: {lap_var:.1f})"

def apply_cinematic_grade(img: np.ndarray) -> np.ndarray:
    if img is None:
        return None
    # 1. Edge-preserving bilateral denoising to remove JPEG compression blocks & pixelation noise
    smoothed = cv2.bilateralFilter(img, d=5, sigmaColor=25, sigmaSpace=25)

    # 2. CIE-LAB Dynamic Contrast CLAHE
    lab = cv2.cvtColor(smoothed, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.7, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    merged = cv2.merge((cl, a, b))
    graded = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    graded = cv2.convertScaleAbs(graded, alpha=1.02, beta=1)

    # 3. Micro-texture preservation: unsharp mask to ensure edges stay crisp
    gaussian = cv2.GaussianBlur(graded, (0, 0), sigmaX=1.5)
    graded = cv2.addWeighted(graded, 1.15, gaussian, -0.15, 0)
    return graded
