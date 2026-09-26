import os
import json
import re
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def build_system_prompt(language: str = "en", channel_name: str = "") -> str:
    target_str = f" for '{channel_name}'" if channel_name else ""
    if language == "ne":
        return f"""तपाईं एक वरिष्ठ नेपाली पत्रकार र समाचार सम्पादक हुनुहुन्छ जो फेसबुकका लागि दृश्य रूपमा प्रभावकारी, तथ्यमा आधारित नेपाली समाचार लेख र पोस्टर शीर्षक तयार गर्नुहुन्छ{target_str}।
Facebook Distribution Guidelines को पूर्ण पालना गर्नुहोस्: कुनै क्लिकबेट छैन, कुनै अतिरञ्जना छैन, र कुनै कमेन्ट बेट (comment bait) छैन।
यदि यो समाचार अन्य कुनै पेज वा च्यानलमा पनि पोस्ट भएको छ भने, यो च्यानल{target_str} को लागि नयाँ टेक्स्ट ओभरले र नयाँ भेरियसनको क्याप्सन बनाउनुहोस्।

अति महत्त्वपूर्ण नियमहरू:
१. ओभरले हेडलाइन्स (STRONG HOOK LINE + MAIN HEADLINE, strictly 2 lines, 2-3 words per line):
   - लाइन १: STRONG HOOK LINE (मुख्य विषय वा पात्र, २ देखि ३ शब्द)
   - लाइन २: MAIN HEADLINE (मुख्य घटना वा नतिजा, २ देखि ३ शब्द)
   - अर्थपूर्ण ओभरले: ओभरले उक्त समाचारको मुख्य विषयसँग प्रत्यक्ष सम्बन्धित र अर्थपूर्ण हुनुपर्छ। "आज आईतवार", "विशेष कभरेज", "ताजा समाचार", "महत्वपूर्ण अपडेट" जस्ता निरर्थक शब्दहरू प्रयोग गर्न पाइने छैन।
   - अनिवार्य नियम: ओभरलेको दोस्रो लाइनको अन्तिम शब्दको पछाडि अनिवार्य रूपमा तीनवटा थोप्लो (...) राख्नुहोस् (e.g. "जिल्लाबाटै...", "शव फेला...", "कडा चेतावनी...")।
   - हाइलाइटिङ नियम: मुख्य विषय वा नामलाई HIGHLIGHT गर्नुहोस्।
     टोकन विभाजन: [{{"text": "पहिलो शब्द ", "type": "white"}}, {{"text": "मुख्य विषय...", "type": "highlight"}}]

२. फेसबुक क्याप्सन (Authentic Source Facts Only, No Fake Boilerplate):
   - स्रोतबाट प्राप्त वास्तविक तथ्य मात्र प्रयोग गर्नुहोस्। काल्पनिक वा नक्कली अनुच्छेदहरू (जस्तै 'सम्बन्धित निकायले अध्ययन सुरु गर्यो', 'दीर्घकालीन सकारात्मक प्रभाव पार्नेछ') मनगढन्ते बनाउन पाइने छैन।
   - दोहोरो वाक्य पूर्ण निषेध (NO DUPLICATE LINES): क्याप्सनमा एउटै वाक्य वा लाइन दुई पटक दोहोर्याउन पाइने छैन। शीर्षक र पहिलो अनुच्छेद एउटै हुनुहुँदैन।
   - यदि स्रोत पोस्ट छोटो वा शुभकामना सन्देश हो भने त्यसलाई अनावश्यक रूपमा नक्कली अनुच्छेद थपेर लामो नबनाउनुहोस्।
   - ह्यासट्यागहरू: ४-६ वटा सान्दर्भिक ह्यासट्यागहरू अन्त्यमा राख्नुहोस्।

Return strictly JSON:
{{
  "overlay_lines": [
    [{{"text": "हुक वाक्यांश ", "type": "white"}}, {{"text": "नयाँ निर्णय", "type": "highlight"}}],
    [{{"text": "मुख्य घटना ", "type": "white"}}, {{"text": "जिल्लाबाटै...", "type": "highlight"}}]
  ],
  "rewritten_caption": "सफा र तथ्यपरक क्याप्सन (कुनै दोहोरो लाइन छैन)...\\n\\n#NepalSpeaks #NepaliNews #NepalUpdates"
}}"""

    return f"""You are a senior entertainment journalist and news editor crafting visually impactful, deeply detailed social media news articles for Facebook{target_str}.
Strictly adhere to Facebook Distribution Guidelines: NO clickbait, NO sensationalism, and ABSOLUTELY NO comment bait or engagement bait.
If this news item is syndicated across multiple media pages, craft a fresh, unique angle, new text overlay, and a distinct variation of the caption tailored specifically{target_str}.

CRITICAL RULES:
1. OVERLAY HEADLINES (STRONG HOOK LINE + MAIN HEADLINE, strictly 2 lines, 2-3 words per line):
   - Line 1: STRONG HOOK LINE (Core subject or key entity, 2-3 words)
   - Line 2: MAIN HEADLINE (Core action, milestone or outcome, 2-3 words)
   - MEANINGFUL OVERLAY: Must directly describe this specific story/show/person. NEVER use generic filler words like "Breaking News", "Special Coverage", "Today Update".
   - Split each line into tokens: [{{"text": "...", "type": "white"}}, {{"text": "...", "type": "highlight"}}].

2. REWRITTEN CAPTION (Authentic Source Facts Only, NO Repetition):
   - Extract and convey the ACTUAL factual substance and meaning from the source.
   - Absolutely NO duplicate lines: The headline and first body sentence must NEVER repeat the same line twice.
   - Absolutely NO generic fake filler or fabricated paragraphs (e.g. "Behind the scenes...", "Industry observers note...").
   - If the source is concise, keep it clean and concise. Do NOT pad with hallucinated boilerplate.
   - HASHTAGS: 4-6 targeted, high-traffic entertainment hashtags at the end.

Return strictly JSON:
{{
  "overlay_lines": [
    [{{"text": "STRONG HOOK ", "type": "white"}}, {{"text": "KEY ENTITY", "type": "highlight"}}],
    [{{"text": "MAIN HEADLINE ", "type": "white"}}, {{"text": "KEY OUTCOME", "type": "highlight"}}]
  ],
  "rewritten_caption": "Clean authentic post body with no repeated lines...\\n\\n#Hashtag1 #Hashtag2 #Hashtag3 #Hashtag4"
}}"""

