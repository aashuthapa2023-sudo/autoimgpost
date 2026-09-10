import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def hex_to_rgb(hex_str: str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def render_final_poster(base_img: np.ndarray, overlay_lines: list, highlight_hex: str, badge_path: str = None, output_path: str = "output.jpg"):
    target_w, target_h = 1080, 1350
    h, w, _ = base_img.shape

    # Crop to 4:5 aspect ratio
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

    # Add dark vertical gradient vignette on lower 50%
    overlay = resized.copy()
    start_y = int(target_h * 0.48)
    for y in range(start_y, target_h):
        alpha = ((y - start_y) / (target_h - start_y)) ** 1.35 * 0.92
        overlay[y, :] = (1.0 - alpha) * overlay[y, :] + alpha * np.array([10, 10, 12])

    cv2.addWeighted(overlay, 1.0, resized, 0.0, 0, resized)

    # Convert to PIL for sharp typography
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil_img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
    except Exception:
        font = ImageFont.load_default()

    highlight_rgb = hex_to_rgb(highlight_hex)
    text_y = target_h - 260

    for line in overlay_lines:
        if isinstance(line, str):
            line_text = line
        elif isinstance(line, list):
            line_text = "".join([token.get("text", "") if isinstance(token, dict) else str(token) for token in line])
        else:
            line_text = str(line)
        draw.text((60, text_y), line_text, font=font, fill=(255, 255, 255))
        text_y += 68

    pil_img.save(output_path, "JPEG", quality=95)
