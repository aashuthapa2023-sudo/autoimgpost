"""Select complete source events, rather than a fixed number of caption words."""
import re
from modules.llm_transformer import check_source_grounding,headline_is_usable,split_clean_sentences


EVENT = re.compile(r'\b(?:reenters?|returns?|premieres?|releases?|released|hit|hits|reaches?|reached|'
    r'transforms?|opens?|heads?|submitted|praised|praises|trolled|recalls?|called|celebrates?|performs?|debuted|generated|died|got married|says?|reveals?|wore|wears?|axed|suspended|made|tells?|wrote|joins?|joined|sharpens?|demonstrates?|conducts?|trained|walked|'
    r'(?:is|are|was|were|has|have|will|may|might|could)\b.+|'
    r'(?:has|have) (?:officially )?(?:been (?:renewed|cancelled|canceled)|died|released|announced|confirmed)|'
    r'(?:is|are) (?:now )?(?:well )?(?:into production|in production|filming|on the way|canceling|cancelling)|'
    r'(?:will|may|might|could) (?:begin|return|release|train)|'
    r'(?:announced|confirmed|documented|filmed|recorded|saved|reported|observed|spotted|submitted)|'
    r'says? .+\b(?:saved|released|died|cancel|begin)\b)',re.I)
OPTIONAL_TAIL = re.compile(r',\s+(?:with\b|thanks to\b|including\b|bringing\b|starring\b|debuting\b|giving\b|and\b|fast-roping\b|rappelling\b|just a few weeks after\b)'
    r'|\s+and (?:considers?|considered|describes?|described|calls?|called)\b')
QUALIFIER = re.compile(r'\b(?:not|never|no(?!\.)|without|neither|cannot|may|might|could|possibly|'
    r'alleged|reportedly|unconfirmed|rumou?r|denied|false|incorrect|misleading|disputed|refuted|corrected|if|unless)\b',re.I)


def _tidy(value):
    value=re.sub(r'^\s*(?:BREAKING\s*:\s*)','',value,flags=re.I)
    value=re.sub(r'^[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\s]+|'
                 r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\s]+$','',value)
    return value.strip().rstrip('.!')


def _outside_quotes(text,position):
    quote=None;depth=0
    for i,c in enumerate(text[:position]):
        if c in '\"\'':
            if c=="'" and i and text[i-1].isalnum() and i+1<len(text) and text[i+1].isalnum():continue
            if quote==c:quote=None
            elif c=="'" and i and text[i-1].isalnum():continue
            elif quote is None:quote=c
        if quote is None:
            if c=='(':depth+=1
            elif c==')':depth=max(0,depth-1)
    return quote is None and depth==0


def _named_subject(text):
    # Anonymous sequel lines need their actual title before they can be a hook.
    if re.match(r'^(?:It|They|He|She|The (?:show|series|film|movie|season|company|store)|Season \d+)\b',text):return False
    if re.match(r'^(?:The only way|The most|There|These|This)\b',text,re.I):return False
    if re.match(r'''^(['"])(.+)\1\s+(?:is|are|was|were|has|have|will)\b''',text):return True
    from modules.content_quality import PERFORMERS,MILITARY_TERMS
    return bool(re.search(PERFORMERS+'|'+MILITARY_TERMS,text,re.I) or re.search(r'[A-Z][a-z]+(?:[ -][A-Z][a-z]+)|\b[A-Z]{2,}\b|\b(?:whale|orca|dolphin|octopus|shark|fish|isopod|anemone|sponge)\b',text))


def _has_predicate(text):
    return any(_outside_quotes(text,match.start()) for match in EVENT.finditer(text))


