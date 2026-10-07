"""Reuse a complete, verified headline from a source panel already removed safely."""
import math
import re

from modules.llm_transformer import validate_model_payload


def _source_credit(text):
    text = str(text).strip()
    return bool(re.fullmatch(r'(?:news|breaking news|photo|image|source|credit|copyright)', text, re.IGNORECASE)
                or re.match(r'^(?:photo|image|source|credit|copyright|via)\s*[:©@]|^©|^https?://|^www\.|^[@#]', text, re.IGNORECASE))


def extract_source_panel_headline(text_boxes, source_shape, crop_bounds):
    """Use existing OCR only, wholly outside the extractor's proved vertical crop.

    ``crop_bounds`` is ``(top, bottom)`` in the original image coordinates.
    Confidence metadata is mandatory; accepted detector boxes alone cannot
    establish that their recognized words are correct.
    """
    try:
        height, width = map(int, source_shape[:2])
        top, bottom = crop_bounds
        if (height <= 0 or width <= 0 or not isinstance(top, int) or not isinstance(bottom, int)
                or not 0 <= top < bottom <= height or (top == 0 and bottom == height)):
            raise ValueError
    except (TypeError, ValueError, IndexError):
        raise ValueError('Source headline needs a proved nonempty removed panel') from None
    labels = getattr(text_boxes, 'text_labels', {})
    confidences = getattr(text_boxes, 'text_confidences', {})
    lines = []
    for raw_box in text_boxes:
        try:
            left, line_top, right, line_bottom = box = tuple(raw_box)
        except (TypeError, ValueError):
            raise ValueError('Source OCR bounds are malformed') from None
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in box):
            raise ValueError('Source OCR bounds are malformed')
        if not (line_bottom <= top or line_top >= bottom):
            continue
        label = str(labels.get(box, '')).strip()
        if not label:
            if right-left >= width*.25 and line_bottom-line_top >= height*.035:
                raise ValueError('Removed source headline contains uncertain OCR words')
            continue
        if _source_credit(label):
            continue
        if not 0 <= left < right <= width or not 0 <= line_top < line_bottom <= height:
            raise ValueError('Removed source lettering exceeds its source image')
        panel = 'top' if line_bottom <= top else 'bottom'
        for line in lines:
            overlap = min(line['box'][3], line_bottom) - max(line['box'][1], line_top)
            if line['panel'] == panel and overlap >= min(line['box'][3] - line['box'][1], line_bottom - line_top)*.45:
                line['parts'].append((left, label, box, confidences.get(box)))
                line['box'] = (min(left, line['box'][0]), min(line_top, line['box'][1]),
                               max(right, line['box'][2]), max(line_bottom, line['box'][3]))
                break
        else:
            lines.append({'panel': panel, 'box': box, 'parts': [(left, label, box, confidences.get(box))]})
    broad = [line for line in lines if line['box'][2] - line['box'][0] >= width*.25]
    if not broad:
        raise ValueError('Removed source panel contains no prominent headline')
    dominant_height = max(line['box'][3] - line['box'][1] for line in broad)
    prominent = [line for line in broad if line['box'][3] - line['box'][1] >= max(height*.035, dominant_height*.70)]
    if not 1 <= len(prominent) <= 4 or len({line['panel'] for line in prominent}) != 1:
        raise ValueError('Removed source title is ambiguous or too long')
    prominent.sort(key=lambda line: (line['box'][1], line['box'][0]))
    parts = []
    selected_boxes = []
    selected_confidences = []
    for line in prominent:
        for _, label, box, confidence in sorted(line['parts'], key=lambda part: part[0]):
            if (not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                    or confidence < .75 or confidence > 1 or '\ufffd' in label):
                raise ValueError('Removed source headline contains uncertain OCR words')
            if box[0] < 3 or box[2] > width - 3 or box[1] < 3 or box[3] > height - 3:
                raise ValueError('Removed source headline is clipped at a source edge')
            parts.append(label)
            selected_boxes.append(box)
            selected_confidences.append(confidence)
    # Normalize whitespace around existing punctuation only; never repair a
    # count, name, missing word or punctuation symbol guessed by recognition.
    headline = re.sub(r'\s+([,.;:!?।])', r'\1', ' '.join(parts))
    headline = re.sub(r'\s+', ' ', headline).strip()
    return {'headline': headline, 'bounds': selected_boxes, 'confidence': min(selected_confidences)}


def _source_attribution(source_caption, language):
    source = str(source_caption)
    if language == 'ne':
        # This prefix identifies the directive mentioned in the same caption;
        # both the directive and an attribution must actually be present.
        if 'निर्देशन' in source and 'अनुसार' in source:
            return 'निर्देशनअनुसार:'
        match = re.search(r'(?:प्रहरी|मन्त्रालय|अदालत|वैज्ञानिक|अनुसन्धानकर्ता)(?:का|को)?\s+अनुसार', source)
    else:
        match = re.search(r'\baccording to (?:the )?(?:researchers|scientists|study|report)\b', source, re.IGNORECASE)
    return match.group(0) + ':' if match else ''


def source_panel_payload(source_caption, rewritten_caption, text_boxes, source_shape, crop_bounds, *,
                         language='en', channel_name='', channel_id='', content_topic=''):
    """Validate an entire removed title against its exact associated caption.

    The existing caption is validated unchanged. No OCR pass, synthesis, word
    cutting, alternate image, or relaxed grounding is performed here. Layout
    must still independently approve the resulting headline before publishing.
    """
    if language not in ('en', 'ne'):
        raise ValueError('Source-panel headline language is unsupported')
    if language not in ('en', 'ne'):
        raise ValueError('Source-panel headline language is unsupported')
    title = extract_source_panel_headline(text_boxes, source_shape, crop_bounds)
    headlines = [title['headline']]
    attribution = _source_attribution(source_caption, language)
    if attribution:
        headlines.append(attribution + ' ' + title['headline'])
    last_error = None
    for headline in headlines:
        try:
            payload = validate_model_payload({'headline': headline, 'rewritten_caption': rewritten_caption},
                source_caption, language, channel_name, channel_id, content_topic)
            # Validation already inspected this exact original caption. Retain
            # it byte-for-byte so its approved caption manifest stays stable.
            payload['rewritten_caption'] = rewritten_caption
            payload['headline_origin'] = 'removed_source_panel'
            payload['source_headline_bounds'] = title['bounds']
            return payload
        except ValueError as error:
            last_error = error
    raise ValueError('Complete source-panel headline did not pass caption grounding: ' + str(last_error))


def render_with_source_fallback(payload, source_caption, text_boxes, source_shape, crop_bounds, *,
                                language='en', channel_name='', channel_id='', content_topic='',
                                render_fn=None, **poster_options):
    """Retry only a typography overflow with a validated entire removed title."""
    if render_fn is None:
        from modules.poster_engine import render_final_poster
        render_fn = render_final_poster

    def render(candidate):
        render_fn(overlay_lines=candidate['overlay_lines'],caption=candidate['rewritten_caption'],
                  headline_origin=candidate.get('headline_origin','caption'),**poster_options)

    try:
        render(payload)
        return payload
    except ValueError as error:
        if not str(error).startswith('Headline cannot fit at readable type size'):
            raise
        try:
            alternative = source_panel_payload(source_caption,payload['rewritten_caption'],text_boxes,
                source_shape,crop_bounds,language=language,channel_name=channel_name,
                channel_id=channel_id,content_topic=content_topic)
        except ValueError:
            raise error from None
        render(alternative)
        return alternative
