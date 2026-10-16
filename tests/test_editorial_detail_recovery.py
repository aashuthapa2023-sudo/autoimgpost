"""Retain real subject detail, complete facts and reviewed square source frames."""
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
import cv2,numpy as np
from modules.image_cleaner import validate_image_quality,SourceTextBoxes
from modules.source_editorial import extract_editorial_photo,prepare_editorial_photo
from modules.poster_engine import render_final_poster,headline_fits_poster
from modules.poster_quality import verify_publishable_poster
from modules.llm_transformer import format_balanced_overlay,headline_is_usable
from modules.source_replacement import replacement_payload


class EditorialDetailTests(unittest.TestCase):
    def test_near_threshold_native_subject_can_pass_without_sharpening(self):
        # Real pixel fixture: a detailed center with a deliberately soft surround.
        g=np.random.default_rng(1).normal(0,1,(800,1080)).astype(np.float32)
        photo=np.full((800,1080),128,np.float32)
        photo[120:680,162:918]=128+g[120:680,162:918]*1.9
        # Low frequency lighting creates contrast, not fake sharp edges.
        photo+=np.linspace(-60,60,1080)[None,:]
        photo=np.repeat(np.clip(photo,0,255).astype(np.uint8)[:,:,None],3,axis=2)
        original=photo.copy()
        self.assertFalse(validate_image_quality(photo,min_sharpness=40)[0])
        self.assertTrue(validate_image_quality(photo,min_sharpness=40,allow_editorial_detail=True)[0])
        np.testing.assert_array_equal(photo,original)

    def test_display_detail_never_upsamples_or_accepts_gross_blur(self):
        photo=np.random.default_rng(3).integers(0,256,(900,1300,3),dtype=np.uint8)
        scores=[SimpleNamespace(var=lambda:30),SimpleNamespace(var=lambda:60),SimpleNamespace(var=lambda:20)]
        with patch('modules.image_cleaner.cv2.Laplacian',side_effect=scores):
            self.assertTrue(validate_image_quality(photo,min_sharpness=35,allow_editorial_detail=True)[0])
        blurred=cv2.GaussianBlur(photo,(41,41),14)
        self.assertFalse(validate_image_quality(blurred,min_sharpness=35,allow_editorial_detail=True)[0])
        with patch('modules.image_cleaner.cv2.Laplacian',return_value=SimpleNamespace(var=lambda:32)),patch('modules.image_cleaner.cv2.resize') as resize:
            self.assertFalse(validate_image_quality(photo[:800,:1000],min_sharpness=35,allow_editorial_detail=True)[0])
            resize.assert_not_called()

    def test_small_logo_edges_cannot_substitute_for_subject_detail(self):
        photo=np.full((900,1080,3),80,np.uint8)
        photo[:90,:90]=np.random.default_rng(4).integers(0,256,(90,90,3),dtype=np.uint8)
        with patch('modules.image_cleaner.cv2.Laplacian',side_effect=[SimpleNamespace(var=lambda:30),SimpleNamespace(var=lambda:0)]):
            self.assertFalse(validate_image_quality(photo,min_sharpness=35,allow_editorial_detail=True)[0])


