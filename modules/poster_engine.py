import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c*2 for c in hex_str])
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    font_candidates = [
        r"C:\Windows\Fonts\impact.ttf",
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

def render_final_poster(base_img: np.ndarray, overlay_lines: list, highlight_hex: str = "#FFC83B", badge_label: str = "", dest_page_name: str = "", output_path: str = "output/poster.jpg", **kwargs):
    """
    Renders 4:5 visual poster strictly matching user reference layout:
    - Large, bold uppercase typography in dual-tone (White + Gold Highlight).
    - Centered horizontal alignment for all lines.
    - Destination page branding badge (using individual destination page name).
    - NO attribution footer line.
    - Smooth deep gradient fade concealing original captions cleanly.
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

    # 1. Atmospheric Top Vignette (top 12%)
    top_fade_h = int(target_h * 0.12)
    for y in range(top_fade_h):
        alpha = (1.0 - (y / top_fade_h)) * 0.35
        resized[y, :] = (1.0 - alpha) * resized[y, :] + alpha * np.array([8, 8, 10])

    # 2. Smooth Exponential Bottom Vignette
    # Starts at 52%, reaches solid deep black at 78% height
    start_y = int(target_h * 0.52)
    solid_y = int(target_h * 0.78)

    for y in range(start_y, target_h):
        if y < solid_y:
            t = (y - start_y) / float(solid_y - start_y)
            alpha = (t ** 1.8) * 0.98
        else:
            alpha = 1.0
        resized[y, :] = (1.0 - alpha) * resized[y, :] + alpha * np.array([6, 6, 8])

    pil_img = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    highlight_rgb = hex_to_rgb(highlight_hex)

    # 3. Individual Destination Page Name Branding Badge
    branding_name = dest_page_name or badge_label or kwargs.get("source_tag", "")
    if branding_name:
        badge_font = get_font(18, bold=True)
        dest_badge_text = f"●  {branding_name.upper()}  ●"
        try:
            bbox = draw.textbbox((0, 0), dest_badge_text, font=badge_font)
            bw = bbox[2] - bbox[0] + 32
            bh = bbox[3] - bbox[1] + 16
        except Exception:
            bw, bh = 240, 36

        # Centered destination badge above the headline
        bx = (target_w - bw) // 2
        by = target_h - 390
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=(18, 18, 22), outline=highlight_rgb, width=2)
        draw.text((bx + 16, by + 8), dest_badge_text, font=badge_font, fill=highlight_rgb)

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

    # 4. Center-Aligned Bold Typography matching user reference image
    safe_margin = 60
    safe_max_w = target_w - (safe_margin * 2) # 960px

    # Calculate optimal font size starting at 58px down to 36px
    chosen_size = 56
    for test_size in [56, 52, 48, 44, 40, 36]:
        f_test = get_font(test_size, bold=True)
        all_fit = True
        for line in normalized_lines:
            line_w = measure_line_width(draw, line, f_test)
            if line_w > safe_max_w:
                all_fit = False
                break
        if all_fit:
            chosen_size = test_size
            break
        chosen_size = test_size

    title_font = get_font(chosen_size, bold=True)
    line_spacing = int(chosen_size * 1.30)
    total_text_h = len(normalized_lines) * line_spacing

    # Place text dynamically in the lower third with perfect balance
    start_text_y = target_h - 325 if branding_name else (target_h - 300)

    for line in normalized_lines:
        line_w = measure_line_width(draw, line, title_font)
        cur_x = (target_w - line_w) // 2  # EXACT CENTER ALIGNMENT

        for token in line:
            t_str = token.get("text", "") if isinstance(token, dict) else str(token)
            t_type = token.get("type", "white") if isinstance(token, dict) else "white"
            color = highlight_rgb if t_type == "highlight" else (255, 255, 255)

            # Drop shadow for intense 3D clarity
            draw.text((cur_x + 3, start_text_y + 3), t_str, font=title_font, fill=(0, 0, 0))
            draw.text((cur_x + 1, start_text_y + 1), t_str, font=title_font, fill=(0, 0, 0))
            # Main bold text
            draw.text((cur_x, start_text_y), t_str, font=title_font, fill=color)

            try:
                t_bbox = draw.textbbox((cur_x, start_text_y), t_str, font=title_font)
                cur_x += (t_bbox[2] - t_bbox[0])
            except Exception:
                cur_x += len(t_str) * int(chosen_size * 0.55)

        start_text_y += line_spacing

    # NO attribution footer line (removed completely as requested)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pil_img.save(output_path, "JPEG", quality=95)
    return output_path
