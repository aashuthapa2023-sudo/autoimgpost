import os
import re
import cv2
import numpy as np
import hashlib
import random
import math
from PIL import Image, ImageDraw, ImageFont, features
import json
from pathlib import Path
from functools import lru_cache

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

def get_font(size: int, bold: bool = True, language: str = 'en'):
    root = Path(__file__).resolve().parent.parent
    if language == 'ne':
        candidates = [root/'assets/fonts/Akshar-Bold.ttf']
    else:
        candidates = [root/'assets/fonts/BarlowCondensed-Bold.ttf', root/'assets/fonts/impact.ttf']
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise ValueError('Required editorial font is missing; refusing fallback glyphs')

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

    if top_face_detected:
        return 'bottom'
    return 'top' if top_score > max(1.0, bot_score * 1.15) else 'bottom'

def fit_headline_line(tokens, font, font_size, highlight_rgb, max_width, max_height):
    """Rasterize full glyph bounds before fitting, so strokes and matras stay safe."""
    tiles = []
    offsets = []
    for text, kind in tokens:
        color = highlight_rgb if kind == "highlight" else (255, 255, 255)
        if is_devanagari(text) and os.name == 'nt':
            mask, width, height = render_gdi_token(text, font_size, bold=True)
            tile = Image.new('RGBA', (max(1, width), max(1, height)))
            tile.paste(color, (0, 0), Image.fromarray(mask).convert('L'))
            offsets.append(-font.getmetrics()[0])
        else:
            probe = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            left, top, right, bottom = probe.textbbox((0, 0), text, font=font, stroke_width=2, anchor='ls')
            width = max(right - min(0, left), math.ceil(probe.textlength(text, font=font)))
            tile = Image.new('RGBA', (max(1, width + 4), max(1, bottom - top + 4)))
            ImageDraw.Draw(tile).text((2 - min(0, left), 2 - top), text, font=font,
                                     fill=color, stroke_width=2, stroke_fill=(0, 0, 0), anchor='ls')
            offsets.append(top - 2)
        tiles.append(tile)
    # Preserve each glyph's baseline offset instead of aligning cropped word tops.
    origin = min(offsets or [0])
    height = max([offset + tile.height for offset, tile in zip(offsets, tiles)] or [1]) - origin
    line = Image.new('RGBA', (max(1, sum(t.width for t in tiles)), max(1, height)))
    x = 0
    for tile, offset in zip(tiles, offsets):
        line.alpha_composite(tile, (x, offset - origin))
        x += tile.width
    scale = min(1.0, max_width / line.width, max_height / line.height)
    if scale < 1:
        line = line.resize((max(1, int(line.width * scale)), max(1, int(line.height * scale))), Image.Resampling.LANCZOS)
    bounds = line.getbbox()
    if bounds:
        line = line.crop(bounds)  # Centre visible glyphs, excluding padding and trailing spaces.
    return line


def _render_runs(tokens, size, language, accent):
    return _render_runs_cached(tuple(tokens),size,language,accent)


@lru_cache(maxsize=512)
def _render_runs_cached(tokens,size,language,accent):
    font = get_font(size,language=language)
    return fit_headline_line(tokens,font,size,accent,100000,100000)


def _wrap_headline(words, size, language, max_width, accent):
    lines = [[]]
    for word, kind in words:
        token = (word + ' ', kind)
        candidate = lines[-1] + [token]
        if lines[-1] and _render_runs(candidate, size, language, accent).width > max_width:
            lines.append([token])
        else:
            lines[-1] = candidate
    # Prefer balanced visible lengths over a final orphan word.
    for i in range(len(lines)-1, 0, -1):
        left, right = lines[i-1], lines[i]
        while len(left) > 1:
            current_delta = abs(_render_runs(left,size,language,accent).width - _render_runs(right,size,language,accent).width)
            new_right = [left[-1]] + right
            new_delta = abs(_render_runs(left[:-1],size,language,accent).width - _render_runs(new_right,size,language,accent).width)
            if new_delta >= current_delta or _render_runs(new_right,size,language,accent).width > max_width:
                break
            right.insert(0,left.pop())
    return lines