TRAILING_STOPWORDS = {
    'THE', 'A', 'AN', 'OF', 'IN', 'ON', 'AT', 'TO', 'FOR', 'WITH', 'AND', 'OR',
    'BUT', 'BY', 'FROM', 'AS', 'ABOUT', 'INTO', 'HAS', 'HAVE', 'HAD', 'IS', 'ARE',
    'WAS', 'WERE', 'BE', 'BEEN', 'HER', 'HIS', 'THEIR', 'ITS', 'THIS', 'THAT',
    'WHO', 'WHICH', 'WHERE', 'WHEN', 'WHY', 'HOW', 'ALL', 'ANOTHER', 'SOME', 'ANY',
    'TODAY', 'AGO', 'TIME', 'YEARS', 'OLD', 'NO', 'NOT', 'SO', 'CAN', 'COULD', 'WOULD',
    'WILL', 'SHE', 'HE', 'IT', 'THEY', 'WE', 'YOU', 'I', 'AFTER', 'BEFORE', 'WHILE', 'DURING',
    'SUCH', 'THAN', 'THEN', 'OVER', 'UNDER', 'MORE', 'LESS'
}

HIGH_THEME_KEYWORDS = {
    'EMMY', 'EMMYS', 'OSCAR', 'OSCARS', 'GRAMMY', 'AWARD', 'AWARDS', 'NETFLIX', 'HBO',
    'DISNEY', 'MARVEL', 'DC', 'CANCELLED', 'RENEWED', 'PREMIERED', 'RETURNS', 'RETURNING',
    'FINALE', 'TRAILER', 'TEASER', 'CASTING', 'CONFIRMED', 'RECORD', 'HISTORIC',
    'MOVIE', 'SERIES', 'SEASON', 'SEQUEL', 'REBOOT', 'STAR', 'STARS'
}

