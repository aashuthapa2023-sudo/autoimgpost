import os
import re
import cv2
import numpy as np
import hashlib
import random
import math
from PIL import Image, ImageDraw, ImageFont

CURATED_HIGHLIGHT_PALETTE = [
    {"name": "Dark Yellow", "hex": "#FFC83B"}, # Warm cinematic gold / dark yellow
    {"name": "Light Blue",  "hex": "#38BDF8"}, # Electric sky / neon light blue
    {"name": "Vivid Red",   "hex": "#FF3B30"}, # Bold crimson / ruby red
    {"name": "Electric Cyan","hex": "#00E5FF"}, # Bright vibrant aqua cyan
    {"name": "Amber Gold",  "hex": "#F59E0B"}, # Deep sunny amber
    {"name": "Mint Emerald","hex": "#10B981"}, # Vivid neon emerald green
    {"name": "Sunset Coral","hex": "#FF6B6B"}, # Punchy warm coral red
    {"name": "Hot Magenta", "hex": "#F43F5E"}  # Electric neon rose
]

def pick_highlight_color(seed: str = None) -> str:
    """Returns a randomized vibrant, high-contrast highlight color."""
    if seed:
        idx = int(hashlib.md5(str(seed).encode("utf-8")).hexdigest(), 16) % len(CURATED_HIGHLIGHT_PALETTE)
        return CURATED_HIGHLIGHT_PALETTE[idx]["hex"]
    return random.choice(CURATED_HIGHLIGHT_PALETTE)["hex"]

def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c*2 for c in hex_str])
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    font_candidates = [
        os.path.join(repo_root, "assets", "fonts", "Akshar-Bold.ttf"),
        os.path.join(repo_root, "assets", "fonts", "impact.ttf"),
        os.path.join(repo_root, "assets", "fonts", "bold_headline.ttf"),
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\Nirmala.ttc",
        r"C:\Windows\Fonts\ariblk.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    class SIZE(ctypes.Structure):
        _fields_ = [('cx', wintypes.LONG), ('cy', wintypes.LONG)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', wintypes.DWORD),
            ('biWidth', wintypes.LONG),
            ('biHeight', wintypes.LONG),
            ('biPlanes', wintypes.WORD),
            ('biBitCount', wintypes.WORD),
            ('biCompression', wintypes.DWORD),
            ('biSizeImage', wintypes.DWORD),
            ('biXPelsPerMeter', wintypes.LONG),
            ('biYPelsPerMeter', wintypes.LONG),
            ('biClrUsed', wintypes.DWORD),
            ('biClrImportant', wintypes.DWORD)
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]

    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
    user32.DrawTextW.restype = ctypes.c_int

    gdi32.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)]
    gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL

AKSHAR_REGISTERED = False

def ensure_akshar_font():
    global AKSHAR_REGISTERED
    if not AKSHAR_REGISTERED and os.name == 'nt':
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        akshar_path = os.path.join(repo_root, "assets", "fonts", "Akshar-Bold.ttf")
        if os.path.exists(akshar_path):
            try:
                gdi32.AddFontResourceExW(os.path.abspath(akshar_path), 0x10, 0)
                AKSHAR_REGISTERED = True
            except Exception:
                pass

def is_devanagari(text: str) -> bool:
    """Returns True if string contains any Devanagari script characters."""
    return any('\u0900' <= char <= '\u097F' for char in str(text or ""))

