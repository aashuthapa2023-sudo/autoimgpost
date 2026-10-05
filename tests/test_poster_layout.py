import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from modules.poster_engine import render_final_poster

class PosterLayoutTests(unittest.TestCase):
    def test_subject_markers_survive_top_and_bottom_panels(self):
        # Four corner markers must all survive: no centre crop or backing over faces.
        source = np.full((1000,800,3),100,dtype=np.uint8)
        source[:100,:100] = (0,0,255)
        source[:100,-100:] = (0,255,0)
        source[-100:,:100] = (255,0,0)
        source[-100:,-100:] = (0,255,255)
        for position in ['top','bottom']:
            with tempfile.TemporaryDirectory() as directory:
                out = str(Path(directory)/'poster.png')
                render_final_poster(source, [[{'text':'Whale calves swim alongside their mothers in coastal waters','type':'white'}]], dest_page_name='Ocean',output_path=out,text_position=position)
                pixels=np.asarray(Image.open(out))
                for rgb in [(255,0,0),(0,255,0),(0,0,255),(255,255,0)]:
                    self.assertGreater(np.sum(np.max(abs(pixels.astype(int)-rgb),axis=2)<25),100)
    def test_overlong_headline_is_rejected_instead_of_tiny_type(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                render_final_poster(np.zeros((800,800,3),dtype=np.uint8), [[{'text':'Very long headline ' * 40,'type':'white'}]], output_path=str(Path(directory)/'poster.jpg'))