NEPALI_STOPWORDS = {
    'र', 'मा', 'को', 'का', 'की', 'ले', 'लाई', 'बाट', 'छ', 'छन्', 'थियो', 'थिए',
    'भयो', 'भए', 'हुने', 'गरेको', 'गर्ने', 'भने', 'तर', 'पनि', 'यो', 'त्यो',
    'यी', 'ती', 'एक', 'दुई', 'भएको', 'गरेका', 'रहेको', 'रहेका', 'हुन्', 'हुन्थ्यो',
    'भनेर', 'भनी', 'बारे', 'साथै', 'भित्र', 'पछि', 'अघि', 'अनुसार', 'समेत', 'तथा',
    'हुन', 'हुनु', 'गर्न', 'दिन', 'लिने', 'लिन', 'आफ्नो', 'आफू', 'सबै', 'अन्य', 'अब'
}

HIGH_THEME_NEPALI_KEYWORDS = {
    'बालेन', 'सरकार', 'सरकारको', 'निर्णय', 'नागरिकता', 'नागरिकताको', 'प्रतिलिपि',
    'प्रशासन', 'कार्यालय', 'अदालत', 'फैसला', 'निर्वाचन', 'संसद', 'विधेयक',
    'प्रधानमन्त्री', 'मन्त्री', 'काठमाडौं', 'नेपाल', 'नयाँ', 'नियम', 'राहत',
    'सहज', 'व्यवस्था', 'बजेट', 'शुल्क', 'सडक', 'यातायात', 'विमान', 'दुर्घटना',
    'खेलकुद', 'क्रिकेट', 'फुटबल', 'जीत', 'रेकर्ड', 'पुरस्कार', 'ऐतिहासिक'
}

def is_devanagari_text(text: str) -> bool:
    return any('\u0900' <= char <= '\u097F' for char in str(text or ""))

def format_nepali_thematic_tokens(words: list) -> list:
    if not words:
        return []
    if len(words) == 1:
        return [{"text": words[0], "type": "highlight"}]

    scores = []
    for w in words:
        clean = re.sub(r'[^\u0900-\u097F]', '', w)
        if not clean or clean in NEPALI_STOPWORDS:
            scores.append(0.0)
        elif clean in HIGH_THEME_NEPALI_KEYWORDS:
            scores.append(6.0)
        else:
            scores.append(1.0 + len(clean) * 0.4)

    max_score = max(scores)
    if max_score <= 1.0:
        best_idx = len(words) - 1
    else:
        best_idx = scores.index(max_score)

    start_hl = best_idx
    end_hl = best_idx + 1

    while end_hl < len(words) and scores[end_hl] >= 4.0:
        end_hl += 1
    while start_hl > 0 and scores[start_hl - 1] >= 4.0:
        start_hl -= 1

    tokens = []
    if start_hl > 0:
        tokens.append({"text": " ".join(words[:start_hl]) + " ", "type": "white"})
    hl_str = " ".join(words[start_hl:end_hl])
    if end_hl < len(words):
        hl_str += " "
    tokens.append({"text": hl_str, "type": "highlight"})
    if end_hl < len(words):
        tokens.append({"text": " ".join(words[end_hl:]), "type": "white"})
    return tokens

def ensure_nepali_overlay_ellipsis(overlay_lines: list) -> list:
    """Ensures that for all Nepali news pages, the text overlay ending has '...' appended."""
    if not overlay_lines:
        return overlay_lines
    last_line = overlay_lines[-1]
    if last_line:
        last_tok = last_line[-1]
        if isinstance(last_tok, dict) and "text" in last_tok:
            t = re.sub(r'[।!?.…—\-]+$', '', str(last_tok["text"])).rstrip()
            last_tok["text"] = t + "..."
        elif isinstance(last_tok, str):
            t = re.sub(r'[।!?.…—\-]+$', '', str(last_tok)).rstrip()
            last_line[-1] = t + "..."
    return overlay_lines

NEPALI_HANGING_WORDS = {
    'र', 'मा', 'को', 'का', 'की', 'ले', 'लाई', 'बाट', 'तथा', 'वा', 'समेत',
    'पनि', 'भने', 'अब', 'छ', 'छन्', 'भएको', 'गरेको', 'गर्ने', 'हुने', 'दिएका', 'परेका', 'बनेका', 'भएका'
}

