import os
import cv2
import numpy as np
import hashlib
import random
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
    in the TOP region or the BOTTOM region using OpenCV morphological gradient density.
    Returns: 'top' or 'bottom'
    """
    if img is None:
        return 'bottom'

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Text in social media graphics/posters has high gradient energy and distinct aspect ratios
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Horizontal morphological closing to group characters into text lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, int(w * 0.035)), 3))
    connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, h_kernel)

    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    top_score = 0.0
    bot_score = 0.0

    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        aspect = cw / float(ch + 1e-5)
        # Headline/title candidate: wide horizontal block, reasonable height
        if cw > w * 0.15 and ch > h * 0.015 and ch < h * 0.25 and aspect > 1.8:
            y_center = y + ch / 2.0
            area = cw * ch
            # Top 42% vs Bottom 42%
            if y_center < h * 0.42:
                dist_weight = 1.0 + (1.0 - (y_center / (h * 0.42)))
                top_score += area * dist_weight
            elif y_center > h * 0.58:
                dist_weight = 1.0 + ((y_center - h * 0.58) / (h * 0.42))
                bot_score += area * dist_weight

    if top_score > bot_score * 1.2:
        return 'top'
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

    # Subtle HD unsharp mask for crystal-clear edges
    blurred = cv2.GaussianBlur(canvas, (0, 0), sigmaX=1.5)
    canvas = cv2.addWeighted(canvas, 1.15, blurred, -0.15, 0)

    # Identify where original text is: TOP or BOTTOM
    text_position = kwargs.get("text_position")
    if not text_position or text_position == "auto":
        text_position = detect_image_text_position(canvas)
    text_position = str(text_position).lower()
    if text_position not in ["top", "bottom"]:
        text_position = "bottom"
    print(f"           [Text Placement] Detected original text position: {text_position.upper()} -> Placing faded black gradient at {text_position.upper()} to block original text cleanly.")

    max_alpha = 0.94
    gap = 20
    total_content_h = (bh + gap if branding_name else 0) + total_text_h

    # Detect exact bounding boxes of text in canvas to ensure 100% blocking coverage
    gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    k_el = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m_grad = cv2.morphologyEx(gray_canvas, cv2.MORPH_GRADIENT, k_el)
    _, m_thresh = cv2.threshold(m_grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    k_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, int(target_w * 0.035)), 3))
    m_conn = cv2.morphologyEx(m_thresh, cv2.MORPH_CLOSE, k_h)
    m_cnts, _ = cv2.findContours(m_conn, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    top_text_max_y = int(target_h * 0.32)
    bot_text_min_y = int(target_h * 0.68)
    for c in m_cnts:
        bx_t, by_t, bw_t, bh_t = cv2.boundingRect(c)
        aspect = bw_t / float(bh_t + 1e-5)
        if bw_t > target_w * 0.12 and bh_t > target_h * 0.012 and bh_t < target_h * 0.25 and aspect > 1.6:
            y_mid = by_t + bh_t / 2.0
            if y_mid < target_h * 0.45:
                top_text_max_y = max(top_text_max_y, by_t + bh_t)
            elif y_mid > target_h * 0.55:
                bot_text_min_y = min(bot_text_min_y, by_t)

    dark_black = np.array([6, 6, 8], dtype=np.uint8)

    if text_position == "top":
        # Base covers entire detected top text with solid dark black (100% blocked), ensuring enough room for large typography
        base_bottom = max(int(target_h * 0.36), min(int(target_h * 0.45), max(total_content_h + 60, top_text_max_y + 40)))
        fade_end = min(target_h - 200, base_bottom + 180)

        # 1. Solid dark black covering all original text so zero ghost text shows through
        for y in range(base_bottom):
            canvas[y, :] = dark_black

        # 2. Smooth faded gradient transitioning into the image
        for y in range(base_bottom, fade_end):
            t = (fade_end - y) / float(fade_end - base_bottom)
            alpha = (t ** 1.8)
            canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * dark_black

        # 3. Clean any source watermark footer bar at bottom edge (bottom 6% with soft fade)
        bot_strip_h = int(target_h * 0.06) # 81px
        fade_strip_h = 15
        strip_start = target_h - bot_strip_h
        for y in range(strip_start - fade_strip_h, strip_start):
            alpha = (y - (strip_start - fade_strip_h)) / float(fade_strip_h)
            canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * dark_black
        for y in range(strip_start, target_h):
            canvas[y, :] = dark_black

        # Vertically center badge and text inside top black base [0, base_bottom]
        base_h = base_bottom
        if total_content_h <= base_h:
            pad = (base_h - total_content_h) // 2
            by = max(28, pad)
            start_text_y = by + (bh + gap if branding_name else 0)
        else:
            by = 28
            start_text_y = by + (bh + gap if branding_name else 0)

    else:
        # Atmospheric Top Vignette (top 8%)
        top_fade_h = int(target_h * 0.08)
        for y in range(top_fade_h):
            alpha = (1.0 - (y / top_fade_h)) * 0.20
            canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * np.array([8, 8, 10])

        # Base covers entire detected bottom text with solid dark black (100% blocked), ensuring room for large typography
        base_top = min(int(target_h * 0.64), max(int(target_h * 0.55), min(target_h - total_content_h - 60, bot_text_min_y - 40)))
        fade_start = max(100, base_top - 180)

        # 1. Smooth faded gradient leading into black base
        for y in range(fade_start, base_top):
            t = (y - fade_start) / float(base_top - fade_start)
            alpha = (t ** 1.8)
            canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * dark_black

        # 2. Solid dark black covering all original text so zero ghost text shows through
        for y in range(base_top, target_h):
            canvas[y, :] = dark_black

        # EXACT VERTICAL CENTERING OF LOGO & TEXT IN BLACK BASE:
        base_h = target_h - base_top
        if total_content_h <= base_h:
            pad = (base_h - total_content_h) // 2
            by = base_top + pad
            start_text_y = by + (bh + gap if branding_name else 0)
        else:
            bottom_padding = 28
            start_text_y = target_h - bottom_padding - total_text_h
            by = start_text_y - bh - gap

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