def render_final_poster(base_img, overlay_lines, highlight_hex='#FFC83B', badge_label='',
                        dest_page_name='', output_path='output/poster.jpg', **kwargs):
    """Render a measured editorial card and write a verifiable quality manifest."""
    if base_img is None or base_img.ndim != 3 or min(base_img.shape[:2]) < 240:
        raise ValueError('Clean source photograph is too small or invalid')
    words = []
    for line in overlay_lines:
        for token in ([{'text':line,'type':'white'}] if isinstance(line,str) else line):
            text = str(token.get('text','')) if isinstance(token,dict) else str(token)
            kind = token.get('type','white') if isinstance(token,dict) else 'white'
            words.extend((word,kind) for word in text.split())
    if not words or len(words) > 32:
        raise ValueError('Headline must be complete and concise before layout')
    language = 'ne' if any(is_devanagari(word) for word,_ in words) else 'en'
    if language == 'ne' and os.name != 'nt' and not features.check_feature('raqm'):
        raise ValueError('Devanagari shaping is unavailable; refusing broken text')
    accent = hex_to_rgb(highlight_hex if highlight_hex and highlight_hex != 'random' else '#FFC83B')
    background_hex = kwargs.get('panel_color','#0D111A')
    panel_color = hex_to_rgb(background_hex)
    if sum(accent)/3 < 100 or sum(panel_color)/3 > 65:
        raise ValueError('Brand colours do not provide safe headline contrast')
    margin = max(56,min(80,int(kwargs.get('safe_margin',64))))
    max_width = 1080 - 2*margin
    min_size = max(64,int(kwargs.get('min_font_size',68)))
    max_size = min(100,int(kwargs.get('max_font_size',94)))
    max_lines = min(3,int(kwargs.get('max_lines',3)))
    line_gap = 14 if language=='en' else 20
    # Bottom mastheads start the title 110px into a maximum470px panel.
    # Use the actual remaining glyph space without sacrificing the global margin.
    bottom_masthead = (kwargs.get('text_position','bottom')=='bottom'
                       and kwargs.get('logo_position','with-text')=='with-text')
    max_title_height = min(296,470-110-margin) if bottom_masthead else 290
    selected = None
    for size in range(max_size,min_size-1,-2):
        lines = _wrap_headline(words,size,language,max_width,accent)
        images = [_render_runs(line,size,language,accent) for line in lines]
        if len(lines)<=max_lines and all(0<im.width<=max_width and im.getbbox() for im in images):
            height = sum(im.height for im in images)+line_gap*(len(images)-1)
            if height <= max_title_height:
                selected = size,images
                break
    if selected is None:
        raise ValueError('Headline cannot fit at readable type size; rewrite before publishing')
    size,images = selected
    title_height=sum(im.height for im in images)+line_gap*(len(images)-1)
    brand_name=dest_page_name or badge_label
    brand_font=get_font(28,language='ne' if is_devanagari(brand_name) else 'en')
    if len(brand_name)>40:
        raise ValueError('Brand wordmark is too long')
    # Brand, breathing space, headline and bottom margin have fixed measured slots.
    panel_h=max(260,title_height+180)
    if bottom_masthead:
        panel_h=min(470,max(panel_h,title_height+110+margin))
    if panel_h>470:
        raise ValueError('Text panel would dominate the photograph')
    position=kwargs.get('text_position','bottom')
    if position not in ('top','bottom'):
        raise ValueError('Unsupported headline position')
    logo_position=kwargs.get('logo_position','with-text')
    allowed_logo_positions=('with-text','top-left','top-center','top-right','bottom-left','bottom-center','bottom-right')
    if logo_position not in allowed_logo_positions:
        raise ValueError('Unsupported branding position')
    external_brand=logo_position!='with-text' and not logo_position.startswith(position+'-')
    brand_strip=148 if external_brand else 0
    if external_brand:
        panel_h=max(242,title_height+128)
    photo_h=1350-panel_h-brand_strip
    photo_top=panel_h if position=='top' else brand_strip
    panel_top=0 if position=='top' else 1350-panel_h
    canvas=Image.new('RGB',(1080,1350),panel_color)
    photo=Image.fromarray(cv2.cvtColor(base_img,cv2.COLOR_BGR2RGB))
    scale=min(1080/photo.width,photo_h/photo.height)
    if kwargs.get('photo_fit')=='face-safe-cover':
        cover_scale=max(1080/photo.width,photo_h/photo.height)
        retained=(1080/cover_scale)*(photo_h/cover_scale)/(photo.width*photo.height)
        if cover_scale<=1.75 and retained>=.50:
            left=(photo.width-1080/cover_scale)/2;top=(photo.height-photo_h/cover_scale)/2
            right=photo.width-left;bottom=photo.height-top
            detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
            scan_scale=min(1,900/photo.width)
            gray=cv2.resize(cv2.cvtColor(base_img,cv2.COLOR_BGR2GRAY),(round(photo.width*scan_scale),round(photo.height*scan_scale)))
            faces=detector.detectMultiScale(gray,scaleFactor=1.15,minNeighbors=5,minSize=(35,35))
            if all((fx/scan_scale>=left and fy/scan_scale>=top and
                    (fx+fw)/scan_scale<=right and (fy+fh)/scan_scale<=bottom)
                   for fx,fy,fw,fh in faces):
                scale=cover_scale
    if scale>1.75:
        raise ValueError('Retained photograph would need excessive enlargement')
    photo=photo.resize((round(photo.width*scale),round(photo.height*scale)),Image.Resampling.LANCZOS)
    # Solid matte preserves the whole photograph without inventing blurred duplicates.
    photo_layer=Image.new('RGB',(1080,photo_h),panel_color)
    photo_layer.paste(photo,((1080-photo.width)//2,(photo_h-photo.height)//2))
    canvas.paste(photo_layer,(0,photo_top))
    draw=ImageDraw.Draw(canvas)
    rule_y=panel_top if position=='bottom' else panel_h-4
    draw.rectangle((0,rule_y,1079,rule_y+3),fill=accent)
    brand_y=(1350-margin-38 if position=='top' else margin+6) if external_brand else panel_top+(margin+6 if position=='top' else 48)
    brand=fit_headline_line([(brand_name.upper(),'highlight')],brand_font,28,accent,max_width,42)
    if brand.width>max_width or not brand.getbbox():
        raise ValueError('Branding could not be rendered clearly')
    # Optional owned logo appears once in a reserved header slot, never over the subject.
    logo_path=kwargs.get('logo_path')
    badge=None
    if logo_path:
        root=Path(__file__).resolve().parent.parent
        logo=(root/logo_path).resolve()
        if not logo.is_relative_to(root/'assets/branding'):
            raise ValueError('Logo must be a local approved branding asset')
        badge=Image.open(logo).convert('RGBA')
        badge.thumbnail((44,44),Image.Resampling.LANCZOS)
    group_width=brand.width+(badge.width+16 if badge else 0)
    if group_width>max_width:
        raise ValueError('Logo and wordmark cannot fit without overlap')
    alignment=logo_position.rsplit('-',1)[-1] if logo_position!='with-text' else 'center'
    group_x=margin if alignment=='left' else 1080-margin-group_width if alignment=='right' else (1080-group_width)//2
    logo_bounds=None
    if badge:
        canvas.paste(badge,(group_x,brand_y-6),badge)
        logo_bounds=[group_x,brand_y-6,group_x+badge.width,brand_y-6+badge.height]
    brand_x=group_x+(badge.width+16 if badge else 0)
    canvas.paste(brand,(brand_x,brand_y),brand)
    title_y=panel_top+(margin if external_brand else margin+68 if position=='top' else 110)
    bounds=[]
    for im in images:
        x=(1080-im.width)//2
        box=[x,title_y,x+im.width,title_y+im.height]
        if x<margin or box[2]>1080-margin or box[1]<margin or box[3]>min(1350-margin,panel_top+panel_h-32):
            raise ValueError('Headline exceeds its measured safe area')
        canvas.paste(im,(x,title_y),im)
        bounds.append(box)
        title_y+=im.height+line_gap
    output=Path(output_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(output,'JPEG',quality=96,subsampling=0)
    manifest={'schema_version':3,'approved':True,'image_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'caption_sha256':hashlib.sha256(str(kwargs.get('caption','')).encode('utf-8')).hexdigest(),
              'source_checked':kwargs.get('source_checked',False),'size':[1080,1350],
              'font_size':size,'safe_margin':margin,'text_bounds':bounds,'panel_height':panel_h,
              'panel_bounds':[0,panel_top,1080,panel_top+panel_h],
              'brand_bounds':[brand_x,brand_y,brand_x+brand.width,brand_y+brand.height],
              'logo_bounds':logo_bounds,
              'photo_bounds':[(1080-photo.width)//2,photo_top+(photo_h-photo.height)//2,photo.width,photo.height],
              'style_id':kwargs.get('style_id','editorial'),'headline':' '.join(word for word,_ in words),
              'headline_origin':kwargs.get('headline_origin','caption')}
    output.with_suffix('.quality.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(output)
