"""Retain a readable source card intact when a page explicitly selects this mode."""
import hashlib
import json
import os
import re
from pathlib import Path
import cv2
from PIL import Image
from modules.poster_engine import get_font, fit_headline_line, hex_to_rgb
from modules.llm_transformer import headline_is_usable, check_source_grounding, split_clean_sentences

_english_source_reader = None


def _read_english_card(image):
    # A multilingual recognizer can turn English decimal digits into another
    # script. Use the card's configured language rather than changing OCR text.
    global _english_source_reader
    if _english_source_reader is None:
        import easyocr
        options = {'gpu': False}
        if os.getenv('IMAGE_OCR_MODEL_DIR'):
            options['model_storage_directory'] = os.environ['IMAGE_OCR_MODEL_DIR']
        _english_source_reader = easyocr.Reader(['en'], **options)
    return _english_source_reader.readtext(image, detail=1, paragraph=False)


def _source_lines(records):
    lines=[]
    for polygon,text,confidence in records:
        if sum(c.isalnum() for c in str(text))<2:
            continue
        xs,ys=zip(*polygon)
        box=[min(xs),min(ys),max(xs),max(ys)]
        for line in lines:
            overlap=min(line['box'][3],box[3])-max(line['box'][1],box[1])
            if overlap>min(line['box'][3]-line['box'][1],box[3]-box[1])*.45:
                line['parts'].append((box[0],str(text)))
                line['confidence'] = min(line['confidence'], float(confidence))
                line['box']=[min(line['box'][0],box[0]),min(line['box'][1],box[1]),max(line['box'][2],box[2]),max(line['box'][3],box[3])]
                break
        else:
            lines.append({'box':box,'parts':[(box[0],str(text))],'confidence':float(confidence)})
    for line in lines:
        line['text']=' '.join(text for _,text in sorted(line['parts']))
    return sorted(lines,key=lambda line:line['box'][1])


def inspect_readable_source_card(image,source_caption,records=None):
    """Approve only a source-grounded, visibly readable existing headline."""
    height,width=image.shape[:2]
    if records is None:
        records = _read_english_card(image)
    lines=_source_lines(records)
    # The full original frame is contained within 64px margins and a masthead.
    scale=min(952/width,1150/height)
    broad=[line for line in lines if line['box'][2]-line['box'][0]>=width*.25]
    if any(line['confidence']<.55 for line in broad):
        raise ValueError('Original card contains uncertain headline or body lettering')
    readable=[line for line in broad if (line['box'][3]-line['box'][1])*scale>=32]
    if not 1<=len(readable)<=4:
        raise ValueError('Original card has no clearly readable headline')
    # Body paragraphs cannot be excused as an original headline.
    if any((line['box'][3]-line['box'][1])*scale<24 for line in broad):
        raise ValueError('Original card contains unreadable small body text')
    headline=' '.join(line['text'] for line in readable)
    # Match this existing headline to its own caption. Uncertainty in a different
    # paragraph must not invalidate a directly quoted, definite source fact.
    def normalized(text):
        return ' '.join(re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?",str(text).lower().replace('’',"'")))
    quoted_fact = normalized(headline)
    matches = [sentence for line in str(source_caption).splitlines()
               for sentence in split_clean_sentences(line)
               if quoted_fact and f' {quoted_fact} ' in f' {normalized(sentence)} ']
    if (not headline_is_usable(headline,'en') or not matches
            or not all(check_source_grounding(headline,sentence,'en') for sentence in matches)):
        raise ValueError('Original card headline is incomplete or not supported by its caption')
    for line in readable:
        left,top,right,bottom=line['box']
        if left<3 or right>width-3 or top<3 or bottom>height-3:
            raise ValueError('Original card lettering is clipped at its edge')
    return {'headline':headline,'headline_bounds':[line['box'] for line in readable],
            'source_image_sha256':hashlib.sha256(image.tobytes()).hexdigest()}


def render_preserved_source_card(image,review,caption,dest_page_name,output_path,highlight_hex='#4DD6E8',panel_color='#081E28',**kwargs):
    """Fit the untouched card and one page masthead; never add another headline."""
    if review.get('source_image_sha256')!=hashlib.sha256(image.tobytes()).hexdigest():
        raise ValueError('Original card changed after readability approval')
    margin=64
    background=hex_to_rgb(panel_color)
    accent=hex_to_rgb(highlight_hex)
    canvas=Image.new('RGB',(1080,1350),background)
    brand=fit_headline_line([(dest_page_name.upper(),'highlight')],get_font(32),32,accent,952,48)
    if not brand.getbbox() or brand.width>952:
        raise ValueError('Page masthead does not fit')
    brand_y=1350-margin-brand.height
    photo_limit=min(1150,brand_y-28-margin)
    photo=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
    scale=min(952/photo.width,photo_limit/photo.height)
    photo=photo.resize((round(photo.width*scale),round(photo.height*scale)),Image.Resampling.LANCZOS)
    x=(1080-photo.width)//2
    y=margin+(photo_limit-photo.height)//2
    canvas.paste(photo,(x,y))
    canvas.paste(brand,((1080-brand.width)//2,brand_y),brand)
    bounds=[[x+round(l*scale),y+round(t*scale),x+round(r*scale),y+round(b*scale)] for l,t,r,b in review['headline_bounds']]
    if any(b-t<32 for l,t,r,b in bounds):
        raise ValueError('Original headline becomes too small in the final card')
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(output,'JPEG',quality=96,subsampling=0)
    manifest={'schema_version':3,'approved':True,'source_checked':True,
              'layout_kind':'preserved_source_card','preserved_source_approved':True,
              'image_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'caption_sha256':hashlib.sha256(caption.encode('utf-8')).hexdigest(),
              'size':[1080,1350],'safe_margin':margin,'text_bounds':bounds,
              'min_visible_letter_height':min(b-t for l,t,r,b in bounds),
              'photo_bounds':[x,y,photo.width,photo.height],
              'brand_bounds':[(1080-brand.width)//2,brand_y,(1080+brand.width)//2,brand_y+brand.height],
              'headline':review['headline'],'style_id':kwargs.get('style_id','ocean_source_card')}
    output.with_suffix('.quality.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(output)
