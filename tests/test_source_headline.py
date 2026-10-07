import unittest
from unittest.mock import Mock, patch

from modules.source_headline import extract_source_panel_headline, source_panel_payload, render_with_source_fallback


class OCRBoxes(list):
    def __init__(self, records):
        super().__init__(box for box, label, confidence in records)
        self.text_labels = {tuple(box): label for box, label, confidence in records}
        self.text_confidences = {tuple(box): confidence for box, label, confidence in records if confidence is not None}


class SourceHeadlineTests(unittest.TestCase):
    source = ('A marine survey documented two false killer whale calves alongside their mothers in coastal waters.')
    caption = source + '\n\n#MarineLife'

    def boxes(self, lines=None, confidence=.95):
        lines = lines or ['Two false killer whale calves swim', 'beside their mothers in coastal waters']
        return OCRBoxes([((80, 780+index*65, 920, 830+index*65), line, confidence)
                         for index, line in enumerate(lines)])

    def payload(self, boxes=None, **changes):
        arguments = dict(source_caption=self.source, rewritten_caption=self.caption,
                         text_boxes=boxes or self.boxes(), source_shape=(1000,1000,3), crop_bounds=(0,700),
                         content_topic='ocean')
        arguments.update(changes)
        return source_panel_payload(**arguments)

    def test_all_title_words_are_retained_and_caption_is_unchanged(self):
        result = self.payload()
        self.assertEqual(result['headline'], 'Two false killer whale calves swim beside their mothers in coastal waters')
        self.assertEqual(result['rewritten_caption'], self.caption)
        self.assertEqual(result['headline_origin'], 'removed_source_panel')

    def test_colored_fragments_merge_in_source_reading_order(self):
        boxes = OCRBoxes([
            ((440,780,920,830), 'killer whale calves swim', .95),
            ((80,780,420,830), 'Two false', .95),
            ((80,845,920,895), 'beside their mothers in coastal waters', .95)])
        self.assertEqual(self.payload(boxes)['headline'], 'Two false killer whale calves swim beside their mothers in coastal waters')

    def test_body_text_credits_and_retained_photo_words_are_excluded(self):
        boxes = self.boxes()
        extra = [((80,925,920,940),'A long small body paragraph.',.95),
                 ((80,720,920,760),'SOURCE: Publication',.95),
                 ((80,400,920,460),'An unrelated title still inside the photo',.95)]
        for box, label, confidence in extra:
            boxes.append(box); boxes.text_labels[box]=label; boxes.text_confidences[box]=confidence
        result=self.payload(boxes)
        self.assertNotIn('paragraph',result['headline'])
        self.assertNotIn('Publication',result['headline'])
        self.assertNotIn('unrelated',result['headline'])

    def test_missing_or_uncertain_ocr_confidence_fails_closed(self):
        for confidence in [None,.40,float('nan')]:
            with self.subTest(confidence=confidence), self.assertRaisesRegex(ValueError,'uncertain OCR'):
                self.payload(self.boxes(confidence=confidence))

    def test_missing_prominent_label_cannot_silently_drop_title_words(self):
        boxes=self.boxes()
        del boxes.text_labels[boxes[1]]
        with self.assertRaisesRegex(ValueError,'uncertain OCR'):
            self.payload(boxes)

    def test_no_proved_crop_or_title_overlapping_retained_photo_is_rejected(self):
        for crop in [(0,1000),(0,900),(-1,700),(700,0)]:
            with self.subTest(crop=crop), self.assertRaises(ValueError):
                self.payload(crop_bounds=crop)

    def test_top_and_bottom_title_panels_are_ambiguous(self):
        boxes=OCRBoxes([((80,50,920,100),'Two false killer whale calves swim',.95),
                        ((80,850,920,900),'beside their mothers in coastal waters',.95)])
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            self.payload(boxes,crop_bounds=(200,700))

    def test_clipped_or_malformed_source_bounds_are_rejected(self):
        for box in [(0,780,920,830),(80,780,1001,830),(80,780,float('nan'),830)]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                self.payload(OCRBoxes([(box,'Two false killer whale calves swim offshore',.95)]))

    def test_incomplete_titles_counts_species_and_other_page_topics_are_rejected(self):
        cases = ['Two false killer whale calves swim beside their mothers and',
                 'Three false killer whale calves swim beside their mothers',
                 'Two killer whale calves swim beside their mothers',
                 'A new Netflix series begins streaming today']
        for headline in cases:
            with self.subTest(headline=headline), self.assertRaises(ValueError):
                self.payload(self.boxes([headline]))

    def test_punctuation_is_normalized_without_guessing_ocr_symbols(self):
        boxes=self.boxes(['Two false killer whale calves swim .', 'They swim beside their mothers'])
        title=extract_source_panel_headline(boxes,(1000,1000,3),(0,700))['headline']
        self.assertIn('swim. They',title)
        self.assertNotIn('swim,',title)

    def test_actual_nepali_card_uses_only_supported_directive_attribution(self):
        source=('नेकपा एमालेले पार्टीको नीति, निर्णय र नेतृत्वको सार्वजनिक रूपमा आलोचना वा विरोध गर्ने नेता तथा कार्यकर्तामाथि अनुशासनको कारबाही गर्ने निर्णय गरेको छ। '
                'असोज ८ गते सम्पन्न बैठकको निर्णयअनुसार अन्तरपार्टी निर्देशन जारी गरिएको छ। '
                'अध्यक्ष केपी शर्मा ओलीले हस्ताक्षर गरेका छन्। '
                'एमालेले पार्टीमा पुस्तान्तरणलाई संस्थागत प्रक्रियामा लैजाने दाबी गरेको छ। '
                'पार्टी नेतृत्वले पछिल्लो निर्णयलाई संगठनमा अनुशासन र एकता कायम गर्ने प्रयासका रूपमा व्याख्या गरेको छ।')
        caption=('नेकपा एमालेले पार्टीको नीति, निर्णय र नेतृत्वको सार्वजनिक रूपमा आलोचना वा विरोध गर्ने नेता तथा कार्यकर्तामाथि अनुशासनको कारबाही गर्ने निर्णय गरेको छ। '
                 'बैठकको निर्णयअनुसार अन्तरपार्टी निर्देशन जारी गरिएको छ।\n\n#NEPALSPEAKS #NepaliNews')
        lines=['एमालेमा ओलीको आलोचना गरे', 'कारबाही . सार्वजनिक विरोधमा', "'कडा अनुशासन' लागू"]
        boxes=OCRBoxes([((133,1354,1511,1530),lines[0],.95),
                        ((147,1557,1500,1737),lines[1],.95),
                        ((334,1776,1341,1961),lines[2],.95)])
        result=self.payload(boxes,source_caption=source,rewritten_caption=caption,
                            source_shape=(2048,1639,3),crop_bounds=(0,1217),language='ne',content_topic='news')
        self.assertEqual(result['headline'], 'निर्देशनअनुसार: ' + ' '.join(lines).replace(' . ','. '))
        self.assertEqual(result['rewritten_caption'],caption)

    def test_attribution_is_never_invented_if_exact_caption_has_no_source(self):
        source='Scientists may document two false killer whale calves alongside their mothers in coastal waters.'
        with self.assertRaisesRegex(ValueError,'grounding'):
            self.payload(source_caption=source,rewritten_caption=source+'\n\n#MarineLife')

    def test_existing_english_attribution_is_reused_verbatim(self):
        source='According to scientists, two false killer whale calves may swim beside their mothers in coastal waters.'
        result=self.payload(source_caption=source,rewritten_caption=source+'\n\n#MarineLife')
        self.assertTrue(result['headline'].startswith('According to scientists:'))

    def test_exact_caption_pair_is_passed_to_existing_validator(self):
        original_validator=__import__('modules.source_headline',fromlist=['validate_model_payload']).validate_model_payload
        with patch('modules.source_headline.validate_model_payload', wraps=original_validator) as validator:
            result=self.payload()
        self.assertEqual(validator.call_args.args[1],self.source)
        self.assertEqual(validator.call_args.args[0]['rewritten_caption'],self.caption)
        self.assertEqual(result['rewritten_caption'],self.caption)


