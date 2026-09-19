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
        os.path.join(repo_root, "assets", "fonts", "impact.ttf"),
        os.path.join(repo_root, "assets", "fonts", "bold_headline.ttf"),
        r"C:\Windows\Fonts\impact.ttf",
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

def measure_line_width(draw, tokens, font):
    w = 0
    for t in tokens:
        t_str = t.get("text", "") if isinstance(t, dict) else str(t)
        try:
            bbox = draw.textbbox((0, 0), t_str, font=font)
            w += (bbox[2] - bbox[0])
        except Exception:
            w += len(t_str) * (font.size * 0.55 if hasattr(font, 'size') else 24)
    return w

def render_final_poster(base_img: np.ndarray, overlay_lines: list, highlight_hex: str = "random", badge_label: str = "", dest_page_name: str = "", output_path: str = "output/poster.jpg", **kwargs):
    """
    Renders 4:5 visual poster strictly matching user reference layout:
    - Large, bold uppercase typography in dual-tone (White + Dynamic Highlight Color).
    - Centered horizontal alignment for all lines with whole-sentence thematic entity highlights.
    - Destination page branding badge (using individual destination page name).
    - Randomized visible highlight colors: Red, Light Blue, Dark Yellow, Cyan, Emerald, Coral.
    - NO attribution footer line.
    - Smooth deep gradient fade placed downside concealing original captions cleanly.
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

    # Typography sizing matching exact reference style
    chosen_size = 54 if len(normalized_lines) >= 3 else 58
    for test_size in [chosen_size, 50, 46, 42, 38]:
        f_test = get_font(test_size, bold=True)
        all_fit = True
        for line in normalized_lines:
            line_w = measure_line_width(temp_draw, line, f_test)
            if line_w > safe_max_w:
                all_fit = False
                break
        if all_fit:
            chosen_size = test_size
            break
        chosen_size = test_size

    title_font = get_font(chosen_size, bold=True)
    line_spacing = int(chosen_size * 1.15)
    total_text_h = len(normalized_lines) * line_spacing

    # Branding Badge metrics matching exact reference style
    branding_name = dest_page_name or badge_label or kwargs.get("source_tag", "")
    badge_font = get_font(22, bold=True)
    dest_badge_text = f"• {branding_name.upper()} •" if branding_name else ""
    if branding_name:
        try:
            bbox = temp_draw.textbbox((0, 0), dest_badge_text, font=badge_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            bw = text_w + 30
            bh = max(text_h + 12, 30)
        except Exception:
            bw, bh = 220, 30
            text_w, text_h = 180, 20
            bbox = (0, 4, 180, 24)
        radius = bh // 2  # Classic smooth stadium pill
        bx = (target_w - bw) // 2
    else:
        bx, bw, bh = 0, 0, 0
        text_w, text_h, radius = 0, 0, 0
        bbox = (0, 0, 0, 0)

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

    # Atmospheric Top Vignette (top 8%)
    top_fade_h = int(target_h * 0.08)
    for y in range(top_fade_h):
        alpha = (1.0 - (y / top_fade_h)) * 0.20
        canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * np.array([8, 8, 10])

    # FADED DARK BLACK GRADIENT:
    # Starts fading softly from 50% height (675px) down to the black base at 68% (918px)
    start_y = int(target_h * 0.50)  # 675px (50%)
    base_top = int(target_h * 0.68) # 918px (68%) — top of the Black Base

    # Soft, faded dark black: max_alpha is 0.94 to 0.97 so the black base stays atmospheric and faded
    max_alpha = 0.94

    for y in range(start_y, target_h):
        if y < base_top:
            t = (y - start_y) / float(base_top - start_y)
            alpha = (t ** 1.6) * max_alpha
        else:
            t_base = (y - base_top) / float(target_h - base_top)
            alpha = max_alpha + 0.03 * t_base
        canvas[y, :] = (1.0 - alpha) * canvas[y, :] + alpha * np.array([6, 6, 8])

    gap = 20
    total_content_h = (bh + gap if branding_name else 0) + total_text_h

    # EXACT VERTICAL CENTERING OF LOGO & TEXT IN BLACK BASE:
    # Black base spans from base_top (918px) to target_h (1350px) = 432px
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
        draw.text((target_w / 2.0, by + bh / 2.0), dest_badge_text, font=badge_font, fill=highlight_rgb, anchor="mm")

    # Render Headline Typography — each line mathematically centered
    for line in normalized_lines:
        full_line_tokens = []
        for token in line:
            t_str = token.get("text", "") if isinstance(token, dict) else str(token)
            t_type = token.get("type", "white") if isinstance(token, dict) else "white"
            full_line_tokens.append((t_str, t_type))

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
