import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from modules.source_card import inspect_readable_source_card, render_preserved_source_card
from modules.poster_quality import verify_publishable_poster


class SourceCardTests(unittest.TestCase):
    def image(self):
        # Distinct corners expose any destructive crop; smooth photo-like pixels
        # allow an intact resized frame to be compared through JPEG compression.
        y, x = np.indices((1000, 800))
        image = np.stack((40+x//8, 60+y//10, 90+(x+y)//20), axis=2).astype(np.uint8)
        image[:80, :80] = (0, 0, 255)
        image[:80, -80:] = (0, 255, 0)
        image[-80:, :80] = (255, 0, 0)
        image[-80:, -80:] = (0, 255, 255)
        return image

    def record(self, text, top=550, height=50, left=80, right=720, confidence=.99):
        return ([[left, top], [right, top], [right, top+height], [left, top+height]], text, confidence)

    def approved(self, lines=None):
        lines = lines or ['Two whale calves swim', 'beside their mothers in coastal waters']
        image = self.image()
        records = [self.record(line, top=550+index*75) for index, line in enumerate(lines)]
        for index, line in enumerate(lines):
            cv2.putText(image, line, (80, 590+index*75), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
        caption = ' '.join(lines)+'.'
        return image, caption, inspect_readable_source_card(image, caption, records=records)

    def render(self, directory):
        image, caption, review = self.approved()
        path = Path(directory)/'poster.jpg'
        render_preserved_source_card(image, review, caption, "Ocean's Secret", str(path))
        return image, caption, review, path

    def test_complete_supported_headlines_with_one_to_four_lines_are_accepted(self):
        examples = [
            ['Whale calves swim offshore'],
            ['Two whale calves swim', 'beside their mothers in coastal waters'],
            ['Two whale calves swim', 'beside their mothers', 'in coastal waters'],
            ['Two whale calves swim', 'beside their mothers', 'in coastal waters', 'during a marine survey'],
        ]
        for lines in examples:
            with self.subTest(lines=len(lines)):
                image, caption, review = self.approved(lines)
                self.assertEqual(review['headline'], caption[:-1])
                self.assertEqual(len(review['headline_bounds']), len(lines))
                self.assertEqual(review['source_image_sha256'], hashlib.sha256(image.tobytes()).hexdigest())

    def test_small_body_text_is_rejected_even_with_a_readable_headline(self):
        image = self.image()
        records = [self.record('Whale calves swim offshore'), self.record('A marine survey documented the calves.', top=650, height=14)]
        with self.assertRaisesRegex(ValueError, 'small body text'):
            inspect_readable_source_card(image, 'Whale calves swim offshore. A marine survey documented the calves.', records)

    def test_too_many_readable_lines_or_low_confidence_headline_are_rejected(self):
        for records in [
            [self.record('Whale calves swim offshore', top=300+index*75) for index in range(5)],
            [self.record('Whale calves swim offshore', confidence=.2)],
        ]:
            with self.subTest(records=records), self.assertRaises(ValueError):
                inspect_readable_source_card(self.image(), 'Whale calves swim offshore.', records)

    def test_quoted_headline_with_unrelated_uncertainty_in_another_paragraph_is_accepted(self):
        headline = 'Whale calves swim offshore'
        caption = 'Whale calves swim offshore.\n\nScientists may find additional animals during the next marine survey, but no future findings are confirmed.'
        review = inspect_readable_source_card(self.image(), caption, [self.record(headline)])
        self.assertEqual(review['headline'], headline)

    def test_ocr_cannot_turn_decimal_2_point_4_into_24(self):
        source = 'These marine organisms date back 2.4 billion years.'
        correct = 'These marine organisms date back 2.4 billion years'
        self.assertEqual(inspect_readable_source_card(self.image(), source, [self.record(correct)])['headline'], correct)
        with self.assertRaisesRegex(ValueError, 'not supported'):
            inspect_readable_source_card(self.image(), source, [self.record(correct.replace('2.4', '24'))])

    def test_caption_that_explicitly_debunks_the_same_headline_is_rejected(self):
        headline = 'Scientists discovered a new coral species'
        caption = 'The claim that scientists discovered a new coral species is not true.'
        with self.assertRaises(ValueError):
            inspect_readable_source_card(self.image(), caption, [self.record(headline)])

    def test_headline_lettering_clipped_at_any_source_edge_is_rejected(self):
        cases = [dict(left=0), dict(right=800), dict(top=0), dict(top=960)]
        for changes in cases:
            with self.subTest(edge=changes), self.assertRaisesRegex(ValueError, 'clipped'):
                inspect_readable_source_card(self.image(), 'Whale calves swim offshore.', [self.record('Whale calves swim offshore', **changes)])

    def test_unsupported_counts_species_or_certainty_are_rejected(self):
        cases = [
            ('Three false killer whale calves swim offshore', 'Two false killer whale calves swim offshore.'),
            ('Two killer whale calves swim offshore', 'Two false killer whale calves swim offshore.'),
            ('Scientists identify a new coral species', 'Scientists may identify a new coral species.'),
        ]
        for headline, caption in cases:
            with self.subTest(headline=headline), self.assertRaisesRegex(ValueError, 'not supported'):
                inspect_readable_source_card(self.image(), caption, [self.record(headline)])

    def test_incomplete_or_question_only_source_headline_is_rejected(self):
        for headline in ['Two whale calves swim offshore and', 'Two whale calves swim...', 'Why are whale calves swimming offshore?']:
            with self.subTest(headline=headline), self.assertRaisesRegex(ValueError, 'incomplete'):
                inspect_readable_source_card(self.image(), headline, [self.record(headline)])

    def test_changing_source_pixels_after_review_blocks_rendering(self):
        image, caption, review = self.approved()
        image[500, 500] ^= 255
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'poster.jpg'
            with self.assertRaisesRegex(ValueError, 'changed after readability approval'):
                render_preserved_source_card(image, review, caption, 'Ocean', str(path))
            self.assertFalse(path.exists())

    def test_original_card_is_retained_without_a_second_headline(self):
        with tempfile.TemporaryDirectory() as directory:
            source, caption, review, path = self.render(directory)
            manifest = verify_publishable_poster(str(path), caption)
            self.assertEqual(manifest['layout_kind'], 'preserved_source_card')
            self.assertTrue(manifest['preserved_source_approved'])
            self.assertEqual(manifest['headline'], review['headline'])
            self.assertEqual(len(manifest['text_bounds']), len(review['headline_bounds']))
            x, y, width, height = manifest['photo_bounds']
            expected = Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB)).resize((width, height), Image.Resampling.LANCZOS)
            with Image.open(path) as poster:
                self.assertEqual(poster.size, (1080, 1350))
                retained = np.asarray(poster.crop((x, y, x+width, y+height))).astype(int)
            self.assertLess(np.mean(np.abs(retained-np.asarray(expected).astype(int))), 4)
            # A separate masthead is permitted, but no generated text panel or
            # second headline may be painted over any part of the source card.
            self.assertGreater(manifest['brand_bounds'][1], y+height)
            self.assertNotIn('panel_bounds', manifest)
            self.assertGreaterEqual(manifest['min_visible_letter_height'], 32)

    def test_mutated_finished_image_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, caption, _, path = self.render(directory)
            path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError, 'changed after quality approval'):
                verify_publishable_poster(str(path), caption)

    def test_mutated_caption_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, caption, _, path = self.render(directory)
            with self.assertRaisesRegex(ValueError, 'Caption does not match'):
                verify_publishable_poster(str(path), caption+' An unsupported new claim.')

    def test_missing_readability_approval_or_reduced_letter_height_is_blocked(self):
        for changes in [{'preserved_source_approved': False}, {'min_visible_letter_height': 31}]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                _, caption, _, path = self.render(directory)
                report = path.with_suffix('.quality.json')
                data = json.loads(report.read_text(encoding='utf-8'))
                data.update(changes)
                report.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'readability approval'):
                    verify_publishable_poster(str(path), caption)

    def test_headline_outside_retained_frame_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, caption, _, path = self.render(directory)
            report = path.with_suffix('.quality.json')
            data = json.loads(report.read_text(encoding='utf-8'))
            data['text_bounds'][0][0] = data['photo_bounds'][0]-1
            report.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'outside its retained frame'):
                verify_publishable_poster(str(path), caption)


if __name__ == '__main__':
    unittest.main()
