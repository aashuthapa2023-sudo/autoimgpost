import unittest
import cv2
import numpy as np
from modules.image_cleaner import detect_source_text_boxes, remove_source_text, detect_and_remove_watermarks, extract_source_photo

class Detector:
    def readtext(self, image, **kwargs):
        return [([[35,30],[165,30],[165,60],[35,60]], 'NEWS', .95),
                ([[35,185],[165,185],[165,215],[35,215]], 'NEWS', .95),
                ([[180,80],[220,90],[210,125],[170,110]], 'TEXT', .9)]

class SourceTextCleanupTests(unittest.TestCase):
    def test_full_image_and_rotated_bounds_are_padded(self):
        image = np.full((400, 400, 3), 90, dtype=np.uint8)
        boxes = detect_source_text_boxes(image, Detector())
        self.assertEqual(boxes, [(31, 26, 169, 64), (31, 181, 169, 219), (166, 76, 224, 129)])

    def test_photo_lettering_is_rejected_without_changing_pixels(self):
        image = np.full((400, 400, 3), 90, dtype=np.uint8)
        cv2.putText(image, 'NEWS', (40, 56), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
        cv2.putText(image, 'NEWS', (40, 210), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 220, 255), 2)
        boxes = detect_source_text_boxes(image, Detector())
        original = image.copy()
        with self.assertRaisesRegex(ValueError, 'instead of inpainting'):
            remove_source_text(image, boxes)
        np.testing.assert_array_equal(image, original)

    def test_color_and_edges_do_not_authorize_watermark_removal(self):
        image = np.zeros((800, 800, 3), dtype=np.uint8)
        cv2.rectangle(image, (15, 15), (80, 70), (0, 0, 255), -1)
        cv2.putText(image, 'BASS', (500, 740), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        self.assertIs(detect_and_remove_watermarks(image), image)

    def test_unrecognized_texture_does_not_get_removed(self):
        class TextureDetector:
            def readtext(self, image, **kwargs):
                return [([[20,20],[80,20],[80,60],[20,60]], 'xx', .2)]
        self.assertEqual(detect_source_text_boxes(np.full((400,400,3),90,dtype=np.uint8), TextureDetector()), [])

    def test_source_initials_single_character_and_number_are_retained(self):
        class ShortTextReader:
            def readtext(self, image, **kwargs):
                return [([[10,10],[65,10],[65,45],[10,45]], 'ND', .45),
                        ([[700,20],[765,20],[765,60],[700,60]], 'N', .70),
                        ([[300,350],[350,350],[350,385],[300,385]], '42', .90),
                        ([[400,450],[430,450],[430,490],[400,490]], '7', .95)]
        image = np.zeros((1000, 800, 3), dtype=np.uint8)
        boxes = detect_source_text_boxes(image, ShortTextReader())
        self.assertEqual(len(boxes), 4)
        with self.assertRaises(ValueError):
            extract_source_photo(image, boxes)

    def test_unreadable_corner_logo_is_not_claimed_clean(self):
        class LogoReader:
            def readtext(self, image, **kwargs):
                return [([[47,23],[87,23],[87,71],[47,71]], ' )', .033)]
            def detect(self, image, **kwargs):
                return ([[[47,87,23,71]]], [[]])
        image = np.random.default_rng(3).integers(0,256,(1350,1080,3),dtype=np.uint8)
        original = image.copy()
        boxes = detect_source_text_boxes(image, LogoReader())
        self.assertFalse(boxes)
        self.assertEqual(len(boxes.suspected_marks), 1)
        with self.assertRaisesRegex(ValueError, 'Unverified corner'):
            extract_source_photo(image, boxes)
        np.testing.assert_array_equal(image, original)

    def test_large_removal_is_rejected(self):
        with self.assertRaises(ValueError):
            remove_source_text(np.zeros((400,400,3), dtype=np.uint8), [(0,0,200,200)])

    def test_no_detection_preserves_photo(self):
        image = np.full((100, 100, 3), 90, dtype=np.uint8)
        self.assertIs(remove_source_text(image, []), image)
