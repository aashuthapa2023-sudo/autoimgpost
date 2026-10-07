import cv2
import numpy as np
import requests
import urllib.parse
import os

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
            clean_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
            }
            resp_orig = requests.get(orig_url, headers=clean_headers, timeout=12)
            if resp_orig.status_code == 200 and 'text/html' not in resp_orig.headers.get('Content-Type', ''):
                arr = np.asarray(bytearray(resp_orig.content), dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None and img.shape[0] >= 200 and img.shape[1] >= 200:
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
        if img is not None:
            if img.shape[0] < 50 or img.shape[1] < 50:
                return None
            # Preserve native resolution so the quality gate cannot mistake an
            # enlarged thumbnail for a detailed source photograph.
        return img
    except Exception:
        return None

def detect_and_remove_watermarks(img: np.ndarray) -> np.ndarray:
    """Legacy entry point: gradients and red objects are not proof of a watermark.

    Preserve the original pixels. The pipeline uses OCR and separable source
    panels through erase_text_and_watermarks instead of generic inpainting.
    """
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
    Safely preserves source image without destructively hard-wiping regions to black.
    Actual gradient feathering and text backing is handled organically by the poster engine.
    """
    return img

_source_text_reader = None


class SourceTextBoxes(list):
    """Recognized text plus separate detector evidence; never mix their trust levels."""
    def __init__(self, boxes=(), suspected_rows=(), suspected_marks=(), text_labels=None, text_confidences=None):
        super().__init__(boxes)
        self.suspected_rows = list(suspected_rows)
        self.suspected_marks = list(suspected_marks)
        self.text_labels = dict(text_labels or {})
        self.text_confidences = dict(text_confidences or {})


def _text_rows(boxes):
    rows = []
    for box in sorted(boxes, key=lambda item: item[1]):
        for index, row in enumerate(rows):
            overlap = min(row[3], box[3]) - max(row[1], box[1])
            if overlap > min(row[3]-row[1], box[3]-box[1]) * .5:
                rows[index] = (min(row[0], box[0]), min(row[1], box[1]),
                               max(row[2], box[2]), max(row[3], box[3]))
                break
        else:
            rows.append(tuple(box))
    return rows


def _clamped_boxes(boxes, height, width, padding=0):
    result = []
    for left, top, right, bottom in boxes:
        left = max(0, int(left)-padding)
        top = max(0, int(top)-padding)
        right = min(width, int(right)+padding)
        bottom = min(height, int(bottom)+padding)
        if right > left and bottom > top:
            result.append((left, top, right, bottom))
    return result


def detect_source_text_boxes(img, reader=None):
    """Inspect the whole source, keeping unreadable detector hits separate.

    CRAFT alone often labels water, instruments, fur, and buildings as text.
    Its hits can identify a designed panel, but never authorize pixel removal.
    """
    if img is None:
        return SourceTextBoxes()
    global _source_text_reader
    if reader is None:
        if _source_text_reader is None:
            import easyocr
            options = {'gpu': False, 'verbose': False}
            if os.getenv('IMAGE_OCR_MODEL_DIR'):
                options['model_storage_directory'] = os.environ['IMAGE_OCR_MODEL_DIR']
            # Nepali is explicitly supported by EasyOCR's Devanagari model;
            # include it rather than relying on Hindi's character whitelist.
            _source_text_reader = easyocr.Reader(['en', 'ne', 'hi'], **options)
        reader = _source_text_reader
    height, width = img.shape[:2]
    padding = max(4, round(min(height, width)*.006))
    recognized = []
    labels = {}
    confidences = {}
    for polygon, text, confidence in reader.readtext(img, detail=1, paragraph=False):
        letters = sum(character.isalnum() for character in str(text))
        xs, ys = zip(*polygon)
        near_corner = ((max(ys) <= height*.18 or min(ys) >= height*.82)
                       and (max(xs) <= width*.22 or min(xs) >= width*.78))
        minimum_confidence = .35 if letters >= 3 else (.35 if near_corner and letters == 2
                              else .60 if letters == 2 else .55 if near_corner else .80)
        if letters < 1 or confidence < minimum_confidence:
            continue
        bounds = _clamped_boxes([(min(xs), min(ys), max(xs), max(ys))], height, width, padding)
        if not bounds:
            continue
        box = bounds[0]
        recognized.append(box)
        labels[box] = str(text)
        confidences[box] = float(confidence)
    suspected = []
    marks = []
    if hasattr(reader, 'detect'):
        horizontal, free = reader.detect(img, min_size=12, text_threshold=.65,
                                         low_text=.35, link_threshold=.4)
        detected = [(left, top, right, bottom)
                    for group in horizontal for left, right, top, bottom in group]
        suspected = [row for row in _text_rows(detected)
                     if row[2]-row[0] >= width*.35 and row[3]-row[1] <= height*.14]
        # Small source initials can be recognized as punctuation or a single
        # glyph. Keep that uncertainty rather than claiming an OCR-clean photo.
        # These bounds may veto a source, never authorize erasing its pixels.
        marks = [box for box in detected
                 if (box[3] <= height*.18 or box[1] >= height*.82)
                 and (box[2] <= width*.22 or box[0] >= width*.78)
                 and box[2]-box[0] >= max(12, width*.018)
                 and box[3]-box[1] >= max(12, height*.012)
                 and (box[2]-box[0])*(box[3]-box[1]) <= height*width*.025]
    return SourceTextBoxes(recognized,
                           _clamped_boxes(suspected, height, width, padding),
                           _clamped_boxes(marks, height, width, padding),
                           labels, confidences)


def _source_provenance_marks(boxes, height, width):
    """Identify small original source credits, never body headlines or subtitles.

    Compact peripheral initials and known source names can stay in their
    original pixels. Group the entire corner so a paragraph cannot evade the
    size limit by splitting into tiny OCR words. Original-image geometry is
    used again after cropping; newly peripheral body text is never promoted.
    """
    known = {'nd','nf','bbc','cnn','nbc','cbs','abc','npr','afp','ap','netflixdaily','netflixfanatics','himali',
             'himalimedia','smartmedia','smartmedianp','oceanssecret','anisha',
             'nepalspeaks','हि','हिं','हिमाली'}
    labels = getattr(boxes, 'text_labels', {})
    groups = {}
    candidates = list(boxes)+list(getattr(boxes, 'suspected_marks', []))
    for box in _clamped_boxes(candidates, height, width):
        left, top, right, bottom = box
        vertical = 'top' if bottom <= height*.15 else 'bottom' if top >= height*.85 else None
        horizontal = 'left' if right <= width*.22 else 'right' if left >= width*.78 else None
        if vertical and horizontal:
            groups.setdefault((vertical,horizontal), []).append(box)
    result = []
    for cluster in groups.values():
        left=min(box[0] for box in cluster); top=min(box[1] for box in cluster)
        right=max(box[2] for box in cluster); bottom=max(box[3] for box in cluster)
        mark_width,mark_height=right-left,bottom-top
        if (mark_width > width*.18 or mark_height > height*.10
                or mark_width*mark_height > height*width*.015):
            continue
        recognized_labels = [str(labels[tuple(box)]) for box in cluster if tuple(box) in labels]
        initials_only = True
        label_rejected = False
        for label in recognized_labels:
            letters=''.join(character for character in label if character.isalnum())
            initial = letters.isascii() and letters.isalpha() and letters.isupper() and len(letters)<=2
            if letters.casefold() not in known and not initial:
                label_rejected = True
                break
            initials_only = initials_only and initial
        if label_rejected:
            continue
        # Unreadable initials must remain compact. A long horizontal detector
        # hit is too easily a subtitle, credit line or a short source headline.
        max_aspect = 5.0 if recognized_labels and not initials_only else 2.8
        if mark_width/max(1,mark_height) > max_aspect:
            continue
        result.append((left,top,right,bottom))
    return result


def _inside_source_mark(box, marks):
    left,top,right,bottom=box
    return any(left>=mark_left-4 and top>=mark_top-4
               and right<=mark_right+4 and bottom<=mark_bottom+4
               for mark_left,mark_top,mark_right,mark_bottom in marks)


def remove_source_text(img, boxes):
    """Never fabricate photo pixels to erase a rectangular OCR detection.

    Even a small label can overlap a face, animal, instrument or other subject.
    A safe source panel can be cropped by extract_source_photo; text inside the
    retained photograph requires another source image.
    """
    if img is None or not boxes:
        return img
    raise ValueError('Embedded source text overlaps the photograph; choose another image instead of inpainting subjects')


def _flat_panel_rows(img, boxes):
    """Rows with a uniform designed background after excluding lettering.

    Exclusions are only used to assess backgrounds, never to change pixels.
    Require a substantial visible background on each row. Missing rows are
    bridged only where OCR boxes cover them and neighboring backgrounds agree.
    """
    height, width = img.shape[:2]
    left, right = int(width*.15), max(int(width*.85), int(width*.15)+1)
    # Sample columns rather than scaling vertically: crop boundaries stay exact.
    step = max(1, (right-left)//320)
    xs = np.arange(left, right, step)
    samples = img[:, xs].astype(np.int16)
    available = np.ones(samples.shape[:2], dtype=bool)
    covered = np.zeros(height, dtype=bool)
    for box_left, top, box_right, bottom in boxes:
        available[top:bottom, (xs >= box_left) & (xs < box_right)] = False
        if box_right-box_left >= width*.25:
            covered[top:bottom] = True
    flat = np.zeros(height, dtype=bool)
    colors = np.zeros((height, 3), dtype=np.float32)
    for y in range(height):
        visible = samples[y, available[y]]
        if len(visible) < max(16, len(xs)*.18):
            continue
        color = np.median(visible, axis=0)
        colors[y] = color
        flat[y] = np.mean(np.max(np.abs(visible-color), axis=1) <= 14) >= .90
    # Letter rows may be fully covered, but unrelated photo texture cannot
    # become a panel just because a fixed-size morphological kernel joined it.
    y = 0
    while y < height:
        if flat[y]:
            y += 1
            continue
        start = y
        while y < height and not flat[y]:
            y += 1
        end = y
        if (start > 0 and end < height and np.all(covered[start:end])
                and end-start <= height*.15
                and np.max(np.abs(colors[start-1]-colors[end])) <= 18):
            flat[start:end] = True
    return flat


def _has_panel_text(rows, width, top, bottom, verified):
    relevant = [row for row in rows if row[1] >= top and row[3] <= bottom
                and row[2]-row[0] >= width*.25]
    if not relevant:
        return False
    # Recognizable broad headline + solid background suffices. Unreadable
    # typography needs multiple aligned lines, not one detector band of waves.
    if any(row[1] >= top and row[3] <= bottom and row[2]-row[0] >= width*.25
           for row in _text_rows(verified)):
        return True
    broad = [row for row in relevant if row[2]-row[0] >= width*.40]
    return len(broad) >= 2 and max(row[0] for row in broad)-min(row[0] for row in broad) <= width*.12


def extract_source_photo(img, boxes, *, retained_marks=None, return_crop_bounds=False):
    """Extract only edge-connected solid news panels; preserve photo pixels.

    A headline's y-coordinate is never itself a crop boundary. Typography over
    a photograph and ambiguous panels are rejected. Small original corner
    provenance remains intact; it is never erased or expanded into a headline.
    """
    if img is None:
        return (None,0,0) if return_crop_bounds else None
    height, width = img.shape[:2]
    verified = _clamped_boxes(boxes, height, width)
    suspected = _clamped_boxes(getattr(boxes, 'suspected_rows', []), height, width)
    marks = _clamped_boxes(getattr(boxes, 'suspected_marks', []), height, width)
    evidence = verified+suspected+marks
    provenance = _source_provenance_marks(boxes,height,width) if retained_marks is None else retained_marks
    if not evidence:
        return (img,0,height) if return_crop_bounds else img
    rows = _text_rows(evidence)
    flat = _flat_panel_rows(img, evidence)
    top, bottom = 0, height
    # Allow up to 8px of compression/separator line at the physical edge.
    edge_slop = max(2, min(8, round(height*.006)))
    if flat[edge_slop]:
        candidate = edge_slop
        while candidate < height and flat[candidate]:
            candidate += 1
        if _has_panel_text(rows, width, 0, candidate, verified):
            top = candidate
    if flat[height-1-edge_slop]:
        candidate = height-1-edge_slop
        while candidate >= 0 and flat[candidate]:
            candidate -= 1
        candidate += 1
        if _has_panel_text(rows, width, candidate, height, verified):
            bottom = candidate
    cropped = top > 0 or bottom < height
    if cropped:
        retained_height = bottom-top
        if (retained_height < max(280, height*.35)
                or retained_height*width < 200000 or width/retained_height > 3.0):
            raise ValueError('Source panels leave too little usable photograph; choose another image')
        # A sharp boundary to varied photo pixels is essential. Do not crop a
        # natural flat sky or a fade based solely on approximate OCR placement.
        for boundary, direction in ((top, 1), (bottom, -1)):
            if boundary in (0, height):
                continue
            photo_slice = flat[boundary: min(height, boundary+12)] if direction == 1 else flat[max(0,boundary-12):boundary]
            if not len(photo_slice) or np.mean(photo_slice) > .5:
                raise ValueError('Source panel boundary is ambiguous; choose another image')
    remaining = [box for box in verified if box[1] < bottom and box[3] > top
                 and not _inside_source_mark(box,provenance)]
    if remaining:
        raise ValueError('Source text or logo remains inside the photo; skipping to preserve the subject')
    if any(box[1] < bottom and box[3] > top and not _inside_source_mark(box,provenance) for box in marks):
        raise ValueError('Unverified corner lettering or source logo remains; choose another image')
    remaining_suspected = [row for row in suspected if row[1] < bottom and row[3] > top]
    # Multiple broad aligned lines are strong evidence of unrecognized embedded
    # typography (including Devanagari), even in the center of the photograph.
    if len(remaining_suspected) >= 2:
        for first in remaining_suspected:
            for second in remaining_suspected:
                if (first != second and abs(first[0]-second[0]) <= width*.10
                        and abs(first[2]-second[2]) <= width*.15
                        and abs(first[1]-second[1]) <= height*.25):
                    raise ValueError('Unrecognized source typography overlaps the photo; choose another image')
    photo = img[top:bottom].copy() if cropped else img
    return (photo,top,bottom) if return_crop_bounds else photo


def erase_text_and_watermarks(img: np.ndarray, source_text_boxes=None, return_crop_bounds=False):
    """Return only the residual-checked photo, optionally with original row bounds."""
    boxes = detect_source_text_boxes(img) if source_text_boxes is None else source_text_boxes
    if img is None:
        return (None,0,0) if return_crop_bounds else None
    provenance = _source_provenance_marks(boxes,*img.shape[:2])
    photo,top,bottom = extract_source_photo(img,boxes,retained_marks=provenance,return_crop_bounds=True)
    if photo is None:
        return (None,top,bottom) if return_crop_bounds else None
    # Source credits must use the original-image decision; cropping cannot
    # turn a source subtitle into a newly allowed corner logo.
    retained_provenance = [(left,mark_top-top,right,mark_bottom-top)
                           for left,mark_top,right,mark_bottom in provenance
                           if mark_top<bottom and mark_bottom>top]
    # A second full-image inspection still rejects every body headline or
    # caption; narrowly bounded original provenance keeps its source pixels.
    residual = detect_source_text_boxes(photo)
    inspected = extract_source_photo(photo,residual,retained_marks=retained_provenance)
    if inspected is not photo:
        raise ValueError('Source text remains after photo extraction; skipping this image')
    return (photo,top,bottom) if return_crop_bounds else photo


def validate_image_quality(img: np.ndarray, min_dim: int = 500, min_sharpness: float = 100.0) -> tuple:
    """
    Validates image resolution and clarity to strictly eliminate blurry or pixelated images:
    - Verifies native dimensions are at least min_dim x min_dim and area >= 350,000 px
    - Verifies sharpness variance using Laplacian operator >= min_sharpness
    - Verifies color / contrast standard deviation >= 20 (rejects blank, washed out, or corrupted images)
    """
    if img is None:
        return False, "Image is None or corrupt"

    h, w = img.shape[:2]
    total_pixels = h * w
    if min(w, h) < min_dim or total_pixels < 350000:
        return False, f"Low resolution: {w}x{h}px ({total_pixels:,} pixels; minimum required is {min_dim}px short-edge & 350,000px area)"

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
    """
    Applies subtle, natural studio editorial color grading:
    - Gentle bilateral denoising to remove compression artifacts without losing skin texture.
    - Subtle CLAHE contrast enhancement (clipLimit=1.15) blended 75/25 with original luminance.
    - Gentle film S-curve with soft highlight roll-off (never blows out skin or crushes shadows).
    - Skin-tone protected vibrance (HSV): protects human faces from orange/red shifts.
    - Clean micro-contrast (unsharp mask: 1.10x) for crisp editorial detail with zero halos.
    - Seamless, unnoticeable corner falloff (no heavy dark vignette).
    """
    if img is None:
        return None

    # 1. Gentle edge-preserving bilateral denoising (smooth compression noise while keeping edges sharp)
    denoised = cv2.bilateralFilter(img, d=5, sigmaColor=12, sigmaSpace=12)

    # 2. CIE-LAB Color Space: Subtle Dynamic Contrast (CLAHE)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Mild clip limit 1.15 avoids micro-contrast noise or harsh textures
    clahe = cv2.createCLAHE(clipLimit=1.15, tileGridSize=(8, 8))
    l_clahe = clahe.apply(l)
    
    # Blend 75% original + 25% CLAHE for natural, non-processed look
    l_blended = cv2.addWeighted(l, 0.75, l_clahe, 0.25, 0)

    # 3. Smooth Film Tone Curve with Gentle Highlight Roll-Off
    # Soft contrast adjustment: lift midtone clarity without crushing blacks or blowing whites
    lut_curve = np.zeros(256, dtype=np.uint8)
    for i in range(256):
        x = i / 255.0
        # Gentle cubic film contrast curve
        if x < 0.5:
            y = 0.5 * ((2.0 * x) ** 1.06)
        else:
            y = 1.0 - 0.5 * ((2.0 * (1.0 - x)) ** 1.06)
        # Soft highlight roll-off above 0.85
        if y > 0.85:
            y = 0.85 + (y - 0.85) * 0.88
        lut_curve[i] = np.clip(y * 255.0, 0, 255).astype(np.uint8)

    l_graded = cv2.LUT(l_blended, lut_curve)
    lab_graded = cv2.merge((l_graded, a, b))
    graded_bgr = cv2.cvtColor(lab_graded, cv2.COLOR_LAB2BGR)

    # 4. Skin-Tone Protected Vibrance in HSV Space
    hsv = cv2.cvtColor(graded_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    h_chan, s_chan, v_chan = cv2.split(hsv)

    # Human skin hues in OpenCV HSV are typically [5, 26]
    # Calculate skin-tone mask to strictly avoid oversaturating human faces
    is_skin = (h_chan >= 5.0) & (h_chan <= 26.0) & (s_chan >= 30.0) & (v_chan >= 50.0)
    
    # Normal vibrance: slightly boost dull/washed-out non-skin tones (+4% to +8% max)
    s_norm = s_chan / 255.0
    vibrance_factor = 1.0 + (1.0 - s_norm) * 0.08
    vibrance_factor = np.clip(vibrance_factor, 1.0, 1.08)
    
    # Protect skin: keep factor near 1.00 (neutral natural skin)
    vibrance_factor = np.where(is_skin, 1.01, vibrance_factor)
    
    s_boosted = np.clip(s_chan * vibrance_factor, 0, 255.0)
    hsv_boosted = cv2.merge((h_chan, s_boosted, v_chan))
    graded_bgr = cv2.cvtColor(hsv_boosted.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 5. Subtle Micro-Clarity (Razor sharp without pixel halos or fringing)
    blur_fine = cv2.GaussianBlur(graded_bgr, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(graded_bgr, 1.12, blur_fine, -0.12, 0)

    # 6. Ultra-Subtle Natural Corner Falloff (Max 5% only at extreme outer corners)
    h, w = sharpened.shape[:2]
    X = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    Y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    xx, yy = np.meshgrid(X, Y)
    dist = np.sqrt(xx * xx + yy * yy)
    vignette = np.clip(1.0 - 0.06 * (dist ** 2.5), 0.94, 1.0)
    vignette_3c = cv2.merge([vignette, vignette, vignette])

    final_graded = np.clip(sharpened.astype(np.float32) * vignette_3c, 0, 255).astype(np.uint8)
    return final_graded
