"""Conservative multi-scale matching of known source badges in image corners."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'branding'


def detect_source_logos(image):
    h, w = image.shape[:2]
    template = cv2.imread(str(ASSETS / 'himali_reference.png'))
    if template is None:
        raise FileNotFoundError('Missing Himali logo reference')
    matches = []
    # Search all four corners, never faces or objects in the image centre.
    cw, ch = int(w * .25), int(h * .25)
    for x0, y0 in ((0, 0), (w-cw, 0), (0, h-ch), (w-cw, h-ch)):
        region = image[y0:y0+ch, x0:x0+cw]
        best = None
        for ratio in np.linspace(.5, 1.8, 53):
            scale = w / 1080.0 * ratio
            tw, th = round(template.shape[1]*scale), round(template.shape[0]*scale)
            if min(tw, th) < 20 or tw > cw or th > ch:
                continue
            ref = cv2.resize(template, (tw, th), interpolation=cv2.INTER_AREA)
            score_map = cv2.matchTemplate(region, ref, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(score_map)
            if best is None or score > best[0]:
                best = (score, (x0+location[0], y0+location[1], tw, th))
        if best and best[0] >= .88:
            matches.append(best[1])
    return matches


def apply_branding(poster, boxes, source_size):
    """Map detected bounds through the renderer's centre crop, then overlay."""
    sw, sh = source_size
    scale = max(poster.width/sw, poster.height/sh)
    rw, rh = int(sw*scale), int(sh*scale)
    ox, oy = (rw-poster.width)//2, (rh-poster.height)//2
    logo = Image.open(ASSETS / 'nepal_speaks.png').convert('RGBA')
    for x, y, w, h in boxes:
        left, top = round(x*rw/sw)-ox, round(y*rh/sh)-oy
        width, height = round(w*rw/sw), round(h*rh/sh)
        # The reference badge is clipped by the right image edge: retain its
        # circular proportions rather than squeezing a circle into visible bounds.
        diameter = max(width, height)
        badge = logo.resize((diameter, diameter), Image.Resampling.LANCZOS)
        backing = Image.new('RGBA', badge.size, (255, 255, 255, 255))
        backing.alpha_composite(badge)
        mask = Image.new('L', badge.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diameter-1, diameter-1), fill=255)
        poster.paste(backing.convert('RGB'), (left, top), mask)
    return poster
