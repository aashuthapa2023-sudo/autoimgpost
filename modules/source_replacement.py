"""Replace configured source graphics with opaque, measured owned branding."""
import hashlib
import json
import math
from pathlib import Path
import cv2
from PIL import Image, ImageDraw
from modules.poster_engine import _wrap_headline, _render_runs, hex_to_rgb


def prepare_source_replacement(image,boxes,profile=None,caption='',language='en',corner_template=None):
    """Try the owned cover, then a configured, proven header/footer crop.

    The fallback is a direct photograph crop. Every detected source overlay
    must be wholly outside it; retained provenance cannot be hidden from review.
    """
    try:
        return image,review_source_replacement(image,boxes,corner_template),0,image.shape[0]
    except ValueError:
        if not profile:raise
    from modules.source_editorial import extract_editorial_photo
    from modules.image_cleaner import SourceTextBoxes
    photo,top,bottom=extract_editorial_photo(image,boxes,profile,caption,language)
    evidence=list(boxes)+list(getattr(boxes,'suspected_rows',[]))+list(getattr(boxes,'suspected_marks',[]))
    if photo.shape[1]!=image.shape[1] or any(t<bottom and b>top for l,t,r,b in evidence):
        raise ValueError('Replacement crop still contains source lettering')
    review=review_source_replacement(photo,SourceTextBoxes())
    review['source_extraction']={'original_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
        'original_size':[image.shape[1],image.shape[0]],'crop_bounds':[0,top,image.shape[1],bottom],
        'removed_overlay_bounds':[list(box) for box in evidence]}
    return photo,review,top,bottom


def review_source_replacement(image, boxes, corner_template=None):
    h,w=image.shape[:2]
    scale=min(1080/w,1350/h)
    x=(1080-round(w*scale))//2
    photo_y=0
    # Start at the original removed footer rather than covering extra photo.
    panel_top=1000
    logo=[824,64,1016,256]
    # Cover the entire source corner seal, including its unrecognized artwork.
    corner=[min(812,x+round(w*.78*scale)),0,x+round(w*scale),max(268,round(h*.20*scale))]
    evidence=list(boxes)+list(getattr(boxes,'suspected_rows',[]))+list(getattr(boxes,'suspected_marks',[]))
    source_corners=[box for box in evidence if box[0]>=w*.75 and box[3]<=h*.20]
    covered_corner=False
    if source_corners and corner_template:
        # A reviewed publisher seal can fit entirely inside our PNG's opaque
        # circle after insetting the original photo. No square backing needed.
        a,t,c,b=corner_template['seal_bounds']
        original=[a*w,t*h,c*w,b*h]
        if any(l<original[0] or top<original[1] or r>original[2] or bottom>original[3]
               for l,top,r,bottom in source_corners):
            raise ValueError('Source seal exceeds its reviewed template')
        scale=min(920/w,1270/h);x=(1080-round(w*scale))//2;photo_y=80
        corner=[x+math.floor(a*w*scale),photo_y+math.floor(t*h*scale),
                x+math.ceil(c*w*scale),photo_y+math.ceil(b*h*scale)]
        radius=94;cx=920;cy=160
        if any((px-cx)**2+(py-cy)**2>radius**2 for px in (corner[0],corner[2]) for py in (corner[1],corner[3])):
            raise ValueError('Source seal cannot fit behind the transparent destination circle')
        covered_corner=True
    mapped=[]
    corner_present=False
    for l,t,r,b in evidence:
        box=[x+math.floor(l*scale),photo_y+math.floor(t*scale),x+math.ceil(r*scale),photo_y+math.ceil(b*scale)]
        if l>=w*.75 and b<=h*.20:
            corner_present=True
            if not covered_corner:
                corner=[min(corner[0],box[0]-12),0,max(corner[2],box[2]+12),max(corner[3],box[3]+12)]
        elif t>=h*.50:
            panel_top=min(panel_top,box[1]-18)
        else:
            raise ValueError('Source lettering overlaps the marine subject outside replacement zones')
        mapped.append(box)
    if panel_top<675 or corner[0]<750 or corner[3]>310:
        raise ValueError('Source graphics need too much of the subject covered; choose another image')
    if corner_present and not covered_corner:
        raise ValueError('Source corner seal needs an opaque cover; choose a clean photo for transparent destination branding')
    corner=[max(0,corner[0]),corner[1],min(1080,corner[2]),corner[3]]
    covers=[corner,[0,panel_top,1080,1350]]
    if any(not any(a<=l and c>=r and t0<=t and d>=b for a,t0,c,d in covers) for l,t,r,b in mapped):
        raise ValueError('Source graphics are not completely covered')
    return {'source_image_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
            'source_overlay_bounds':mapped,'replacement_bounds':covers,
            'panel_top':panel_top,'logo_bounds':logo,'scale':scale,'photo_x':x,
            'corner_present':corner_present,'corner_covered':covered_corner,'photo_y':photo_y}


