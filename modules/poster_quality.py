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
    original_card=data.get('layout_kind')=='preserved_source_card'
    if original_card:
        if data.get('preserved_source_approved') is not True or data.get('min_visible_letter_height',0)<32:
            raise ValueError('Original card did not pass headline readability approval')
    if size != (1080,1350) or (not original_card and data.get('font_size',0)<64):
        raise ValueError('Poster does not meet image size and typography requirements')
    margin=data.get('safe_margin',64)
    bounds=data.get('text_bounds',[])
    if not bounds or any(l<margin or r>1080-margin or t<margin or b>1350-margin or r<=l or b<=t for l,t,r,b in bounds):
        raise ValueError('Poster lettering is outside the approved safe area')
    panel=data.get('panel_bounds')
    if original_card:
        photo=data.get('photo_bounds')
        if not photo or any(l<photo[0] or r>photo[0]+photo[2] or t<photo[1] or b>photo[1]+photo[3] or b-t<32 for l,t,r,b in bounds):
            raise ValueError('Original card headline is outside its retained frame')
    elif not panel or any(t<panel[1]+32 or b>panel[3]-32 or abs((l+r)/2-540)>1 for l,t,r,b in bounds):
        raise ValueError('Headline is not centered inside its separate text panel')
    for key in ('brand_bounds','logo_bounds'):
        box=data.get(key)
        if box and (box[0]<margin or box[2]>1080-margin or box[1]<margin or box[3]>1350-margin):
            raise ValueError('Branding is outside the safe area')
    if data.get('layout_kind') == 'source_replacement':
        covers=data.get('replacement_bounds',[])
        if not covers or not data.get('logo_bounds'):
            raise ValueError('Source replacement needs opaque panels and destination logo')
        if any(not any(a<=l and c>=r and t0<=t and d>=b for a,t0,c,d in covers)
               for l,t,r,b in data.get('source_overlay_bounds',[])):
            raise ValueError('Source lettering is not completely covered by replacement panels')
    return data