NEPALI_BANNED_OVERLAY_WORDS = {
    'आज', 'आजको', 'आइतबार', 'आईतवार', 'आइतवार', 'सोमबार', 'सोमवार', 'मंगलबार', 'मङ्गलवार',
    'बुधबार', 'बुधवार', 'बिहीबार', 'बिहिवार', 'शुक्रबार', 'शुक्रवार', 'शनिबार', 'शनिवार',
    'सुप्रभात', 'शुभप्रभात', 'नमस्ते', 'नमस्कार', 'विशेष', 'कभरेज', 'अपडेट', 'ताजा', 'समाचार',
    'महत्वपूर्ण', 'तथा', 'र', 'अब', 'भने', 'को', 'का', 'की', 'ले', 'लाई', 'बाट', 'छ', 'छन्',
    'समेत', 'पनि', 'यो', 'त्यो', 'यी', 'ती', 'एक', 'दुई', 'भएको', 'हुने', 'गरेको', 'भनेर',
    'नयाँ', 'कडा', 'जारी', 'गर्दै', 'गरेका', 'रहेको', 'रहेका'
}

DEITY_PATTERNS = [
    (r'(?:सरस्वती|सरस्वतीमाता|सरस्वतीमाताको)', 'सरस्वती माताको', 'शुभ आशिर्वाद'),
    (r'(?:पशुपति|पशुपतिनाथ|महादेव|शिव|भोलेनाथ)', 'पशुपतिनाथको', 'कृपा र आशिर्वाद'),
    (r'(?:गणेश|गणेशजी|गणपति)', 'भगवान गणेशको', 'शुभ आशिर्वाद'),
    (r'(?:कृष्ण|श्रीकृष्ण|राधाकृष्ण)', 'भगवान श्रीकृष्णको', 'दिव्य आशिर्वाद'),
    (r'(?:राम|श्रीराम|सीताराम)', 'प्रभु श्रीरामको', 'शुभ कृपा'),
    (r'(?:दुर्गा|भवानी|काली|लक्ष्मी)', 'माता दुर्गाको', 'शुभ आशिर्वाद'),
    (r'(?:बुद्ध|भगवान बुद्ध|गौतम बुद्ध)', 'भगवान बुद्धको', 'शान्ति सन्देश'),
]

