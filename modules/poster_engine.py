import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def hex_to_rgb(hex_str: str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def get_font(size: int, bold: bool = True):
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/impact.ttf",
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
            w += len(t_str) * (font.size * 0.55 if hasattr(font, 'size') else 20)
    return w

def render_final_poster(base_img: np.ndarray, overlay_lines: list, highlight_hex: str = "#FFC83B", badge_label: str = "NETFLIX FANS EXCLUSIVE", badge_path: str = None, output_path: str = "output/poster.jpg"):
    target_w, target_h = 1080, 1350
    h, w, _ = base_img.shape

    # Center crop to 4:5 aspect ratio
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

    # Smooth deep gradient covering lower 42%
    start_y = int(target_h * 0.54)
    solid_y = int(target_h * 0.76)

    for y in range(start_y, target_h):
        if y < solid_y:
            t = (y - start_y) / (solid_y - start_y)
            alpha = t * t * (3.0 - 2.0 * t)
        else:
            alpha = 1.0
        resized[y, :] = (1.0 - alpha) * resized[y, :] + alpha * np.array([12, 12, 14])

    # Convert to PIL
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil_img)

    badge_font = get_font(18, bold=True)
    highlight_rgb = hex_to_rgb(highlight_hex)

    # 1. Draw Modern Pill Badge
    if badge_label:
        badge_text = f"●  {badge_label.upper()}  ●"
        try:
            bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
            bw = bbox[2] - bbox[0] + 32
            bh = bbox[3] - bbox[1] + 16
        except Exception:
            bw, bh = 260, 38

        bx = 60
        by = target_h - 320
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=(24, 24, 28), outline=highlight_rgb, width=2)
        draw.text((bx + 16, by + 8), badge_text, font=badge_font, fill=highlight_rgb)

    # Normalize overlay lines
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

    # Auto-fit font size so text never overflows 960px width
    max_allowed_w = target_w - 120  # 960px
    chosen_size = 50
    for test_size in [50, 46, 42, 38, 34]:
        f_candidate = get_font(test_size, bold=True)
        all_fit = True
        for line in normalized_lines:
            lw = measure_line_width(draw, line, f_candidate)
            if lw > max_allowed_w:
                all_fit = False
                break
        if all_fit:
            chosen_size = test_size
            break
        chosen_size = test_size

    title_font = get_font(chosen_size, bold=True)
    text_y = target_h - 240
    line_spacing = int(chosen_size * 1.35)

    for line in normalized_lines:
        cur_x = 60
        for token in line:
            t_str = token.get("text", "") if isinstance(token, dict) else str(token)
            t_type = token.get("type", "white") if isinstance(token, dict) else "white"
            color = highlight_rgb if t_type == "highlight" else (255, 255, 255)

            # Drop shadow
            draw.text((cur_x + 3, text_y + 3), t_str, font=title_font, fill=(0, 0, 0))
            # Main text
            draw.text((cur_x, text_y), t_str, font=title_font, fill=color)

            try:
                t_bbox = draw.textbbox((cur_x, text_y), t_str, font=title_font)
                cur_x += (t_bbox[2] - t_bbox[0])
            except Exception:
                cur_x += len(t_str) * int(chosen_size * 0.55)

        text_y += line_spacing

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pil_img.save(output_path, "JPEG", quality=95)
    return output_path
