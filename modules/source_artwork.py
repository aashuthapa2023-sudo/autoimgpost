"""Preserve a verified released film poster as the subject of a source post."""
import hashlib,re
from modules.llm_transformer import strip_source_caption_noise,headline_is_usable


def inspect_film_artwork(image,boxes,caption):
    source=strip_source_caption_noise(caption)
    announcement=re.compile(r'\b(?:first|new|official) poster for (.+?) has (?:dropped|been released)\b',re.I)
    named=announcement.search(source)
    if not named:raise ValueError('Source is not a named film-poster announcement')
    title=named.group(1).strip();h,w=image.shape[:2]
    if not .65<=w/h<=.90:raise ValueError('Film artwork needs its complete portrait format')
    norm=lambda text:set(re.findall(r'[a-z0-9]+',str(text).lower()))
    words=norm(title);labels=getattr(boxes,'text_labels',{});scores=getattr(boxes,'text_confidences',{})
    selected=[];recognized=set()
    for raw in boxes:
        box=tuple(raw);text=str(labels.get(box,''));tokens=norm(text)
        if tokens and tokens<=words and scores.get(box,0)>=.75 and box[1]>=h*.5:
            selected.append(list(box));recognized.update(tokens);continue
        if re.fullmatch(r'(?:A .+ (?:BEGINS|FILM)|A FILM BY [A-Z ]+|ONLY IN (?:THEATERS|CINEMAS)|'
                r'(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER) \d{1,2}|'
                r'EXPERIENCE IT IN|IMAX[\'’]?)',text,re.I):continue
        raise ValueError('Film artwork contains unverified lettering or a publisher watermark')
    if not selected or len(recognized&words)/max(1,len(words))<.9:
        raise ValueError('Film artwork title does not match its exact source caption')
    for box in list(getattr(boxes,'suspected_rows',[]))+list(getattr(boxes,'suspected_marks',[])):
        if not any(l<=box[0] and r>=box[2] and t<=box[1] and b>=box[3] for l,t,r,b in selected):
            raise ValueError('Film artwork contains an unexplained detector mark')
    if any(b-t<h*.035 or l<3 or r>w-3 or t<3 or b>h-3 for l,t,r,b in selected):
        raise ValueError('Film artwork title is clipped or too small')
    # This is the caption's complete event, not a second display headline.
    headline=re.split(r'(?<=[.!?])\s+',source)[0].rstrip('.')
    if not headline_is_usable(headline):raise ValueError('Film artwork announcement is incomplete')
    caption_facts=[]
    for fact in re.split(r'(?<=[.!?])\s+',source):
        if re.search(r'\bcoming (?:today|tomorrow|tonight)\b',fact,re.I):
            # Relative trailer teasers age independently of the poster release.
            # Drop the teaser clause, never leave fragments such as "trailer is".
            if not announcement.search(fact):continue
            fact=re.sub(r'\s+ahead of .+?\bcoming (?:today|tomorrow|tonight)\b.*$', '.',fact,flags=re.I)
            if re.search(r'\bcoming (?:today|tomorrow|tonight)\b',fact,re.I):continue
        if fact.strip():caption_facts.append(fact.strip())
    return {'headline':headline,'headline_bounds':selected,'source_image_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
            'intrinsic_artwork':True,'artwork_title':title,
            'caption_source':' '.join(caption_facts)}
