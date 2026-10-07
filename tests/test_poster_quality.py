import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from modules.poster_engine import render_final_poster
from modules.poster_quality import verify_publishable_poster
from modules.publisher import publish_to_facebook
from modules.story_dedup import is_repeated_story


class PublishApprovalTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image=Path(self.directory.name)/'poster.jpg'
        self.caption='Two whale calves were documented alongside their mothers in coastal waters.'
        render_final_poster(np.zeros((1000,800,3),dtype=np.uint8),
            [[{'text':'Two whale calves documented alongside their mothers','type':'white'}]],
            dest_page_name="Ocean's Secret",output_path=str(self.image),caption=self.caption,source_checked=True)

    def test_approved_exact_pair_passes(self):
        data=verify_publishable_poster(self.image,self.caption)
        self.assertGreaterEqual(data['font_size'],64)
        for l,t,r,b in data['text_bounds']:
            self.assertLessEqual(abs((l+r)/2-540),1)

    def test_three_tall_glyph_lines_use_remaining_safe_panel_space(self):
        # Devanagari ascenders can make three readable lines295px high. They
        # physically fit while the old290px cap rejected the entire post.
        runs=[[('समुद्रमा नयाँ जीव भेटियो','white')]]*3
        glyphs=Image.new('RGBA',(900,85),(255,255,255,255))
        with patch('modules.poster_engine._wrap_headline',return_value=runs), \
             patch('modules.poster_engine._render_runs',return_value=glyphs):
            render_final_poster(np.zeros((1000,800,3),dtype=np.uint8),
                [[{'text':'समुद्रमा नयाँ जीव भेटियो','type':'white'}]],
                dest_page_name='Nepal Speaks',output_path=str(self.image),
                caption=self.caption,source_checked=True,text_position='bottom',
                logo_position='with-text',safe_margin=64,min_font_size=66)
        data=verify_publishable_poster(self.image,self.caption)
        self.assertLessEqual(data['panel_height'],470)
        self.assertGreaterEqual(data['font_size'],66)
        self.assertEqual(len(data['text_bounds']),3)
        self.assertLessEqual(data['text_bounds'][-1][3],1286)

    def test_changed_image_or_caption_cannot_publish(self):
        with self.assertRaises(ValueError):
            verify_publishable_poster(self.image,self.caption+' Extra unsupported claim.')
        self.image.write_bytes(self.image.read_bytes()+b'altered')
        with patch('modules.publisher.requests.post') as request:
            with self.assertRaises(RuntimeError):
                publish_to_facebook('page','token',str(self.image),self.caption)
            request.assert_not_called()

    def test_unchecked_source_and_legacy_queue_are_blocked(self):
        report=self.image.with_suffix('.quality.json')
        data=json.loads(report.read_text(encoding='utf-8'))
        data['source_checked']=False
        report.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):verify_publishable_poster(self.image,self.caption)
        report.unlink()
        with patch('modules.publisher.requests.post') as request:
            with self.assertRaises(RuntimeError):publish_to_facebook('page','token',str(self.image),self.caption)
            request.assert_not_called()

    def test_opposite_branding_edge_reserves_photo_space(self):
        render_final_poster(np.zeros((1000,800,3),dtype=np.uint8),
            [[{'text':'Two whale calves documented alongside their mothers','type':'white'}]],
            dest_page_name="Ocean's Secret",output_path=str(self.image),caption=self.caption,
            source_checked=True,text_position='bottom',logo_position='top-right')
        data=verify_publishable_poster(self.image,self.caption)
        self.assertLess(data['brand_bounds'][3],data['photo_bounds'][1])

    def test_owned_logo_is_safe_at_every_supported_placement(self):
        for position in ('top','bottom'):
            for logo in ('with-text','top-left','top-center','top-right','bottom-left','bottom-center','bottom-right'):
                with self.subTest(position=position,logo=logo):
                    render_final_poster(np.zeros((1000,800,3),dtype=np.uint8),
                        [[{'text':'Two whale calves documented alongside their mothers','type':'white'}]],
                        dest_page_name='Nepal Speaks',output_path=str(self.image),caption=self.caption,
                        source_checked=True,text_position=position,logo_position=logo,
                        logo_path='assets/branding/nepal_speaks.png')
                    data=verify_publishable_poster(self.image,self.caption)
                    self.assertGreaterEqual(data['logo_bounds'][1],64)
                    self.assertLessEqual(data['logo_bounds'][3],1286)


class StoryDedupTests(unittest.TestCase):
    def test_same_story_from_different_links_is_duplicate(self):
        caption='Artists released 31000 songs last year, according to the new music report.'
        self.assertTrue(is_repeated_story(caption+' https://site.test/story', [caption.upper()]))

    def test_changed_count_is_a_new_fact(self):
        old='Artists released 31000 songs last year, according to the new music report.'
        self.assertFalse(is_repeated_story(old.replace('31000','32000'),[old]))

    def test_similar_subject_different_event_is_retained(self):
        old='Taylor Swift released her new album with thirteen tracks this Friday.'
        new='Taylor Swift announced her concert tour visiting London and Paris next summer.'
        self.assertFalse(is_repeated_story(new,[old]))
