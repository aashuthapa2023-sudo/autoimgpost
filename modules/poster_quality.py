"""Verify the exact image and caption approved by the renderer before upload."""
import hashlib
import json
from pathlib import Path
from PIL import Image

def verify_publishable_poster(image_path, caption):
    image=Path(image_path)
    report=image.with_suffix('.quality.json')
    if not image.exists() or not report.exists():
        raise ValueError('Poster has no quality approval; regenerate with the current pipeline')
    data=json.loads(report.read_text(encoding='utf-8'))
    if data.get('schema_version') != 3 or data.get('approved') is not True or data.get('source_checked') is not True:
        raise ValueError('Source cleanup and layout approval are required before publishing')
    if hashlib.sha256(image.read_bytes()).hexdigest()!=data.get('image_sha256'):
        raise ValueError('Poster changed after quality approval')
    if not caption or hashlib.sha256(caption.encode('utf-8')).hexdigest()!=data.get('caption_sha256'):
        raise ValueError('Caption does not match the approved poster')
    with Image.open(image) as poster:
        size=poster.size
    if size != (1080,1350) or data.get('font_size',0)<64:
        raise ValueError('Poster does not meet image size and typography requirements')
    margin=data.get('safe_margin',64)
    bounds=data.get('text_bounds',[])
    if not bounds or any(l<margin or r>1080-margin or t<margin or b>1350-margin or r<=l or b<=t for l,t,r,b in bounds):
        raise ValueError('Poster lettering is outside the approved safe area')
    panel=data.get('panel_bounds')
    if not panel or any(t<panel[1]+32 or b>panel[3]-32 or abs((l+r)/2-540)>1 for l,t,r,b in bounds):
        raise ValueError('Headline is not centered inside its separate text panel')
    for key in ('brand_bounds','logo_bounds'):
        box=data.get(key)
        if box and (box[0]<margin or box[2]>1080-margin or box[1]<margin or box[3]>1350-margin):
            raise ValueError('Branding is outside the safe area')
    return data