class SourceHeadlineFallbackTests(unittest.TestCase):
    source = SourceHeadlineTests.source
    caption = SourceHeadlineTests.caption
    boxes = SourceHeadlineTests.boxes
    overflow = 'Headline cannot fit at readable type size; rewrite before publishing'

    def initial_payload(self):
        return {
            'headline': 'Two false killer whale calves swim beside their mothers in coastal waters during a marine survey',
            'overlay_lines': [[{'text': 'Two false killer whale calves swim beside their mothers in coastal waters during a marine survey', 'type': 'white'}]],
            'rewritten_caption': self.caption,
        }

    def run_fallback(self, render_fn, **changes):
        arguments = dict(payload=self.initial_payload(), source_caption=self.source,
                         text_boxes=self.boxes(), source_shape=(1000,1000,3), crop_bounds=(0,700),
                         content_topic='ocean', render_fn=render_fn)
        arguments.update(changes)
        return render_with_source_fallback(**arguments)

    def test_first_headline_that_fits_renders_once_with_the_identical_caption(self):
        initial = self.initial_payload()
        renderer = Mock()
        result = self.run_fallback(renderer, payload=initial)
        self.assertIs(result, initial)
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.kwargs['overlay_lines'], initial['overlay_lines'])
        self.assertEqual(renderer.call_args.kwargs['caption'], self.caption)
        self.assertEqual(renderer.call_args.kwargs['headline_origin'], 'caption')

    def test_only_typography_overflow_retries_the_entire_validated_removed_title(self):
        renderer = Mock(side_effect=[ValueError(self.overflow), None])
        unchanged_source_photo = object()
        result = self.run_fallback(renderer, base_img=unchanged_source_photo, output_path='poster.jpg', text_position='bottom')
        self.assertEqual(renderer.call_count, 2)
        self.assertEqual(result['headline'], 'Two false killer whale calves swim beside their mothers in coastal waters')
        self.assertEqual(result['rewritten_caption'], self.caption)
        self.assertEqual(result['headline_origin'], 'removed_source_panel')
        self.assertEqual(result['source_headline_bounds'], list(self.boxes()))
        first, second = [call.kwargs for call in renderer.call_args_list]
        for call in [first, second]:
            self.assertEqual(call['caption'], self.caption)
            self.assertIs(call['base_img'], unchanged_source_photo)
            self.assertEqual(call['output_path'], 'poster.jpg')
            self.assertEqual(call['text_position'], 'bottom')
        self.assertEqual(first['headline_origin'], 'caption')
        self.assertEqual(second['headline_origin'], 'removed_source_panel')
        self.assertEqual(second['overlay_lines'], result['overlay_lines'])
        self.assertNotEqual(first['overlay_lines'], second['overlay_lines'])

    def test_other_render_value_errors_do_not_try_an_alternative(self):
        for message in ['Source cleanup and layout approval are required before publishing',
                        'Headline exceeds its measured safe area',
                        'Brand colours do not provide safe headline contrast',
                        'Headline must be complete and concise before layout']:
            with self.subTest(message=message):
                original = ValueError(message)
                renderer = Mock(side_effect=original)
                with self.assertRaises(ValueError) as caught:
                    self.run_fallback(renderer)
                self.assertIs(caught.exception, original)
                renderer.assert_called_once()

    def test_missing_proved_crop_invalid_title_or_uncertain_ocr_cannot_retry(self):
        cases = [
            {'crop_bounds': (0,1000)},
            {'crop_bounds': None},
            {'text_boxes': OCRBoxes([])},
            {'text_boxes': self.boxes(['Two false killer whale calves swim beside their mothers and'])},
            {'text_boxes': self.boxes(['Three false killer whale calves swim beside their mothers in coastal waters'])},
            {'text_boxes': self.boxes(['A new Netflix series begins streaming today'])},
            {'text_boxes': self.boxes(confidence=None)},
            {'text_boxes': self.boxes(confidence=.74)},
            {'text_boxes': self.boxes(confidence=float('nan'))},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                original = ValueError(self.overflow)
                renderer = Mock(side_effect=[original, None])
                with self.assertRaises(ValueError) as caught:
                    self.run_fallback(renderer, **changes)
                self.assertIs(caught.exception, original)
                renderer.assert_called_once()

    def test_failed_fallback_render_propagates_failure_instead_of_success(self):
        for message in [self.overflow, 'Branding is outside the safe area']:
            with self.subTest(message=message):
                fallback_error = ValueError(message)
                renderer = Mock(side_effect=[ValueError(self.overflow), fallback_error])
                with self.assertRaises(ValueError) as caught:
                    self.run_fallback(renderer)
                self.assertIs(caught.exception, fallback_error)
                self.assertEqual(renderer.call_count, 2)

    def test_existing_headline_origin_is_forwarded_on_a_successful_first_render(self):
        initial = self.initial_payload()
        initial['headline_origin'] = 'removed_source_panel'
        renderer = Mock()
        result = self.run_fallback(renderer, payload=initial)
        self.assertIs(result, initial)
        renderer.assert_called_once()
        self.assertEqual(renderer.call_args.kwargs['headline_origin'], 'removed_source_panel')


if __name__ == '__main__':
    unittest.main()
