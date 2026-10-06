import unittest
import cv2
import numpy as np
from modules.image_cleaner import extract_source_photo

class NewsCardTests(unittest.TestCase):
    def test_lower_source_panel_is_discarded(self):
        rng=np.random.default_rng(1)
        image=rng.integers(30,220,(1000,800,3),dtype=np.uint8)
        image[550:] = (80,30,10)
        boxes=[(80,620,720,670),(80,710,720,760),(80,830,720,880)]
        photo=extract_source_photo(image,boxes)
        self.assertEqual(photo.shape,(550,800,3))
        np.testing.assert_array_equal(photo,image[:550])
    def test_text_free_photo_is_unchanged(self):
        image=np.full((800,800,3),120,dtype=np.uint8)
        self.assertIs(extract_source_photo(image,[]),image)
    def test_unseparable_card_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_source_photo(np.zeros((1000,800,3),dtype=np.uint8),[(0,300,800,390),(0,420,800,490)])