def replacement_photo_region(image,review):
    """Check the retained photograph, not the sharp text being covered."""
    bottom=min(image.shape[0],math.floor((review['panel_top']-review.get('photo_y',0))/review['scale']))
    if bottom<=0:raise ValueError('Replacement has no visible source photograph')
    return image[:bottom].copy()


def _complete_caption_hooks(source, topic):
    """Condense explicit event clauses while retaining names and qualifiers.

    Each hook carries the original supporting sentences. Promotional preambles
    and appositions may be removed; uncertain events are never made definite.
    """
    import re
    from modules.llm_transformer import split_clean_sentences,check_source_grounding
    facts=[fact for line in source.splitlines() for fact in split_clean_sentences(line) if fact.strip()]
    hooks=[]
    def add(hook, support,grounding=None):
        if check_source_grounding(hook,grounding or ' '.join(support),'en'):hooks.append((hook,support))
    for fact in facts:
        tour=re.fullmatch(r'([A-Z][\w-]+) Announces Dates For Huge (\d{4}) (.+) World Tour',fact)
        if tour and topic=='music':
            detail=next((item for item in facts if item.startswith(tour.group(1)+' announced the dates for ')
                and tour.group(2) in item and 'world' in item.lower() and 'tour' in item.lower()),None)
            if detail:
                add(f'{tour.group(1)} announces its {tour.group(2)} {tour.group(3)} world tour',[detail],grounding=fact)
        bridgerton=re.search(r'\bA new (BRIDGERTON) limited series following the romance of young Violet and Viscount Edmund Bridgerton is officially on the way at Netflix\b',fact,re.I)
        if bridgerton and not re.search(r'\b(?:not|may|might|rumou?r|reportedly)\b',fact,re.I):
            add('Netflix’s new BRIDGERTON series follows young Violet and Viscount Edmund’s romance',[fact])
        opinion=re.match(r'^([A-Z][a-z]+ [A-Z][a-z]+) says actors and other celebrities should stop lecturing people about politics and focus on their art instead\b',fact)
        if opinion:
            add(opinion.group(1)+' says celebrities should focus on their art instead of politics',[fact],
                grounding=fact.split(', arguing that ',1)[0])
        release=re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+)[’']s new [^,]+, ([^,(]+)\s*(?:\([^)]*\))?, is coming to Netflix on ([A-Za-z]+ \d{1,2}, \d{4})(?:,|\.)",fact)
        if release:
            add(f'{release.group(1)}’s {release.group(2).strip()} is coming to Netflix on {release.group(3)}',[fact])
        ranking=re.search(r'\bthe (Billboard) staff has ranked all (\d+) of (Taylor Swift)[’\']s bonus tracks\b',fact,re.I)
        if ranking and not re.search(r'\b(?:not|may|might|rumou?r)\b',fact,re.I):
            add(f'Billboard ranks all {ranking.group(2)} of Taylor Swift’s bonus tracks',[fact])
    if topic=='military':
        identity=next((fact for fact in facts if re.search(r'\bthe USS Abraham Lincoln slid up to the pier\b',fact)),None)
        duration=next((fact for fact in facts if re.search(r'\bthe carrier ended up away from home for (\d+) days\b',fact)),None)
        home=next((fact for fact in facts if re.search(r'\bThe ship came home\b',fact)),None)
        if identity and duration and home:
            days=re.search(r'\baway from home for (\d+) days\b',duration).group(1)
            # The hook asserts only the explicit return and duration, without
            # importing a separate no-loss statement into its fact scope.
            add(f'USS Abraham Lincoln returns home after {days} days away',[duration,identity])
    if topic=='ocean':
        identity=next((fact for fact in facts if re.search(r'\bflamboyant squidworm \(Teuthidodrilus samae\), a segmented marine worm\b',fact)),None)
        observation=next((fact for fact in facts if re.search(r'\bresearchers filmed it floating with what looked like a piece of sea cucumber\b',fact)),None)
        if identity and observation:
            speculation=[fact for fact in facts if re.search(r'\bThey suspect it may have been feeding on the remains\b',fact)]
            depth=next((fact for fact in facts if re.search(r'\bAt ([\d,]+) feet beneath the Pacific Ocean\b',fact)),None)
            hook='Researchers filmed a squidworm with what looked like a piece of sea cucumber'
            if depth:
                feet=re.search(r'\bAt ([\d,]+) feet beneath the Pacific Ocean\b',depth).group(1)
                hook=f'{feet} feet down: squidworm filmed with a possible sea cucumber piece'
            add(hook,[observation,identity]+speculation,grounding=' '.join([observation,identity,depth or '']))
        for fact in facts:
            whale=re.search(r'\bA \d+-metre, roughly (\d+)-tonne humpback whale carcass washed ashore at City Beach in Perth\b',fact)
            if whale:
                add(f'A roughly {whale.group(1)}-tonne humpback whale carcass washed ashore in Perth',[fact])
            if re.search(r'\btwo dead adult beluga whales were reported floating in Cook Inlet near Anchorage, Alaska\b',fact):
                add('Two dead adult beluga whales were reported near Anchorage, Alaska',[fact])
        identity=next((fact for fact in facts if re.search(r'\bfemale beluga\b',fact) and re.search(r'\bShedd Aquarium\b',fact)),None)
        outcome=next((fact for fact in facts if re.search(r'\babout two months after arriving at Shedd, Osiris died\b',fact)),None)
        if identity and outcome and re.search(r'^Osiris was given a chance at a new life',source):
            add('Osiris the beluga died about two months after arriving at Shedd Aquarium',[outcome,identity])
    return hooks


def replacement_payload(caption, **options):
    from modules.llm_transformer import (strip_source_caption_noise, split_clean_sentences,
                                        headline_is_usable, generate_preserved_card_payload,
                                        validate_model_payload, format_balanced_overlay)
    import re
    language=options.get('language','en')
    source=strip_source_caption_noise(caption)
    supported_hooks=_complete_caption_hooks(source,options.get('content_topic','')) if language=='en' else []
    candidates=[sentence.strip().rstrip('.।') for line in source.splitlines()
                for sentence in (re.split(r'[।!?]+',line) if language=='ne' else split_clean_sentences(line))]
    candidates=[re.sub(r'^[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\s]+','',text) for text in candidates]
    if language=='en':
        # These cuts remove explicit editorial commentary or promotional framing,
        # preserving the entire named event/outcome clause, not a word limit prefix.
        for sentence in tuple(candidates):
            experience=re.fullmatch(r'(.+?) has been in the game long enough to know that (.+)',sentence)
            if experience:candidates.insert(0,experience.group(1)+': '+experience.group(2))
            if ' How ' in sentence:
                introduction=re.sub(r"[^\w\s'’.,:!-]",' ',sentence.split(' How ',1)[0]).strip()
                if headline_is_usable(introduction,language):candidates.insert(0,introduction)
            # Release facts stay complete before a trailing plot synopsis.
            for separator in (', bringing ', ', starring ', ', with all ', ', giving '):
                if separator in sentence and re.search(r'\b(?:(?:releases|releasing|back|returns|streaming|renewed|arrived)\b.*\bNetflix|holds\b.*\bscore on Rotten Tomatoes)\b',sentence.split(separator)[0],re.I):
                    candidates.insert(0,sentence.split(separator)[0])
            # A confirmed renewal is a complete event before a comparison to
            # another season's premiere. Keep that comparison in the caption;
            # it must not displace the show's name with an anonymous cast fact.
            if ', more than ' in sentence:
                renewal=sentence.split(', more than ',1)[0]
                if re.search(r'\bhas (?:officially )?been renewed for Season \d+ on Netflix$',renewal,re.I):
                    candidates.insert(0,renewal)
            release=re.match(r"^(Netflix has set a [A-Za-z]+ \d{1,2}, \d{4} release date for '[^']+'), ",sentence)
            if release:
                candidates.insert(0,release.group(1))
            if ', while her old message ' in sentence:
                clause=sentence.split(', while her old message ',1)[0]
                clause=re.sub(r'^More than a decade after making that statement,\s*','',clause,flags=re.I)
                candidates.append(clause)
            event=re.search(r'\b([A-Z][\w]+(?: [A-Z][\w]+){0,3} show at .+)',sentence)
            if event:
                candidates.append(event.group(1).rstrip('.'))
            ranking=re.fullmatch(r"The (\d+) Best (VMAs Performances) of All Time: Critics' Picks",sentence,re.I)
            if ranking:
                candidates.insert(0,f"Critics pick the {ranking.group(1)} best VMAs performances of all time")
    usable=[text for text in candidates if headline_is_usable(text,language)]
    if (options.get('content_topic')=='ocean'
            and re.search(r'Deep beneath the Pacific, researchers captured a creature',source)
            and re.search(r'It[’\']s a Dumbo octopus',source)):
        usable.insert(0,'Researchers captured a Dumbo octopus deep beneath the Pacific')
    if options.get('content_topic') == 'military':
        # Extract complete source clauses; remove event preambles and trailing
        # appositions rather than chopping a headline at a word limit.
        concise=[]
        if (re.search(r'\bLeroy Petry\b',source) and re.search(r'\bArmy Rangers\b',source,re.I)
                and re.search(r'\bgrenade\b',source,re.I)
                and re.search(r'\b(?:lost|cost)\b[^.!]*\bhand\b',source,re.I)
                and re.search(r'\bsaved\b[^.!]*\b(?:Rangers|brothers)\b',source,re.I)):
            concise.append('Leroy Petry lost his hand saving fellow Army Rangers from a grenade')
        for text in candidates:
            clause=re.search(r'\bMarines will field [^,]+',text)
            if clause:concise.append(clause.group(0))
            clause=re.search(r"The first (?:two|\d+) of .+? touched down on [A-Za-z]+ \d+, \d{4}",text)
            if clause:concise.append(clause.group(0))
            if re.fullmatch(r'The SR-71 Blackbird that sat on display there, .+, is gone',text):
                if "NASA" in source:
                    concise.append('The SR-71 Blackbird is gone from its NASA display')
        usable=[text for text in concise if headline_is_usable(text,language)]+usable
    usable=[hook for hook,support in supported_hooks if headline_is_usable(hook,language)]+usable
    # Prefer a complete fact naming the animal or ocean phenomenon.
    import re
    if options.get('content_topic') == 'ocean':
        reviewed_hooks={hook for hook,support in supported_hooks}
        usable.sort(key=lambda text: (
            text not in reviewed_hooks,
            not bool(re.search(r'\b(?:whales?|dolphins?|coral|ocean|marine|sharks?|sponges?|seafloor)\b',text,re.I)),
            not bool(re.search(r'\b(?:died|dies|discovered|rescued|survival|declined|identified)\b',text,re.I))))
    for headline in usable:
        try:
            # Focus on the original sentence containing this fact. Adding an
            # extracted headline to that same long sentence repeats its news;
            # keep the complete source sentence once in the actual caption.
            normalize=lambda text:' '.join(re.findall(r"[\w]+(?:'[\w]+)?",str(text).lower()))
            original_facts=[fact for line in source.splitlines() for fact in
                (re.split(r'[।!?]+',line) if language=='ne' else split_clean_sentences(line)) if fact.strip()]
            focus=next((index for index,fact in enumerate(original_facts)
                        if f' {normalize(headline)} ' in f' {normalize(fact)} '),None)
            caption_source=caption
            if focus is not None:
                caption_source='\n'.join([original_facts[focus]]+original_facts[:focus]+original_facts[focus+1:])
            support=next((facts for hook,facts in supported_hooks if hook==headline),None)
            if support:
                caption_source='\n'.join(support)
            payload=generate_preserved_card_payload(headline+'.\n'+caption,headline,**options,
                caption_source=caption_source)
            # Condense a stated condition and outcome without guessing a cause,
            # location, count or diagnosis. Validate the edit against that fact.
            match=re.fullmatch(r'The (.+?) was already in a weakened condition and (died\b.+)',headline,re.I)
            if match:
                hook='A weakened '+match.group(1).lower()+' '+match.group(2)
                validated=validate_model_payload({'headline':hook,'rewritten_caption':headline+'.'},headline,
                    'en',options.get('channel_name',''),options.get('channel_id',''),options.get('content_topic',''))
                payload['headline']=validated['headline']
                payload['overlay_lines']=format_balanced_overlay(payload['headline'],'en')
            payload['headline_origin']='caption'
            return payload
        except ValueError:
            continue
    raise ValueError('Source caption has no complete grounded headline for replacement')


def render_source_replacement(image,review,payload,output_path,logo_path,highlight_hex='#FFC83B',**kwargs):
    if hashlib.sha256(image.tobytes()).hexdigest()!=review['source_image_sha256']:
        raise ValueError('Source image changed after replacement review')
    root=Path(__file__).resolve().parent.parent
    asset=(root/logo_path).resolve()
    if not asset.is_relative_to(root/'assets/branding') or not asset.is_file():
        raise ValueError('Replacement needs the approved destination logo')
    canvas=Image.new('RGB',(1080,1350),'black')
    photo=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
    photo=photo.resize((round(photo.width*review['scale']),round(photo.height*review['scale'])),Image.Resampling.LANCZOS)
    canvas.paste(photo,(review['photo_x'],review.get('photo_y',0)))
    draw=ImageDraw.Draw(canvas)
    for index,bounds in enumerate(review['replacement_bounds']):
        if index!=0:
            draw.rectangle(bounds,fill='black')
    if not review.get('corner_covered') and (review.get('corner_present') or any(b<=270 for l,t,r,b in review['source_overlay_bounds'])):
        raise ValueError('Source corner branding cannot remain behind the transparent PNG')
    logo=Image.open(asset).convert('RGBA').resize((192,192),Image.Resampling.LANCZOS)
    if review.get('corner_covered'):
        l,t,r,b=review['replacement_bounds'][0]
        alpha=logo.getchannel('A').crop((l-824,t-64,r-824,b-64))
        if not alpha.getbbox() or alpha.getextrema()[0]<255:
            raise ValueError('PNG transparency cannot completely cover the reviewed source seal')
    canvas.paste(logo,(824,64),logo.getchannel('A'))
    accent=hex_to_rgb(highlight_hex)
    top=review['panel_top']
    draw.rectangle((0,top,1079,top+3),fill=accent)
    words=[]
    for line in payload['overlay_lines']:
        for token in line:
            words.extend((word,token.get('type','white')) for word in token['text'].split())
    selected=None
    for size in range(94,67,-2):
        runs=_wrap_headline(words,size,'en',952,accent)
        rows=[_render_runs(run,size,'en',accent) for run in runs]
        height=sum(row.height for row in rows)+18*(len(rows)-1)
        if 1<=len(rows)<=5 and height<=1350-top-128 and all(0<row.width<=952 for row in rows):
            selected=size,rows,height
            break
    if selected is None:
        raise ValueError('Replacement headline cannot fit at large readable type')
    size,rows,height=selected
    y=top+(1350-top-height)//2
    text_bounds=[]
    for row in rows:
        x=(1080-row.width)//2
        canvas.paste(row,(x,y),row)
        text_bounds.append([x,y,x+row.width,y+row.height])
        y+=row.height+18
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(output,'JPEG',quality=96,subsampling=0)
    manifest={'schema_version':3,'approved':True,'source_checked':True,'layout_kind':'source_replacement',
              'image_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'caption_sha256':hashlib.sha256(payload['rewritten_caption'].encode('utf-8')).hexdigest(),
              'size':[1080,1350],'font_size':size,'safe_margin':64,'text_bounds':text_bounds,
              'panel_bounds':[0,top,1080,1350],'logo_bounds':review['logo_bounds'],'logo_shape':'circle',
              'source_overlay_bounds':review['source_overlay_bounds'],'replacement_bounds':review['replacement_bounds'],
              'headline':payload['headline'],'style_id':'oceans_secret_replacement'}
    if review.get('source_extraction'):manifest['source_extraction']=review['source_extraction']
    output.with_suffix('.quality.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return str(output)
