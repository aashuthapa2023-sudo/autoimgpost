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
    bundled_font = os.path.join(repo_root, "assets", "fonts", "bold_headline.ttf")
    font_candidates = [
        bundled_font,
        r"C:\Windows\Fonts\ariblk.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
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

    # 4:5 center-weighted crop
    target_ratio = 4.0 / 5.0
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x_start = (w - new_w) // 2
        cropped = base_img[:, x_start:x_start + new_w]
    else:
        new_h = int(w / target_ratio)
        y_start = (h - new_h) // 2
        cropped = base_img[y_start:y_start + new_h, :]

    resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    # Post-upscale Super-Smooth pass: Eliminates all stretch pixelation, smoothing skin & backgrounds
    resized_smooth = cv2.bilateralFilter(resized, d=7, sigmaColor=28, sigmaSpace=28)
    # Subtle unsharp mask for crystal-clear HD edges (eyes, hair, clothing contours)
    blurred = cv2.GaussianBlur(resized_smooth, (0, 0), sigmaX=2.0)
    resized = cv2.addWeighted(resized_smooth, 1.30, blurred, -0.30, 0)

    # 1. Atmospheric Top Vignette (top 10%)
    top_fade_h = int(target_h * 0.10)
    for y in range(top_fade_h):
        alpha = (1.0 - (y / top_fade_h)) * 0.25
        resized[y, :] = (1.0 - alpha) * resized[y, :] + alpha * np.array([8, 8, 10])

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

    # Pre-calculate typography layout to position the fade precisely downside
    temp_img = Image.new("RGB", (target_w, target_h))
    temp_draw = ImageDraw.Draw(temp_img)
    safe_margin = 55
    safe_max_w = target_w - (safe_margin * 2) # 970px

    chosen_size = 76
    for test_size in [76, 70, 64, 58, 52, 48, 44]:
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
    line_spacing = int(chosen_size * 1.25)
    total_text_h = len(normalized_lines) * line_spacing

    bottom_padding = 65
    start_text_y = target_h - bottom_padding - total_text_h

    # Branding Badge metrics
    branding_name = dest_page_name or badge_label or kwargs.get("source_tag", "")
    badge_font = get_font(28, bold=True)
    dest_badge_text = f"●  {branding_name.upper()}  ●" if branding_name else ""
    if branding_name:
        try:
            bbox = temp_draw.textbbox((0, 0), dest_badge_text, font=badge_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            bw = text_w + 52
            bh = text_h + 22
        except Exception:
            bw, bh = 280, 50
            text_w, text_h = 220, 30
        radius = bh // 2
        bx = (target_w - bw) // 2
        by = start_text_y - bh - 26
    else:
        bx, by, bw, bh = 0, start_text_y, 0, 0
        text_w, text_h, radius = 0, 0, 0

    # 2. Smooth Exponential Bottom Vignette placed downside
    # Starts gently at 58% height, solid black right above the branding badge
    start_y = max(int(target_h * 0.58), by - 120)
    solid_y = by - 12

    for y in range(start_y, target_h):
        if y < solid_y:
            t = (y - start_y) / float(solid_y - start_y)
            alpha = (t ** 1.6) * 1.0
        else:
            alpha = 1.0
        resized[y, :] = (1.0 - alpha) * resized[y, :] + alpha * np.array([6, 6, 8])

    pil_img = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    # Dynamic Highlight Color Selection
    if not highlight_hex or highlight_hex == "random" or kwargs.get("randomize_color", True):
        if highlight_hex and highlight_hex.startswith("#") and highlight_hex.upper() not in ["#FFC83B", "#RANDOM"]:
            pass
        else:
            seed = kwargs.get("post_id") or kwargs.get("seed") or output_path or dest_page_name
            highlight_hex = pick_highlight_color(seed)

    highlight_rgb = hex_to_rgb(highlight_hex)

    # Render High-Visibility Studio Branding Badge
    if branding_name:
        # Multi-layer 3D soft drop shadow for depth
        draw.rounded_rectangle([bx, by + 4, bx + bw, by + bh + 4], radius=radius, fill=(0, 0, 0, 160))
        # Solid vibrant accent pill container (pops brilliantly on dark gradient)
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=radius, fill=highlight_rgb, outline=(255, 255, 255), width=2)
        # Contrast-aware text: Jet black on bright colors, pure white on deep colors
        luminance = (0.299 * highlight_rgb[0] + 0.587 * highlight_rgb[1] + 0.114 * highlight_rgb[2]) / 255.0
        badge_text_color = (12, 12, 16) if luminance > 0.45 else (255, 255, 255)
        tx = bx + (bw - text_w) // 2
        ty = by + (bh - text_h) // 2 - 2
        draw.text((tx, ty), dest_badge_text, font=badge_font, fill=badge_text_color)

    for line in normalized_lines:
        line_w = measure_line_width(draw, line, title_font)
        cur_x = (target_w - line_w) // 2  # EXACT CENTER ALIGNMENT

        for token in line:
            t_str = token.get("text", "") if isinstance(token, dict) else str(token)
            t_type = token.get("type", "white") if isinstance(token, dict) else "white"
            color = highlight_rgb if t_type == "highlight" else (255, 255, 255)

            # Drop shadow with stroke for intense 3D clarity
            draw.text((cur_x + 3, start_text_y + 4), t_str, font=title_font, fill=(0, 0, 0), stroke_width=3, stroke_fill=(0, 0, 0))
            # Main extra-bold text with subtle dark stroke for razor-sharp legibility
            draw.text((cur_x, start_text_y), t_str, font=title_font, fill=color, stroke_width=2, stroke_fill=(0, 0, 0))

            try:
                t_bbox = draw.textbbox((cur_x, start_text_y), t_str, font=title_font)
                cur_x += (t_bbox[2] - t_bbox[0])
            except Exception:
                cur_x += len(t_str) * int(chosen_size * 0.55)

        start_text_y += line_spacing

    # NO attribution footer line (removed completely as requested)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pil_img.save(output_path, "JPEG", quality=98, subsampling=0)
    return output_path
