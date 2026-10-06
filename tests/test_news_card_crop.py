import unittest
import cv2
import numpy as np
from modules.image_cleaner import extract_source_photo, erase_text_and_watermarks, SourceTextBoxes, detect_source_text_boxes
from unittest.mock import patch

class NewsCardTests(unittest.TestCase):
    def make_photo(self, height=1000, width=800):
        return np.random.default_rng(42).integers(30,220,(height,width,3),dtype=np.uint8)

    def test_lower_source_panel_is_discarded(self):
        rng=np.random.default_rng(1)
        image=rng.integers(30,220,(1000,800,3),dtype=np.uint8)
        image[550:] = (80,30,10)
        boxes=[(80,620,720,670),(80,710,720,760),(80,830,720,880)]
        photo=extract_source_photo(image,boxes)
        self.assertEqual(photo.shape,(550,800,3))
        np.testing.assert_array_equal(photo,image[:550])
    def test_unrecognized_source_headline_is_cropped_and_rechecked(self):
        class Reader:
            def readtext(self, image, **kwargs):
                return []
            def detect(self, image, **kwargs):
                return ([[[80,720,620,670],[80,720,710,760]]] if len(image)==1000 else [[]]), [[]]
        rng=np.random.default_rng(2)
        image=rng.integers(30,220,(1000,800,3),dtype=np.uint8)
        image[550:] = (80,30,10)
        with patch('modules.image_cleaner._source_text_reader', Reader()):
            photo=erase_text_and_watermarks(image)
        self.assertEqual(photo.shape,(550,800,3))
        np.testing.assert_array_equal(photo,image[:550])
    def test_text_free_photo_is_unchanged(self):
        image=np.full((800,800,3),120,dtype=np.uint8)
        self.assertIs(extract_source_photo(image,[]),image)
    def test_unseparable_card_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_source_photo(np.zeros((1000,800,3),dtype=np.uint8),[(0,300,800,390),(0,420,800,490)])

    def test_top_solid_panel_extraction_preserves_photo_exactly(self):
        image = self.make_photo()
        image[:300] = (20, 20, 20)
        photo = extract_source_photo(image, [(70,55,730,105), (90,145,710,205)])
        np.testing.assert_array_equal(photo, image[300:])

    def test_stacked_source_and_generated_panels_are_both_discarded(self):
        image = self.make_photo(1350, 1080)
        image[575:935] = (80, 35, 5)
        image[935:] = (8, 8, 8)
        photo = extract_source_photo(image, [(160,630,930,685), (160,705,935,760),
                                              (165,825,930,920), (60,1050,1030,1250)])
        np.testing.assert_array_equal(photo, image[:575])

    def test_mid_photo_text_does_not_crop_a_subject(self):
        image = self.make_photo()
        original = image.copy()
        with self.assertRaisesRegex(ValueError, 'preserve the subject'):
            extract_source_photo(image, [(70,470,720,525), (90,540,730,590)])
        np.testing.assert_array_equal(image, original)

    def test_small_logo_is_not_inpainted_or_ignored(self):
        image = self.make_photo()
        with self.assertRaisesRegex(ValueError, 'logo remains'):
            extract_source_photo(image, [(680,20,760,55)])

    def test_detector_only_wave_band_cannot_modify_a_text_free_photo(self):
        image = self.make_photo()
        boxes = SourceTextBoxes([], [(50,540,750,575)])
        self.assertIs(extract_source_photo(image, boxes), image)

    def test_detector_rows_are_not_returned_as_verified_text(self):
        class Reader:
            def readtext(self, image, **kwargs):
                return []
            def detect(self, image, **kwargs):
                return ([[[30,760,600,630]]], [[]])
        boxes = detect_source_text_boxes(self.make_photo(), Reader())
        self.assertEqual(boxes, [])
        self.assertEqual(len(boxes.suspected_rows), 1)

    def test_unrecognized_multiline_center_typography_is_rejected(self):
        image = self.make_photo()
        boxes = SourceTextBoxes([], [(80,420,730,460), (85,480,720,520)])
        with self.assertRaisesRegex(ValueError, 'Unrecognized source typography'):
            extract_source_photo(image, boxes)

    def test_source_text_outside_a_banner_is_rejected(self):
        image = self.make_photo()
        image[700:] = (8,8,8)
        with self.assertRaisesRegex(ValueError, 'logo remains'):
            extract_source_photo(image, [(80,760,730,810), (300,620,440,655)])

    def test_short_residual_label_is_rejected_by_second_scan(self):
        image = self.make_photo()
        with patch('modules.image_cleaner.detect_source_text_boxes', return_value=[(300,200,390,225)]):
            with self.assertRaisesRegex(ValueError, 'logo remains'):
                erase_text_and_watermarks(image, source_text_boxes=[])

    def test_newly_detected_unreadable_panel_on_second_scan_is_not_returned(self):
        image = self.make_photo()
        image[650:] = (8,8,8)
        residual = SourceTextBoxes([], [(80,710,730,750), (80,800,730,850)])
        with patch('modules.image_cleaner.detect_source_text_boxes', return_value=residual):
            with self.assertRaisesRegex(ValueError, 'Source text remains'):
                erase_text_and_watermarks(image, source_text_boxes=[])

    def test_limited_visible_photo_is_rejected_even_with_clean_panels(self):
        image = self.make_photo()
        image[260:] = (8,8,8)
        with self.assertRaisesRegex(ValueError, 'too little usable'):
            extract_source_photo(image, [(80,310,730,370), (80,400,730,450)])