def clean_and_deduplicate_source_caption(raw_caption: str, language: str = "en", channel_name: str = "", channel_id: str = "") -> str:
    """
    Extracts the clean, authentic caption directly from original source post without fake boilerplate:
    - Strips URLs, promotional spam, 'like our page', and external links.
    - Strictly prevents repeating the same line or sentence twice in the post.
    - Preserves all real facts and sentences from the source.
    - Appends clean channel branding hashtags.
    """
    if not raw_caption:
        return ""

    # Normalize Windows-1252 / smart punctuation
    text = raw_caption.replace('\x91', "'").replace('\x92', "'").replace('\x93', '"').replace('\x94', '"')
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')

    # Remove complete Markdown links first, including shortened URL labels.
    text = re.sub(r'\[[^\]]*\]\(https?://[^\s]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:https?://|www\.)\S+|\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?', '', text, flags=re.IGNORECASE)
    text = text.strip().strip(' {}:*')

    # Remove fake boilerplate if present
    fake_phrases = [
        r'यस विषयमा सम्बन्धित निकाय तथा सरोकारवालाहरूले आवश्यक अध्ययन.*',
        r'यस विकासक्रमले दीर्घकालीन रूपमा सकारात्मक प्रभाव पार्ने.*',
        r'The details behind the announcement demonstrate significant creative investment.*',
        r'Verified production and distribution documentation have been logged.*',
        r'INDUSTRY\s+REPORTING\s*&?\s*UPDATES.*',
        r'According to verified production details,\s*',
    ]
    for fp in fake_phrases:
        text = re.sub(fp, '', text, flags=re.IGNORECASE)

    raw_lines = text.splitlines()
    clean_lines = []
    seen_normalized = []

    promo_patterns = [
        r'https?:\S+',
        r'(?:थप\s+(?:समाचार|जानकारी|विवरण)|हाम्रो\s+(?:फेसबुक\s+)?पेज|भिडियो\s+हेर्नुहोस्|लिंक\s+कमेन्टमा|तस्बिर\s*:|फोटो\s*:|साभार\s*:).*',
        r'(?:Follow\s+(?:our\s+page|us)|Subscribe\s+to|Link\s+in\s+(?:bio|comment)|Click\s+here|Read\s+more|Photo\s*:).*',
        r'^[#@\s\-_=]+$',
        r'^\s*(?:#[\w\u0900-\u097F]+\s*)+$'
    ]

    for line in raw_lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Ignore lines that are purely hashtags
        if re.match(r'^\s*(?:#[\w\u0900-\u097F]+\s*)+$', line_clean):
            continue

        # Strip promo patterns
        for pat in promo_patterns:
            line_clean = re.sub(pat, '', line_clean, flags=re.IGNORECASE).strip()

        if not line_clean or len(line_clean) < 3:
            continue

        # Ignore if line became only hashtags
        if re.match(r'^\s*(?:#[\w\u0900-\u097F]+\s*)+$', line_clean):
            continue

        # Normalize line to detect duplicates (strip punctuation, dandas, emojis, spaces)
        norm = re.sub(r'[।॥\.,;:!?\'"()\[\]{}<>\-—_~/\\|#*&^%$@+=📢🇳🇵🚨⚡🌍✈️🎬📺🌟🎩🐘🏏]', '', line_clean)
        norm = re.sub(r'[^\w\u0900-\u097F]', '', norm.lower())
        norm = re.sub(r'[।॥]', '', norm)
        if not norm or len(norm) < 4:
            continue

        # Check against already seen lines (prevent repeating same line twice)
        is_dup = False
        for prev_norm in seen_normalized:
            if norm == prev_norm:
                is_dup = True
                break
            # Check high similarity or substring containment
            if len(prev_norm) > 10 and len(norm) > 10:
                if norm in prev_norm or prev_norm in norm:
                    is_dup = True
                    break

        if not is_dup:
            clean_lines.append(line_clean)
            seen_normalized.append(norm)

    # Keep a short standalone news brief; never restore discarded raw links.
    sentences = re.split(r'(?<=[.!?।])\s+|\n+', ' '.join(clean_lines))
    brief = []
    for sentence in sentences:
        sentence = sentence.strip(' {}:*')
        if not sentence or sentence.endswith('?'):
            continue
        if re.search(r'\b(?:find out|read the full|tap (?:here|the link)|what you need to know|link below)\b', sentence, re.IGNORECASE):
            continue
        if len((' '.join(brief + [sentence])).split()) > 80:
            break
        if sentence not in brief:
            brief.append(sentence)
        if len(brief) == 3:
            break
    body_text = ' '.join(brief)
    if not body_text:
        return ''

    # Clean channel hashtags
    ch_clean = re.sub(r'[^a-zA-Z0-9\u0900-\u097F]', '', str(channel_name or channel_id or ""))
    is_nepali = (language == "ne" or any('\u0900' <= c <= '\u097F' for c in body_text))

    if is_nepali:
        tag1 = f"#{ch_clean}" if ch_clean else "#NepalSpeaks"
        hashtags = f"{tag1} #NepaliNews #NepalUpdates #NepalNews"
    else:
        tag1 = f"#{ch_clean}" if ch_clean else "#DailyNetflix"
        hashtags = f"{tag1} #Entertainment #StreamingNews"

    return f"{body_text}\n\n{hashtags}"

def extract_meaningful_nepali_overlay(raw_caption: str) -> list:
    """Preserve a complete source headline, including its subject and action."""
    cleaned = clean_and_deduplicate_source_caption(raw_caption, language="ne")
    body = cleaned.split("\n\n")[0]
    sentences = [s.strip() for s in re.split(r"[।!?\n]+", body) if s.strip()]
    # Never turn long stories into four unrelated keywords or invent filler.
    # Select a complete source sentence that can remain legible on the poster.
    headline = next((s for s in sentences if 2 <= len(s.split()) <= 24 and len(s) <= 240), "")
    if not headline:
        raise ValueError("No complete, readable Nepali headline available")
    words = headline.split()
    line_count = 2 if len(words) <= 10 and len(headline) <= 100 else 3
    lines = []
    for remaining_lines in range(line_count, 0, -1):
        if remaining_lines == 1:
            take = len(words)
        else:
            target = len(" ".join(words)) / remaining_lines
            take = min(range(1, len(words) - remaining_lines + 2),
                       key=lambda n: abs(len(" ".join(words[:n])) - target))
        lines.append(format_nepali_thematic_tokens(words[:take]))
        words = words[take:]
    return ensure_nepali_overlay_ellipsis(lines)


