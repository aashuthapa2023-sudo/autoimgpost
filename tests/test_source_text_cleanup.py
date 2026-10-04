import unittest
import cv2
import numpy as np
from modules.image_cleaner import detect_source_text_boxes, remove_source_text

class Detector:
    def detect(self, image, **kwargs):
        return [[[35, 165, 30, 60], [35, 165, 185, 215]]], [[[[180, 80], [220, 90], [210, 125], [170, 110]]]]

class SourceTextCleanupTests(unittest.TestCase):
    def test_full_image_and_rotated_bounds_are_padded(self):
        image = np.full((260, 260, 3), 90, dtype=np.uint8)
        boxes = detect_source_text_boxes(image, Detector())
        self.assertEqual(boxes, [(31, 26, 169, 64), (31, 181, 169, 219), (166, 76, 224, 129)])

    def test_top_and_bottom_lettering_removed_photo_untouched(self):
        image = np.full((260, 260, 3), 90, dtype=np.uint8)
        cv2.putText(image, 'NEWS', (40, 56), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
        cv2.putText(image, 'NEWS', (40, 210), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 220, 255), 2)
        boxes = detect_source_text_boxes(image, Detector())
        cleaned = remove_source_text(image, boxes)
        self.assertLess(np.max(np.abs(cleaned[30:60,35:165].astype(int)-90)), 15)
        self.assertLess(np.max(np.abs(cleaned[185:215,35:165].astype(int)-90)), 15)
        np.testing.assert_array_equal(cleaned[135:175], image[135:175])

    def test_no_detection_preserves_photo(self):
        image = np.full((100, 100, 3), 90, dtype=np.uint8)
        self.assertIs(remove_source_text(image, []), image)