def render_gdi_token(text: str, font_size: int, font_name: str = 'Akshar', bold: bool = True):
    """Renders text with Windows native Uniscribe/GDI using Akshar Bold to guarantee 100% accurate Devanagari conjuncts & ligatures."""
    if not text or os.name != 'nt':
        return None, 0, 0
    ensure_akshar_font()
    try:
        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        weight = 700 if bold else 400
        hfont = gdi32.CreateFontW(-font_size, 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, font_name)
        gdi32.SelectObject(memdc, hfont)

        size = SIZE()
        gdi32.GetTextExtentPoint32W(memdc, text, len(text), ctypes.byref(size))
        w, h = size.cx + 40, size.cy + 40

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        p_bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(p_bits), 0, 0)
        gdi32.SelectObject(memdc, hbmp)
        gdi32.SelectObject(memdc, hfont)

        gdi32.SetTextColor(memdc, 0x00FFFFFF)
        gdi32.SetBkColor(memdc, 0x00000000)
        gdi32.SetBkMode(memdc, 2)

        rect = wintypes.RECT(20, 20, w, h)
        user32.DrawTextW(memdc, text, -1, ctypes.byref(rect), 0x00000000)

        buf = (ctypes.c_ubyte * (w * h * 4)).from_address(p_bits.value)
        arr = np.ctypeslib.as_array(buf).reshape((h, w, 4)).copy()

        gdi32.DeleteObject(hfont)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)

        mask = arr[20:20+size.cy, 20:20+size.cx, 0]
        return mask, size.cx, size.cy
    except Exception:
        return None, 0, 0
    except Exception:
        return None, 0, 0

def composite_mask_on_pil(pil_img: Image.Image, mask: np.ndarray, x: int, y: int, color_rgb: tuple, stroke: bool = True):
    """Composites a grayscale glyph mask onto PIL image with optional dilated black outline."""
    if mask is None or mask.size == 0:
        return
    mh, mw = mask.shape
    img_w, img_h = pil_img.size

    if x >= img_w or y >= img_h or x + mw <= 0 or y + mh <= 0:
        return

    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(img_w, x + mw), min(img_h, y + mh)

    mx1, my1 = x1 - x, y1 - y
    mx2, my2 = mx1 + (x2 - x1), my1 + (y2 - y1)

    sub_mask = mask[my1:my2, mx1:mx2]

    box = (x1, y1, x2, y2)
    roi_pil = pil_img.crop(box)
    roi_arr = np.array(roi_pil, dtype=np.float32)

    if stroke:
        kernel = np.ones((3, 3), np.uint8)
        s_mask = cv2.dilate(sub_mask, kernel, iterations=1)
        s_alpha = (s_mask.astype(np.float32) / 255.0)[:, :, None]
        roi_arr = (1.0 - s_alpha) * roi_arr + s_alpha * np.array([0.0, 0.0, 0.0], dtype=np.float32)

    t_alpha = (sub_mask.astype(np.float32) / 255.0)[:, :, None]
    col_arr = np.array([float(color_rgb[0]), float(color_rgb[1]), float(color_rgb[2])], dtype=np.float32)
    roi_arr = (1.0 - t_alpha) * roi_arr + t_alpha * col_arr

    res_pil = Image.fromarray(np.clip(roi_arr, 0, 255).astype(np.uint8))
    pil_img.paste(res_pil, box)

def measure_line_width(draw, tokens, font, font_size: int = 54):
    w = 0
    for t in tokens:
        t_str = t.get("text", "") if isinstance(t, dict) else str(t)
        if is_devanagari(t_str) and os.name == 'nt':
            _, tw, _ = render_gdi_token(t_str, font_size, bold=True)
            w += tw
        else:
            try:
                bbox = draw.textbbox((0, 0), t_str, font=font)
                w += (bbox[2] - bbox[0])
            except Exception:
                w += len(t_str) * (font.size * 0.55 if hasattr(font, 'size') else 24)
    return w