def nepali_heuristic_payload(raw_caption: str, channel_name: str = "", channel_id: str = "") -> dict:
    overlay_lines = extract_meaningful_nepali_overlay(raw_caption)
    rewritten = clean_and_deduplicate_source_caption(raw_caption, language="ne", channel_name=channel_name, channel_id=channel_id)
    if not rewritten:
        raise ValueError('Source has no usable news facts after removing links and teasers')
    return {
        "overlay_lines": overlay_lines,
        "rewritten_caption": sanitize_caption(rewritten, channel_name=channel_name, channel_id=channel_id)
    }

def analyze_and_rewrite_nepali_caption(raw_caption: str, channel_name: str = "", channel_id: str = "") -> str:
    """Extracts authentic source caption cleanly, preventing duplicate lines and fake boilerplate."""
    return clean_and_deduplicate_source_caption(raw_caption, language="ne", channel_name=channel_name, channel_id=channel_id)

def _is_capitalized_in_raw(word: str, raw_sentence: str) -> bool:
    clean = word.strip('.,;:!?\'"()[]')
    m = re.search(r'\b' + re.escape(clean) + r'\b', raw_sentence, re.IGNORECASE)
    if m:
        raw_token = m.group(0)
        if raw_token[0].isupper() and m.start() > 0:
            return True
        elif raw_token.isupper() and len(raw_token) > 1:
            return True
    return False

def _score_token(tok: str, raw_sentence: str) -> float:
    clean = tok.strip('.,;:!?\'"()[]').upper()
    if not clean or clean in TRAILING_STOPWORDS:
        return 0.0
    score = 1.0
    if re.match(r'^\d+$', clean) or clean in ['FIRST', 'SECOND', 'THIRD', 'FOURTH']:
        score += 3.5
    if clean in HIGH_THEME_KEYWORDS:
        score += 5.0
    if _is_capitalized_in_raw(tok, raw_sentence):
        score += 4.0
    return score

def extract_thematic_line_tokens(words: list, raw_sentence: str) -> list:
    """
    Analyzes a line of words and highlights the key thematic entity (can be anywhere in the line).
    """
    if not words:
        return []
    if len(words) == 1:
        return [{"text": words[0].upper(), "type": "highlight"}]

    scores = [_score_token(w, raw_sentence) for w in words]
    max_score = max(scores)
    
    if max_score <= 1.0:
        best_idx = max(range(len(words)), key=lambda i: len(words[i]) if words[i].upper() not in TRAILING_STOPWORDS else 0)
    else:
        best_idx = scores.index(max_score)
        
    start_hl = best_idx
    end_hl = best_idx + 1
    
    # Expand forward if contiguous high theme
    while end_hl < len(words) and scores[end_hl] >= 3.0:
        end_hl += 1
    # Expand backward if contiguous high theme
    while start_hl > 0 and scores[start_hl - 1] >= 3.0:
        start_hl -= 1

    tokens = []
    # Prefix (white)
    if start_hl > 0:
        prefix_str = " ".join(words[:start_hl]).upper() + " "
        tokens.append({"text": prefix_str, "type": "white"})
        
    # Highlighted theme (proper noun, award, milestone, or key verb)
    hl_str = " ".join(words[start_hl:end_hl]).upper()
    if end_hl < len(words):
        hl_str += " "
    tokens.append({"text": hl_str, "type": "highlight"})
    
    # Suffix (white)
    if end_hl < len(words):
        suffix_str = " ".join(words[end_hl:]).upper()
        tokens.append({"text": suffix_str, "type": "white"})
        
    return tokens

HANGING_WORDS = {'THE', 'A', 'AN', 'OF', 'IN', 'ON', 'AT', 'TO', 'FOR', 'WITH', 'AND', 'OR', 'BUT', 'BY', 'AS', 'ABOUT', 'OVER', 'FROM', 'IS', 'ARE', 'WAS', 'WERE', 'BEEN'}

