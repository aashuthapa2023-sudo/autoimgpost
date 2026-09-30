import unittest
import cv2
import numpy as np
from PIL import Image
from modules.logo_branding import ASSETS, detect_source_logos, apply_branding

class LogoTests(unittest.TestCase):
    def test_scaled_corner_matches(self):
        ref=cv2.imread(str(ASSETS/'himali_reference.png'))
        for factor in (.7,1,1.3):
            h,w=round(1350*factor),round(1080*factor)
            image=np.full((h,w,3),145,dtype=np.uint8)
            badge=cv2.resize(ref,(round(98*factor),round(107*factor)))
            y=round(40*factor); x=w-badge.shape[1]
            image[y:y+badge.shape[0],x:]=badge
            self.assertEqual(len(detect_source_logos(image)),1)
    def test_blank_has_no_match(self):
        self.assertEqual(detect_source_logos(np.zeros((1350,1080,3),dtype=np.uint8)),[])
    def test_no_box_keeps_image_unchanged(self):
        image=Image.new('RGB',(1080,1350),'blue')
        self.assertEqual(apply_branding(image.copy(),[],image.size).tobytes(),image.tobytes())
    def test_circle_keeps_corner_background(self):
        image=Image.new('RGB',(1080,1350),'blue')
        result=apply_branding(image,[(982,40,98,107)],image.size)
        self.assertEqual(result.getpixel((982,40)),(0,0,255))
        self.assertNotEqual(result.getpixel((1030,90)),(0,0,255))

if __name__=='__main__': unittest.main()
