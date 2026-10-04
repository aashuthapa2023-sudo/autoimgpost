import ast
import math
import os
import unittest
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

module = ast.parse(Path('modules/poster_engine.py').read_text(encoding='utf-8'))
function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'fit_headline_line')
namespace = dict(math=math, os=os, Image=Image, ImageDraw=ImageDraw, is_devanagari=lambda text: False)
exec(compile(ast.Module(body=[function], type_ignores=[]), '<safe-margins>', 'exec'), namespace)

class SafeMarginTests(unittest.TestCase):
    def test_oversized_headlines_fit_without_clipping(self):
        font = ImageFont.load_default(size=108)
        for text in ('Breaking news ' * 40, 'W' * 150, 'Short headline'):
            with self.subTest(text=text[:20]):
                line = namespace['fit_headline_line']([(text, 'white')], font, 108, (255, 200, 50), 960, 120)
                self.assertLessEqual(line.width, 960)
                self.assertLessEqual(line.height, 120)
                self.assertIsNotNone(line.getbbox())

    def test_colors_survive_fitting(self):
        line = namespace['fit_headline_line']([('White ', 'white'), ('Highlight', 'highlight')], ImageFont.load_default(size=40), 40, (255, 200, 50), 960, 120)
        colors = set(line.getdata())
        self.assertIn((255, 255, 255, 255), colors)
        self.assertIn((255, 200, 50, 255), colors)