def clean_factual_clause(sentence: str) -> str:
    """Extracts a grammatically complete, natural headline clause without mid-word or mid-name truncation."""
    s = re.sub(r'https?:\S+', '', sentence).strip()
    s = re.sub(r'^(?:[A-Z\s]+:\s*)+', '', s)
    s = re.sub(r'[\(\[]\s*(?:via|source|credit)[^\)\]]*[\)\]]', '', s, flags=re.IGNORECASE).strip()
    s = s.rstrip('.,;:- ')

    # Check for natural subclause breaks (e.g. ", a ", ", an ", " - ", ", which ")
    parts = re.split(r'[,;]\s+(?:a|an|the|which|who|featuring|starring|directed)\s+', s, flags=re.IGNORECASE)
    if len(parts) > 1 and len(parts[0].split()) >= 5:
        candidate = parts[0].strip()
    else:
        # Check dash break
        dash_parts = re.split(r'\s+[-—]\s+', s)
        if len(dash_parts) > 1 and len(dash_parts[0].split()) >= 5:
            candidate = dash_parts[0].strip()
        else:
            candidate = s

    words = candidate.split()
    if len(words) > 13:
        words = words[:12]

    # Clean any trailing hanging words from end of headline
    while words and words[-1].rstrip('.,:;!?').upper() in HANGING_WORDS:
        words.pop()

    return " ".join(words)

def format_factual_overlay(sentence: str) -> list:
    """
    Takes a factual sentence and splits it into 2-3 complete, balanced lines.
    NEVER cuts off mid-sentence or mid-name. Never leaves hanging prepositions.
    Analyzes the entire sentence to highlight the main theme in each line.
    """
    cleaned_clause = clean_factual_clause(sentence)
    words = cleaned_clause.split()
    if not words:
        return []

    N = len(words)
    if N <= 5:
        num_lines = 1
    elif N <= 10:
        num_lines = 2
    else:
        num_lines = 3

    # Calculate balanced distribution across lines
    base = N // num_lines
    rem = N % num_lines
    sizes = [base + (1 if i < rem else 0) for i in range(num_lines)]

    lines_words = []
    idx = 0
    for sz in sizes:
        lines_words.append(words[idx:idx + sz])
        idx += sz

    # Shift hanging prepositions / articles forward for grammatical cohesion
    for i in range(len(lines_words) - 1):
        if lines_words[i] and len(lines_words[i]) > 1:
            last_word_clean = lines_words[i][-1].rstrip('.,:;!?').upper()
            if last_word_clean in HANGING_WORDS:
                moved = lines_words[i].pop()
                lines_words[i + 1].insert(0, moved)

    # Clean hanging words from the very last line
    if lines_words and lines_words[-1]:
        while lines_words[-1] and lines_words[-1][-1].rstrip('.,:;!?').upper() in HANGING_WORDS:
            lines_words[-1].pop()

    res = []
    for lw in lines_words:
        if not lw:
            continue
        line_tokens = extract_thematic_line_tokens(lw, cleaned_clause)
        res.append(line_tokens)
    return res

def split_clean_sentences(text: str) -> list:
    cleaned = re.sub(r'https?:\S+', '', str(text or "")).strip()
    # Protect common abbreviations and numbers from premature splitting
    protected = re.sub(
        r'\b(No|Mr|Mrs|Ms|Dr|Prof|St|vs|Vol|Pt|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|U\.S)\.\s+',
        r'\1_DOT_ ',
        cleaned
    )
    raw_sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', protected) if len(s.strip()) > 8]
    return [s.replace('_DOT_', '.') for s in raw_sents]

def analyze_and_rewrite_english_caption(raw_caption: str, channel_name: str = "", channel_id: str = "") -> str:
    """Extracts authentic source caption cleanly, preventing duplicate lines and fake boilerplate."""
    return clean_and_deduplicate_source_caption(raw_caption, language="en", channel_name=channel_name, channel_id=channel_id)

def smart_heuristic_headline(raw_caption: str, language: str = "en", channel_name: str = "", channel_id: str = "") -> dict:
    """Extracts factual news subject and synthesizes an extensive, deeply detailed multi-paragraph news report."""
    if language == "ne" or is_devanagari_text(raw_caption):
        return nepali_heuristic_payload(raw_caption, channel_name=channel_name, channel_id=channel_id)

    # Normalize Windows-1252 and unicode smart quotes to clean ASCII
    normalized = raw_caption.replace('\x91', "'").replace('\x92', "'").replace('\x93', '"').replace('\x94', '"')
    normalized = normalized.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    cleaned = re.sub(r'https?:\S+', '', normalized).strip()
    sentences = split_clean_sentences(cleaned)
    first_sent = sentences[0] if sentences else cleaned[:120]
    upper = cleaned.upper()

    overlay_lines = format_factual_overlay(first_sent)
    rewritten = analyze_and_rewrite_english_caption(raw_caption, channel_name=channel_name, channel_id=channel_id)

    return {
        "overlay_lines": overlay_lines,
        "rewritten_caption": sanitize_caption(rewritten, channel_name=channel_name, channel_id=channel_id)
    }