def detect_image_text_position(img: np.ndarray) -> str:
    """
    Identifies whether prominent text/headlines in the source image are located
    in the TOP region or the BOTTOM region using OpenCV morphological gradient density,
    color/saturation analysis (cyan, yellow, white text), and human face protection.
    Returns: 'top' or 'bottom'
    """
    if img is None:
        return 'bottom'

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Human Face Detection Safeguard:
    # If prominent human faces exist in the upper 48% of the image (e.g. Balen Shah, public figures, actors),
    # graphic designers position headline banners at the BOTTOM to avoid covering heads/faces.
    top_face_detected = False
    try:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=3, minSize=(int(w*0.08), int(h*0.08)))
        for (fx, fy, fw, fh) in faces:
            face_center_y = fy + fh / 2.0
            if face_center_y < h * 0.48:
                top_face_detected = True
                break
    except Exception:
        pass

    # 2. Text in social media graphics/posters has high gradient energy and distinct aspect ratios
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Horizontal morphological closing to group characters into text lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, int(w * 0.035)), 3))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, h_kernel)

    # 3. Vibrant Colored Headline Detection (Cyan, Yellow, White headlines on news cards)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Cyan / Blue text mask: H [80, 110], S > 80, V > 100
    cyan_mask = cv2.inRange(hsv, np.array([80, 80, 100]), np.array([115, 255, 255]))
    # Yellow / Gold text mask: H [15, 35], S > 100, V > 120
    yellow_mask = cv2.inRange(hsv, np.array([15, 100, 120]), np.array([38, 255, 255]))
    color_text = cv2.bitwise_or(cyan_mask, yellow_mask)
    c_connected = cv2.morphologyEx(color_text, cv2.MORPH_CLOSE, h_kernel)

    combined_text_map = cv2.bitwise_or(connected, c_connected)
    contours, _ = cv2.findContours(combined_text_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    top_score = 0.0
    bot_score = 0.0

    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        aspect = cw / float(ch + 1e-5)
        # Headline/title candidate: wide horizontal block, reasonable height
        if cw > w * 0.14 and ch > h * 0.015 and ch < h * 0.28 and aspect > 1.6:
            y_center = y + ch / 2.0
            area = cw * ch
            # Top 42% vs Bottom 42%
            if y_center < h * 0.42:
                dist_weight = 1.0 + (1.0 - (y_center / (h * 0.42)))
                top_score += area * dist_weight
            elif y_center > h * 0.58:
                dist_weight = 1.0 + ((y_center - h * 0.58) / (h * 0.42))
                bot_score += area * dist_weight

    # 1. Clear winner when one region has text and the other does not:
    if top_score > 300 and bot_score < 150:
        return 'top'
    if bot_score > 300 and top_score < 150:
        return 'bottom'

    # 2. Both regions have detectable text:
    if top_score > 300 and bot_score > 300:
        if top_face_detected:
            return 'bottom'
        if top_score > bot_score * 1.3:
            return 'top'
        return 'bottom'

    # 3. Clean editorial image with no significant text overlay:
    # Default to 'bottom' (standard professional graphic layout)
    return 'bottom'

def render_final_poster(base_img: np.ndarray, overlay_lines: list, highlight_hex: str = "random", badge_label: str = "", dest_page_name: str = "", output_path: str = "output/poster.jpg", **kwargs):
    """
    Renders 4:5 visual poster strictly matching user reference layout:
    - Large, bold uppercase typography in dual-tone (White + Dynamic Highlight Color).
    - Centered horizontal alignment for all lines with whole-sentence thematic entity highlights.
    - Destination page branding badge (using individual destination page name).
    - Randomized visible highlight colors: Red, Light Blue, Dark Yellow, Cyan, Emerald, Coral.
    - NO attribution footer line.
    - Smooth faded dark black gradient placed on TOP or BOTTOM to block original source text cleanly.
    """
    target_w, target_h = 1080, 1350
    h, w, _ = base_img.shape

    # Pre-calculate typography & badge layout
    temp_img = Image.new("RGB", (target_w, target_h))
    temp_draw = ImageDraw.Draw(temp_img)
    safe_margin = 60
    safe_max_w = target_w - (safe_margin * 2) # 960px

    # Normalize lines into lists of token dicts
    normalized_lines = []
    for line in overlay_lines:
        if isinstance(line, str):
            words = line.split(" ")
            mid = max(1, len(words) // 2)
            normalized_lines.append([
                {"text": " ".join(words[:mid]) + " ", "type": "white"},
                {"text": " ".join(words[mid:]), "type": "highlight"}
            ])
        elif isinstance(line, list):
            normalized_lines.append(line)

    # Branding Badge metrics matching exact reference style
    branding_name = dest_page_name or badge_label or kwargs.get("source_tag", "")
    badge_is_deva = is_devanagari(branding_name)

    # For all Nepali news pages/overlays, ensure the text overlay ending has '...'
    is_deva_overlay = badge_is_deva or any(
        any(is_devanagari(t.get("text", "") if isinstance(t, dict) else str(t)) for t in line)
        for line in normalized_lines
    )
    if is_deva_overlay and normalized_lines and normalized_lines[-1]:
        last_tok = normalized_lines[-1][-1]
        if isinstance(last_tok, dict) and "text" in last_tok:
            t = re.sub(r'[।!?.…—\-]+$', '', str(last_tok["text"])).rstrip()
            last_tok["text"] = t + "..."
        elif isinstance(last_tok, str):
            t = re.sub(r'[।!?.…—\-]+$', '', str(last_tok)).rstrip()
            normalized_lines[-1][-1] = t + "..."

    badge_font = get_font(26, bold=True)
    dest_badge_text = f"• {branding_name if badge_is_deva else branding_name.upper()} •" if branding_name else ""
    if branding_name:
        if badge_is_deva and os.name == 'nt':
            _, text_w, text_h = render_gdi_token(dest_badge_text, 26, bold=True)
            bw = text_w + 34
            bh = max(text_h + 14, 34)
        else:
            try:
                bbox = temp_draw.textbbox((0, 0), dest_badge_text, font=badge_font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                bw = text_w + 34
                bh = max(text_h + 14, 34)
            except Exception:
                bw, bh = 240, 34
                text_w, text_h = 200, 24
                bbox = (0, 4, 200, 28)
        radius = bh // 2  # Classic smooth stadium pill
        bx = (target_w - bw) // 2
    else:
        bx, bw, bh = 0, 0, 0
        text_w, text_h, radius = 0, 0, 0
        bbox = (0, 0, 0, 0)

    # Typography sizing: 100% INCREASED FONT SIZE (Doubled from 50-56px to 100-108px)
    safe_margin = 45
    safe_max_w = target_w - (safe_margin * 2) # 990px
    chosen_size = 108 if len(normalized_lines) <= 2 else 96
    for test_size in [chosen_size, 100, 92, 84, 76, 68, 60, 52]:
        line_spacing_test = int(test_size * 1.30)
        total_text_h_test = len(normalized_lines) * line_spacing_test
        total_content_h_test = (bh + 24 if branding_name else 0) + total_text_h_test

        f_test = get_font(test_size, bold=True)
        all_fit = True
        for line in normalized_lines:
            line_w = measure_line_width(temp_draw, line, f_test, font_size=test_size)
            if line_w > safe_max_w:
                all_fit = False
                break
        if all_fit and total_content_h_test <= (target_h - int(target_h * 0.62) - 16):
            chosen_size = test_size
            break
        chosen_size = test_size

    title_font = get_font(chosen_size, bold=True)
    line_spacing = int(chosen_size * 1.30)  # Generous line height ensures top & bottom matras never collide
    total_text_h = len(normalized_lines) * line_spacing

    # ALWAYS USE SOURCE AS 4:5 ASPECT RATIO IMAGE (Fill entire 1080x1350 canvas)
    scale = max(target_w / float(w), target_h / float(h))
    scaled_w = int(w * scale)
    scaled_h = int(h * scale)
    resized_art = cv2.resize(base_img, (scaled_w, scaled_h), interpolation=cv2.INTER_LANCZOS4)

    # Center crop to exact 1080x1350 (4:5 canvas)
    x_off = (scaled_w - target_w) // 2
    y_off = (scaled_h - target_h) // 2
    canvas = resized_art[y_off:y_off+target_h, x_off:x_off+target_w].copy()

    # Pro color grading is already applied once by the upstream pipeline caller (main.py / server.py)
    # Only grade here if explicitly requested or if base_img was not pre-graded
    if kwargs.get("apply_grade", False):
        try:
            from modules.image_cleaner import apply_cinematic_grade
            canvas = apply_cinematic_grade(canvas)
        except Exception:
            pass

    # Identify where original text is: TOP or BOTTOM
    text_position = kwargs.get("text_position")
    if not text_position or text_position == "auto":
        text_position = detect_image_text_position(canvas)
    text_position = str(text_position).lower()
    if text_position not in ["top", "bottom"]:
        text_position = "bottom"
    print(f"           [Text Placement] Placement: {text_position.upper()} -> Rendering seamless filmic photographic fade.")

    gap = 20
    total_content_h = (bh + gap if branding_name else 0) + total_text_h

    # Detect exact bounding boxes of text in canvas to ensure full coverage if source had text
    gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    k_el = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m_grad = cv2.morphologyEx(gray_canvas, cv2.MORPH_GRADIENT, k_el)
    _, m_thresh = cv2.threshold(m_grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    k_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, int(target_w * 0.035)), 3))
    m_conn = cv2.morphologyEx(m_thresh, cv2.MORPH_CLOSE, k_h)
    m_cnts, _ = cv2.findContours(m_conn, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    top_text_max_y = int(target_h * 0.30)
    bot_text_min_y = int(target_h * 0.70)
    has_bot_text = False
    has_top_text = False
    for c in m_cnts:
        bx_t, by_t, bw_t, bh_t = cv2.boundingRect(c)
        aspect = bw_t / float(bh_t + 1e-5)
        if bw_t > target_w * 0.12 and bh_t > target_h * 0.012 and bh_t < target_h * 0.25 and aspect > 1.6:
            y_mid = by_t + bh_t / 2.0
            if y_mid < target_h * 0.45:
                top_text_max_y = max(top_text_max_y, by_t + bh_t)
                has_top_text = True
            elif y_mid > target_h * 0.55:
                bot_text_min_y = min(bot_text_min_y, by_t)
                has_bot_text = True

    dark_black = np.array([8, 8, 10], dtype=np.float32)

    if text_position == "top":
        top_margin = 48
        by = top_margin
        start_text_y = by + (bh + gap if branding_name else 0)
        content_bottom = start_text_y + total_text_h
        
        # Solid dark backing covers text region + detected original top text
        text_floor = max(content_bottom + 35, (top_text_max_y + 15) if has_top_text else (content_bottom + 35))
        fade_depth = max(180, int(total_content_h * 0.65))
        grad_bottom = min(target_h, text_floor + fade_depth)

        # 1. Dark backing across text area [0, text_floor] (100% opaque, zero ghost text)
        for y in range(text_floor):
            canvas[y, :] = dark_black.astype(np.uint8)

        # 2. Filmic cosine smoothstep feathering into the photography [text_floor, grad_bottom]
        for y in range(text_floor, grad_bottom):
            t = (grad_bottom - y) / float(grad_bottom - text_floor + 1e-5)
            ease = 0.5 * (1.0 - math.cos(math.pi * t))
            alpha = ease
            canvas[y, :] = ((1.0 - alpha) * canvas[y, :].astype(np.float32) + alpha * dark_black).astype(np.uint8)

        # Subtle clean at bottom edge for watermarks (bottom 5%)
        bot_strip_h = int(target_h * 0.05)
        strip_start = target_h - bot_strip_h
        for y in range(strip_start, target_h):
            t = (y - strip_start) / float(bot_strip_h)
            alpha = t * 0.75
            canvas[y, :] = ((1.0 - alpha) * canvas[y, :].astype(np.float32) + alpha * dark_black).astype(np.uint8)

    else:
        # Bottom placement:
        # Subtle atmospheric top vignette (gentle 5% top edge frame)
        top_fade_h = int(target_h * 0.06)
        for y in range(top_fade_h):
            alpha = (1.0 - (y / float(top_fade_h))) * 0.12
            canvas[y, :] = ((1.0 - alpha) * canvas[y, :].astype(np.float32) + alpha * np.array([8, 8, 10], dtype=np.float32)).astype(np.uint8)

        # Position text with clean bottom breathing margin
        bottom_margin = 55
        start_text_y = target_h - bottom_margin - total_text_h
        by = start_text_y - bh - gap if branding_name else start_text_y
        content_top = by

        # Determine where dark backing starts:
        # If original bottom text was detected, cover it; otherwise start comfortably above badge
        if has_bot_text and bot_text_min_y < target_h * 0.85:
            text_roof = min(content_top - 25, bot_text_min_y - 20)
        else:
            text_roof = content_top - 35
        text_roof = max(int(target_h * 0.45), text_roof)

        # Filmic cosine smoothstep feather zone extending upward into the photo
        fade_depth = max(180, int(total_content_h * 0.65))
        grad_top = max(0, text_roof - fade_depth)

        # 1. Filmic cosine smoothstep feather zone [grad_top, text_roof]
        for y in range(grad_top, text_roof):
            t = (y - grad_top) / float(text_roof - grad_top + 1e-5)
            ease = 0.5 * (1.0 - math.cos(math.pi * t))
            alpha = ease
            canvas[y, :] = ((1.0 - alpha) * canvas[y, :].astype(np.float32) + alpha * dark_black).astype(np.uint8)

        # 2. 100% Solid dark backing behind text & badge [text_roof, target_h] (zero ghost text)
        for y in range(text_roof, target_h):
            canvas[y, :] = dark_black.astype(np.uint8)

    pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    # Dynamic Highlight Color Selection
    if not highlight_hex or highlight_hex == "random":
        seed = kwargs.get("post_id") or kwargs.get("seed") or output_path or dest_page_name
        highlight_hex = pick_highlight_color(seed)
    elif kwargs.get("randomize_color", False) and not highlight_hex.startswith("#"):
        seed = kwargs.get("post_id") or kwargs.get("seed") or output_path or dest_page_name
        highlight_hex = pick_highlight_color(seed)

    highlight_rgb = hex_to_rgb(highlight_hex)

    # Render High-Visibility Studio Branding Badge — perfectly centered pill
    if branding_name:
        bx = (target_w - bw) // 2
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=radius, fill=(10, 10, 14), outline=highlight_rgb, width=2)
        if badge_is_deva and os.name == 'nt':
            b_mask, bw_act, bh_act = render_gdi_token(dest_badge_text, 22, bold=True)
            bx_text = int((target_w - bw_act) / 2.0)
            by_text = int(by + (bh - bh_act) / 2.0)
            composite_mask_on_pil(pil_img, b_mask, bx_text, by_text, highlight_rgb, stroke=False)
        else:
            draw.text((target_w / 2.0, by + bh / 2.0), dest_badge_text, font=badge_font, fill=highlight_rgb, anchor="mm")

    # Render Headline Typography — each line mathematically centered
    for line in normalized_lines:
        line_is_deva = any(is_devanagari(t.get("text", "") if isinstance(t, dict) else str(t)) for t in line)
        full_line_tokens = []
        for token in line:
            t_str = token.get("text", "") if isinstance(token, dict) else str(token)
            t_type = token.get("type", "white") if isinstance(token, dict) else "white"
            full_line_tokens.append((t_str, t_type))

        if line_is_deva and os.name == 'nt':
            rendered_tokens = []
            total_line_w = 0
            for t_str, t_type in full_line_tokens:
                m, tw, th = render_gdi_token(t_str, chosen_size, bold=True)
                rendered_tokens.append((m, tw, th, t_type))
                total_line_w += tw

            cur_x = (target_w - total_line_w) / 2.0
            for m, tw, th, t_type in rendered_tokens:
                color = highlight_rgb if t_type == "highlight" else (255, 255, 255)
                composite_mask_on_pil(pil_img, m, int(cur_x), int(start_text_y), color, stroke=True)
                cur_x += tw
        else:
            # Use exact font typographical advance width for subpixel centering
            total_line_w = sum(draw.textlength(t_str, font=title_font) for t_str, _ in full_line_tokens)
            cur_x = (target_w - total_line_w) / 2.0

            for t_str, t_type in full_line_tokens:
                color = highlight_rgb if t_type == "highlight" else (255, 255, 255)
                draw.text((cur_x, start_text_y), t_str, font=title_font, fill=color, stroke_width=2, stroke_fill=(0, 0, 0))
                cur_x += draw.textlength(t_str, font=title_font)

        start_text_y += line_spacing

    # NO attribution footer line (removed completely as requested)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pil_img.save(output_path, "JPEG", quality=98, subsampling=0)
    return output_path
