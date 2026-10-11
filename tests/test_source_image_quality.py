import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from modules.image_cleaner import download_image, validate_image_quality


class SourceImageQualityTests(unittest.TestCase):
    def test_download_preserves_thumbnail_dimensions_for_quality_gate(self):
        image = np.random.default_rng(4).integers(0, 256, (240, 320, 3), dtype=np.uint8)
        _, encoded = cv2.imencode('.jpg', image)
        response = SimpleNamespace(content=encoded.tobytes(), headers={'Content-Type': 'image/jpeg'},
                                   status_code=200, raise_for_status=lambda: None)
        with patch('modules.image_cleaner.requests.get', return_value=response):
            downloaded = download_image('https://example.org/photo.jpg')
        self.assertEqual(downloaded.shape, (240, 320, 3))
        accepted, reason = validate_image_quality(downloaded)
        self.assertFalse(accepted)
        self.assertIn('Low resolution', reason)

    def test_custom_native_minimum_is_enforced(self):
        image = np.random.default_rng(5).integers(0, 256, (550, 900, 3), dtype=np.uint8)
        self.assertFalse(validate_image_quality(image, min_dim=600)[0])
        self.assertTrue(validate_image_quality(image, min_dim=500)[0])

    def test_solid_and_heavily_blurred_sources_are_rejected(self):
        blank = np.full((800, 800, 3), 100, dtype=np.uint8)
        self.assertFalse(validate_image_quality(blank)[0])
        photo = np.random.default_rng(6).integers(0, 256, (800, 800, 3), dtype=np.uint8)
        blurred = cv2.GaussianBlur(photo, (41, 41), 16)
        self.assertFalse(validate_image_quality(blurred)[0])

    def test_sharpness_tolerance_only_accepts_near_threshold_jpeg_ties(self):
        photo=np.random.default_rng(12).integers(0,256,(800,800,3),dtype=np.uint8)
        for score,accepted in ((79.9,True),(79.5,True),(79.4,False),(30.8,False)):
            with self.subTest(score=score),patch('modules.image_cleaner.cv2.Laplacian',return_value=SimpleNamespace(var=lambda:score)):
                self.assertEqual(validate_image_quality(photo,min_sharpness=80)[0],accepted)

    def test_portrait_exception_requires_clear_native_face_and_near_threshold_photo(self):
        photo=np.random.default_rng(13).integers(0,256,(800,800,3),dtype=np.uint8)
        for global_score,face_score,size,accepted in [(32.3,52.2,156,True),(15,100,156,False),
                                                    (32.3,30,156,False),(32.3,100,90,False)]:
            with self.subTest(global_score=global_score,face_score=face_score,size=size):
                detector=SimpleNamespace(detectMultiScale=lambda *a,**k:[(200,200,size,size)])
                scores=[SimpleNamespace(var=lambda:global_score),SimpleNamespace(var=lambda:face_score)]
                with patch('modules.image_cleaner.cv2.CascadeClassifier',return_value=detector),patch('modules.image_cleaner.cv2.Laplacian',side_effect=scores):
                    self.assertEqual(validate_image_quality(photo,min_sharpness=35,allow_portrait_background=True)[0],accepted)

    def test_portrait_exception_never_accepts_absent_or_one_unclear_face(self):
        photo=np.random.default_rng(14).integers(0,256,(800,800,3),dtype=np.uint8)
        for faces in [[],[(200,200,156,156),(400,200,156,156)]]:
            scores=[SimpleNamespace(var=lambda:32.3),SimpleNamespace(var=lambda:60),SimpleNamespace(var=lambda:20)]
            detector=SimpleNamespace(detectMultiScale=lambda *a,**k:faces)
            with patch('modules.image_cleaner.cv2.CascadeClassifier',return_value=detector),patch('modules.image_cleaner.cv2.Laplacian',side_effect=scores):
                self.assertFalse(validate_image_quality(photo,min_sharpness=35,allow_portrait_background=True)[0])


if __name__ == '__main__':
    unittest.main()