class ReviewedSourceFrameTests(unittest.TestCase):
    def test_square_template_footer_may_start_at_half_height(self):
        image=np.random.default_rng(6).integers(0,256,(1080,1080,3),dtype=np.uint8)
        badge=(452,568,632,610);title=(80,640,990,720);credit=(350,990,730,1038)
        boxes=SourceTextBoxes([badge,title,credit],text_labels={badge:'NETFLIX NEWS',title:'THE RIVER returns to Netflix',credit:"WHAT'S ON NETFLIX"},text_confidences={badge:.99,title:.99,credit:.99})
        profile={'credit_pattern':'news|what.?s on netflix','allow_edge_zoom':True,'footer_start_fraction':.5}
        detector=MagicMock();detector.detectMultiScale.return_value=[]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
            kept,top,bottom=extract_editorial_photo(image,boxes,profile,'THE RIVER returns to Netflix.')
        self.assertEqual(top,0);self.assertLess(bottom,568);self.assertGreaterEqual(bottom,450)
        np.testing.assert_array_equal(kept,image[:bottom])
        unknown=(300,400,800,450);boxes.append(unknown);boxes.text_labels[unknown]='UNREVIEWED'
        with self.assertRaisesRegex(ValueError,'overlaps the subject'):extract_editorial_photo(image,boxes,profile)

    def test_tiny_corner_gets_a_safe_owned_wordmark_instead_of_a_layout_failure(self):
        image=np.random.default_rng(7).integers(0,256,(1350,1080,3),dtype=np.uint8)
        footer=(80,1060,940,1200)
        boxes=SourceTextBoxes([footer],suspected_marks=[(20,20,60,140)],text_labels={footer:'Aurora Lane releases a new song'},text_confidences={footer:.99})
        profile={'credit_pattern':'billboard','allow_edge_zoom':True,'cover_corner_branding':True,'footer_fraction':.72}
        detector=MagicMock();detector.detectMultiScale.return_value=[]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
            photo,top,bottom,review=prepare_editorial_photo(image,boxes,profile,'Aurora Lane releases a new song.')
        caption='Aurora Lane releases a new song.'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'poster.jpg'
            render_final_poster(photo,format_balanced_overlay(caption.rstrip('.')),caption=caption,dest_page_name='MUSIC STORE',output_path=path,source_checked=True,source_corner_review=review)
            manifest=verify_publishable_poster(path,caption)
            self.assertTrue(manifest['source_corner_replacement']['brand_bounds'])

    def test_recognized_covered_seal_is_still_a_publisher_anchor_for_short_names(self):
        image=np.random.default_rng(11).integers(0,256,(1350,1080,3),dtype=np.uint8)
        seal=(12,12,154,152);footer=(80,1060,940,1200)
        boxes=SourceTextBoxes([seal,footer],text_labels={seal:'b',footer:'BTS V shows life on the road'},text_confidences={seal:.99,footer:.99})
        profile={'credit_pattern':'^b$','allow_edge_zoom':True,'cover_corner_branding':True,'footer_fraction':.72}
        detector=MagicMock();detector.detectMultiScale.return_value=[]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
            photo,top,bottom,review=prepare_editorial_photo(image,boxes,profile,'V gives ARMY a view of BTS.')
        self.assertTrue(review);np.testing.assert_array_equal(photo,image[:bottom])
        boxes.text_labels[seal]='unknown'
        with self.assertRaisesRegex(ValueError,'publisher anchor'):
            prepare_editorial_photo(image,boxes,profile,'V gives ARMY a view of BTS.')


class CoreEventRecoveryTests(unittest.TestCase):
    def test_post_production_and_character_look_are_complete_events(self):
        examples=[('THE RIVER MOVIE is officially in post production, bringing the cast together for one final chapter.','THE RIVER MOVIE is officially in post production'),
            ("Daniel Craig transforms into Uncle Andrew in THE RIVER, with the trailer revealing his magician.","Daniel Craig transforms into Uncle Andrew in THE RIVER")]
        for source,headline in examples:
            with self.subTest(source=source):self.assertEqual(replacement_payload(source,content_topic='film')['headline'],headline)
        result=replacement_payload("'Alicia's Law' is a new Mexican adaptation of the hit American series, bringing fresh courtroom drama to Netflix.",content_topic='film')
        self.assertEqual(result['headline'],"'Alicia's Law' is a new Mexican adaptation of the hit American series")

    def test_location_preamble_uses_main_observation_without_question_bait(self):
        source='WHAT WAS CLINGING TO THIS FISH UNDERWATER?!\nDuring a NOAA expedition in the Samoa Basin, a grenadier fish was observed with an isopod parasite attached to its body.\nResearchers filmed the deep-sea fish beneath the Pacific Ocean.'
        result=replacement_payload(source,content_topic='ocean',headline_accept=lambda t:len(t)<95)
        self.assertEqual(result['headline'],'A grenadier fish was observed with an isopod parasite attached to its body')
        self.assertNotIn('?',result['rewritten_caption'])

    def test_reported_funding_request_preserves_amount_scope_and_uncertainty(self):
        source="Defense Secretary Pete Hegseth said the Pentagon is seeking roughly 50 billion dollars, as a one-time investment, to mass-produce drones and other autonomous systems."
        result=replacement_payload(source,content_topic='military',headline_accept=lambda t:headline_fits_poster(t,max_lines=4))
        self.assertEqual(result['headline'],'Pentagon seeks roughly 50 billion dollars to mass-produce drones and other autonomous systems, Hegseth says')
        self.assertIn('one-time investment',result['rewritten_caption'])
        self.assertNotIn('approved',result['headline'])

    def test_named_pair_retains_both_titles_and_release_details(self):
        source="Two more beloved series, the romantic comedy 'Temperature of Love' and the thrilling drama 'Remember', are officially heading to Netflix US on October 30th."
        result=replacement_payload(source,content_topic='film',headline_accept=lambda t:headline_fits_poster(t,max_lines=4))
        self.assertEqual(result['headline'],"'Temperature of Love' and 'Remember' are officially heading to Netflix US on October 30th")

    def test_vague_narration_and_quoted_verbs_cannot_be_complete_event_hooks(self):
        for text in ['Think about this for a second','The Pentagon just signaled that era is ending','The number it put on the table is staggering']:
            self.assertFalse(headline_is_usable(text))
        from modules.editorial_facts import complete_event_hooks
        self.assertEqual(complete_event_hooks("The title 'Life Is Strange' with two new characters, with a debut next year.",'film'),[])


if __name__=='__main__':unittest.main()