def complete_event_hooks(source,topic):
    """Return each headline with the complete source sentence proving it.

    Optional comma tails are removed only after a finite event clause. Dropped
    conditions, negations and uncertainty invalidate that cut. No word-count
    prefixes, OCR words, pronoun guessing or new entity names are synthesized.
    """
    facts=[fact.strip() for line in source.splitlines() for fact in split_clean_sentences(line) if fact.strip()]
    hooks=[];seen=set()
    def add(title,support,priority=1):
        title=_tidy(title)
        if (title in seen or not headline_is_usable(title,'en') or '?' in title
                or not check_source_grounding(title,' '.join(support),'en')):return
        # Industry vocabulary can sit in a separate source sentence. Retain one
        # distinct context fact rather than rejecting a musician's named chart
        # event or an aviation-maker's quantified statement as off-topic.
        from modules.content_quality import channel_accepts_post
        if topic and not channel_accepts_post({'content_topic':topic},{'caption':' '.join(support)}):
            context=[fact for fact in facts if fact not in support
                     and channel_accepts_post({'content_topic':topic},{'caption':fact})
                     and 4<=len(fact.split())<=30 and '?' not in fact]
            if context:support=support+[min(context,key=lambda fact:len(fact.split()))]
        seen.add(title);hooks.append((priority,len(hooks),title,support))
    for fact in facts:
        text=_tidy(fact)
        variants=[text]
        members=re.match(r'^(.+?) (?:were|was) among (?:the )?(?:stars|artists|performers) who (.+)',text)
        if members:variants.append(members.group(1)+' '+members.group(2))
        # Drop an introductory location/date/event phrase only at its comma.
        # Conditional "if/unless" framing and uncertainty cannot be discarded.
        preamble=re.match(r'^(?:During|In|On|At|Speaking at) [^,]+,\s+(.+)',text)
        if preamble and not QUALIFIER.search(text[:preamble.start(1)]):
            clause=preamble.group(1);variants.append(clause[0].upper()+clause[1:])
        for candidate in variants:
            if _named_subject(candidate) and _has_predicate(candidate):
                add(candidate,[fact])
                for cut in OPTIONAL_TAIL.finditer(candidate):
                    if not _outside_quotes(candidate,cut.start()):continue
                    clause=candidate[:cut.start()].rstrip(', ');tail=candidate[cut.start():]
                    if _has_predicate(clause) and not QUALIFIER.search(tail):add(clause,[fact],0)
        # Two named titles can replace a long descriptive list while retaining
        # its exact plural event clause, platform, date, and any qualification.
        pair=re.match(r'^(?:Two|2) (.+),\s+((?:are|have|will) .+)',text)
        if pair and not QUALIFIER.search(pair.group(1)):
            titles=re.findall(r"(?<!\w)'(.+?)'(?!\w)|\"([^\"]+)\"",pair.group(1))
            names=[next(part for part in item if part) for item in titles]
            if len(names)==2:
                add("'"+names[0]+"' and '"+names[1]+"' "+pair.group(2),[fact],0)
        # A reporting sentence explicitly supplies the speaker and a full that-
        # clause. Keep the attribution; remove only the reporting date/audience.
        report=re.search(r'\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,3}),? (?:told|said to) .+?,? that (.+)',text)
        if report and EVENT.search(report.group(2)):
            add(report.group(1)+' says '+report.group(2),[fact],0)
        # Preserve the named speaker, object and month from an explicit quote.
        quote=re.fullmatch(r'"From ([A-Z][a-z]+), we will begin (.+?)," ([A-Z][a-z]+) said',text)
        if quote:
            add(quote.group(3)+': '+quote.group(2)+' will begin in '+quote.group(1),[fact],0)
        request=re.search(r'\b([A-Z][a-z]+) (?:said|says) (?:that )?((?:the )?[A-Z][\w\'-]+(?: [A-Z][\w\'-]+){0,3}) '
            r'is seeking ([^,]+), as a [^,]+ investment, to (.+)',text)
        if request:
            # Preserve "seeking" and approximate amounts: a request is never
            # rewritten as awarded funding or a completed procurement.
            add(request.group(2)+' is seeking '+request.group(3)+' to '+request.group(4)+', '+request.group(1)+' says',[fact],0)
            subject=re.sub(r'^the\s+','',request.group(2),flags=re.I)
            add(subject+' seeks '+request.group(3)+' to '+request.group(4)+', '+request.group(1)+' says',[fact],0)
        # Temporal observation clauses refer to the same animal, not a vague
        # commentary sentence. Species equality prevents false-killer-whale
        # text from being silently turned into an orca.
        observation=re.fullmatch(r'An? (.+?) captured the attention of researchers in (\d{4}) when '
            r'(?:scientists|researchers) (documented|filmed|observed) (.+?) ((?:near|off) .+)',text)
        if topic=='ocean' and observation:
            species=lambda value:'false killer whale' if 'false killer whale' in value.lower() else (
                'killer whale' if re.search(r'\b(?:orca|killer whale)\b',value,re.I) else '')
            subject=re.sub(r'^(?:extraordinarily |extremely |very )?rare\s+','Rare ',observation.group(1),flags=re.I)
            if species(subject) and species(subject)==species(observation.group(4)):
                add(subject+' '+observation.group(3)+' '+observation.group(5)+' in '+observation.group(2),[fact],0)
    # An explicit named-show introduction can resolve the following season
    # announcement. It cannot resolve arbitrary "it/he/they" prose.
    intro=re.search(r'\b(?:Big week|Good news) for ([A-Z][A-Z :\'-]+) fans[!.]',source)
    if intro:
        for fact in facts:
            if re.match(r'^Season \d+ (?:returns|premieres)\b',fact):add(intro.group(1)+' '+_tidy(fact),[intro.group(0),fact],0)
    return [(title,support) for priority,index,title,support in sorted(hooks)]