def sanitize_caption(caption: str, channel_name: str = "", channel_id: str = "") -> str:
    """
    Universally sanitizes social media captions:
    - Strips robotic boilerplate headers ('INDUSTRY REPORTING & UPDATES', etc.)
    - Removes hallucinated filler paragraphs
    - Strictly prevents repeating the same line or sentence twice
    - Preserves authentic text from the original source with clean channel hashtags
    """
    if not caption:
        return ""
    return clean_and_deduplicate_source_caption(caption, channel_name=channel_name, channel_id=channel_id)

def generate_social_payload(raw_caption: str, language: str = "en", channel_name: str = "", channel_id: str = "") -> dict:
    effective_lang = "ne" if language == "ne" or is_devanagari_text(raw_caption) else (language or "en")

    # For Nepal Speaks / Nepali channels, strictly follow user requirement:
    # Use source's exact caption & exact overlay lines from that caption to match 100%
    if effective_lang == "ne" or channel_id == "nepal_speaks" or "nepal" in str(channel_name).lower():
        return nepali_heuristic_payload(raw_caption, channel_name=channel_name, channel_id=channel_id)

    raw_caption = clean_and_deduplicate_source_caption(raw_caption, language=effective_lang, channel_name=channel_name, channel_id=channel_id)
    if not raw_caption:
        raise ValueError('Source has no usable news facts after removing links and teasers')
    prompt = build_system_prompt(effective_lang, channel_name=channel_name)
    prompt += '\nCAPTION REQUIREMENT: Write a standalone news brief in 1-3 short sentences, at most 80 words. Explain who did what and include available key details. Use only facts explicitly supplied in the source. Never invent song names, dates, explanations or context. No URLs, bare domains, Markdown links, read-more prompts or teaser questions. Keep brief sources brief.'
    payload = None

    # Tier 1: Groq Cloud
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"Raw post caption to rewrite for originality and centered headline for channel '{channel_name or channel_id}':\n{raw_caption}"}
                    ],
                    "response_format": {"type": "json_object"}
                },
                timeout=12
            )
            if res.status_code == 200:
                payload = json.loads(res.json()["choices"][0]["message"]["content"])
        except Exception:
            pass

    # Tier 2: Google Gemini
    if not payload:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"{prompt}\n\nRaw post caption (Channel: {channel_name or channel_id}):\n{raw_caption}",
                    config={"response_mime_type": "application/json"}
                )
                payload = json.loads(resp.text)
            except Exception:
                pass

    # Tier 3: OpenRouter
    if not payload:
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
                    json={
                        "model": "meta-llama/llama-3.3-70b-instruct:free",
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": f"Raw post (Channel: {channel_name or channel_id}):\n{raw_caption}"}
                        ]
                    },
                    timeout=15
                )
                if res.status_code == 200:
                    txt = res.json()["choices"][0]["message"]["content"]
                    payload = json.loads(txt[txt.find("{"):txt.rfind("}")+1])
            except Exception:
                pass

    # Tier 4: Smart Heuristic
    if not payload:
        payload = smart_heuristic_headline(raw_caption, language=effective_lang, channel_name=channel_name, channel_id=channel_id)

    # Universal Sanitization of Caption
    if isinstance(payload, dict) and "rewritten_caption" in payload:
        payload["rewritten_caption"] = sanitize_caption(payload["rewritten_caption"], channel_name=channel_name, channel_id=channel_id)
        if not payload["rewritten_caption"]:
            raise ValueError('Generated caption contains no usable news summary')

    # Guarantee ellipsis (...) on Nepali overlays ending
    if effective_lang == "ne" and isinstance(payload, dict) and "overlay_lines" in payload:
        payload["overlay_lines"] = ensure_nepali_overlay_ellipsis(payload["overlay_lines"])

    return payload
