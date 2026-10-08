"""Extract configured editorial frames without erasing photographed subjects."""
import re
from urllib.parse import urlsplit,parse_qs
import cv2
from modules.image_cleaner import SourceTextBoxes,_source_provenance_marks,_inside_source_mark


def source_profile(channel,post):
    parsed=urlsplit(str(post.get('source_page_url','')))
    if parsed.hostname not in ('facebook.com','www.facebook.com','m.facebook.com'):
        return None
    key=parsed.path.strip('/').split('/')[0].lower()
    if key=='profile.php':key=parse_qs(parsed.query).get('id',[''])[0]
    return channel.get('source_cleanup_profiles',{}).get(key)


def _normal(text):
    return re.sub(r'[^\w]','',str(text).lower())


def extract_editorial_photo(image,boxes,profile,caption='',language='en'):
    """Known source templates authorize edge cropping, never central text wiping.

    Scene labels are source-specific, narrowly bounded and kept untouched. A
    central publisher watermark or unknown lettering still blocks publication.
    """
    h,w=image.shape[:2]
    labels=getattr(boxes,'text_labels',{});confidence=getattr(boxes,'text_confidences',{})
    credits=re.compile(profile['credit_pattern'],re.I)
    zoom=bool(profile.get('allow_edge_zoom'))
    header_limit=float(profile.get('header_max_fraction',.20))
    allowed={_normal(text) for text in profile.get('scene_labels',[])}
    scene=[];corners=[];footer=[];headers=[]
    for raw in boxes:
        l,t,r,b=box=tuple(raw);text=str(labels.get(box,''))
        is_credit=bool(credits.search(text))
        if is_credit and t<h*.2 and r-l<w*.25 and b-t<h*.14:
            if r<=w*.28 or l>=w*.72:
                corners.append(box);continue
        configured_footer = profile.get('footer_start_fraction')
        if t>=h*.55 and (is_credit or r-l>=w*.25 or
                (configured_footer is not None and t>=h*float(configured_footer)) or zoom):
            footer.append(box);continue
        if (profile.get('header_fraction') or zoom) and b<=h*header_limit:
            headers.append(box);continue
        if (not is_credit and _normal(text) in allowed and confidence.get(box,0)>=.45
                and t<h*.52 and r-l<w*.50 and b-t<h*.09):
            scene.append(box);continue
        raise ValueError('Unknown source lettering or watermark overlaps the subject')
    rows=list(getattr(boxes,'suspected_rows',[]));marks=list(getattr(boxes,'suspected_marks',[]))
    for raw in rows+marks:
        l,t,r,b=box=tuple(raw)
        if t>=h*.55:
            footer.append(box);continue
        if (profile.get('header_fraction') or zoom) and b<=h*header_limit:
            headers.append(box);continue
        if any(a<=l and c>=r and y<=t and d>=b for a,y,c,d in corners):continue
        # A detector row can extend beyond individual recognized sign words.
        # It cannot grant arbitrary vertical space or excuse publisher marks.
        if any(abs(t-y)<h*.02 and abs(b-d)<h*.025 and r-l<=w*.50 for a,y,c,d in scene):continue
        raise ValueError('Unrecognized source typography overlaps the subject')
    top=round(h*profile.get('header_fraction',0)) if headers else 0
    if headers and zoom:
        padding=max(2,int(profile.get('header_crop_padding',max(12,round(h*.012)))))
        top=max(top,max(box[3] for box in headers)+padding)
    bottom=min((box[1]-max(12,round(h*.012)) for box in footer),default=h)
    if footer and profile.get('footer_fraction'):
        bottom=min(bottom,round(h*profile['footer_fraction']))
    if bottom-top<max(450,h*float(profile.get('min_retained_fraction',.42))) or (bottom-top)*w<350000:
        raise ValueError('Source graphics leave too little usable photograph')
    verified_credit=any(
            credits.search(str(labels.get(tuple(box),''))) and confidence.get(tuple(box),0)>=.55
            for box in boxes)
    # A repeated named subject in the paired caption can verify a publisher
    # frame when a stylized masthead or NEWS badge is unreadable. This is
    # enabled only for reviewed source templates, not arbitrary photos.
    caption_words={word.lower() for word in re.findall(r'\b\w{5,}\b',caption)}-{'officially','releases','season','november','october','music','awards','news','which','their','there'}
    named_anchor=zoom and any(confidence.get(tuple(box),0)>=.55 and
        caption_words.intersection(word.lower() for word in re.findall(r'\b\w{5,}\b',str(labels.get(tuple(box),''))))
        for box in boxes if tuple(box) in footer or tuple(box) in headers)
    if (top or bottom<h or corners) and not (verified_credit or named_anchor):
        raise ValueError('Source frame has no verified publisher anchor')
    # Detect faces in the full source; no recognized face may be cut by either
    # edge. The retained photo is a direct copy, with no inpainting or blur.
    if top or bottom<h:
        cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        scale=min(1,900/w);gray=cv2.resize(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),(round(w*scale),round(h*scale)))
        for fx,fy,fw,fh in cascade.detectMultiScale(gray,scaleFactor=1.15,minNeighbors=5,minSize=(35,35)):
            face_top=fy/scale;face_bottom=(fy+fh)/scale
            if face_top<bottom and face_bottom>top and (face_top<top or face_bottom>bottom):
                raise ValueError('Source frame would crop a face; choose another image')
    # Corner provenance is permitted only by the existing bounded original
    # credit rule. It is not promoted by the new crop geometry.
    provenance=_source_provenance_marks(boxes,h,w)
    if any(not _inside_source_mark(box,provenance) for box in corners):
        raise ValueError('Corner source logo is too large for this editorial template')
    return image[top:bottom].copy(),top,bottom
