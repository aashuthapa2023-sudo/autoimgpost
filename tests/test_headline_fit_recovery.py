"""Fit complete facts before compositing; never shrink type or cut a prefix."""
import tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import numpy as np
from modules.source_replacement import replacement_payload,replacement_headline_fits,render_source_replacement,review_source_replacement
from modules.poster_engine import headline_fits_poster,render_final_poster
from modules.poster_quality import verify_publishable_poster
from modules.image_cleaner import SourceTextBoxes
from modules.source_editorial import extract_editorial_photo
from modules.llm_transformer import generate_social_payload,format_balanced_overlay


class HeadlineFitRecoveryTests(unittest.TestCase):
    def test_long_first_fact_moves_to_complete_fitting_fact(self):
        source='Netflix has officially renewed the drama for Season 2, bringing an extensive cast together for the next installment. The Netflix drama returns for Season 2.'
        result=replacement_payload(source,headline_accept=lambda title:len(title)<60)
        self.assertEqual(result['headline'],'The Netflix drama returns for Season 2')
    def test_no_fitting_fact_is_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError,'no complete grounded headline'):
            replacement_payload('Netflix renewed the drama for Season 2.',content_topic='entertainment',headline_accept=lambda title:False)
    def test_short_octopus_observation_keeps_appearing_and_source_location(self):
        source='On October 9, 2026, the E/V Nautilus team filmed a camouflaged octopus appearing to pursue the green scaling lasers on their underwater vehicle, about 1,059 feet below the surface near Hawaii.'
        result=replacement_payload(source,content_topic='ocean',headline_accept=lambda title:len(title)<95)
        self.assertEqual(result['headline'],'Octopus filmed appearing to pursue green scaling lasers near Hawaii')
        self.assertEqual(result['rewritten_caption'].count('Nautilus'),1)
        self.assertIn('appearing',result['rewritten_caption'])
        with self.assertRaises(ValueError):replacement_payload(source.replace('team filmed','team did not film'),content_topic='ocean',headline_accept=lambda title:len(title)<95)
    def test_quoted_nepali_relief_statement_keeps_attribution(self):
        source='बुढीगण्डकी बाढीपीडितको उद्धार र राहतमा तीव्रता दिएका छौँ : गृहमन्त्री गुरुङ'
        result=replacement_payload(source,language='ne')
        self.assertIn('गृहमन्त्री गुरुङले',result['headline']);self.assertTrue(result['headline'].endswith('बताए'))
    def test_rapper_headline_names_teased_campaign_without_confirming_candidacy(self):
        source='Soulja Boy wants to take "Crank That" to the White House. The rapper teased a 2028 presidential run in an Instagram post, calling it "a bigger vision."'
        result=replacement_payload(source,content_topic='music')
        self.assertEqual(result['headline'],'Soulja Boy teases a 2028 presidential run')
    def test_missile_contract_hook_keeps_value_and_named_weapon(self):
        source='The U.S. Navy destroyers answered with the SM-3. This week, Raytheon announced a five-year contract worth $6.3 billion, with two more option years, to keep its production line turning out the Standard Missile-3 Block IB.'
        result=replacement_payload(source,content_topic='military')
        self.assertEqual(result['headline'],'Raytheon announces $6.3 billion SM-3 missile production contract')
        self.assertIn('two more option years',result['rewritten_caption'])
    def test_source_review_promotion_is_not_claimed_as_our_own_work(self):
        source="'Animals' has arrived on Netflix. The crime thriller follows a kidnapping. Our review breaks down the performances in the movie."
        result=replacement_payload(source,content_topic='film')
        self.assertNotIn('Our review',result['rewritten_caption'])
    def test_complete_season_heading_with_stray_comma_does_not_need_uncertain_ocr(self):
        source='BEAUTY IN BLACK Season 4 is officially on the way at Netflix,\n\nProduction is reportedly taking place in Atlanta. A release date has not been announced.'
        result=replacement_payload(source,content_topic='entertainment',headline_accept=lambda title:len(title)<95)
        self.assertEqual(result['headline'],'Netflix: BEAUTY IN BLACK Season 4 is officially on the way')
        self.assertNotIn('reportedly',result['headline'])
        self.assertNotIn('Netflix,',result['rewritten_caption'])
    def test_measured_fit_matches_final_renderer(self):
        photo=np.random.default_rng(1).integers(0,255,(700,1000,3),dtype=np.uint8)
        for title in ['Netflix renews the drama for Season 2','Extremelylongwordwithoutanybreaks'*6]:
            fits=headline_fits_poster(title,min_font_size=68)
            with tempfile.TemporaryDirectory() as directory:
                try:overlay=format_balanced_overlay(title)
                except ValueError:overlay=[[{'text':title,'type':'white'}]]
                options=dict(base_img=photo,overlay_lines=overlay,caption='Netflix renewed the drama for Season 2.',dest_page_name='TEST',source_checked=True,output_path=Path(directory)/'poster.jpg',min_font_size=68)
                if fits:
                    render_final_poster(**options)
                    self.assertGreaterEqual(verify_publishable_poster(options['output_path'],options['caption'])['font_size'],68)
                else:
                    with self.assertRaises(ValueError):render_final_poster(**options)
    def test_corner_logo_crop_uses_side_when_header_would_cut_forehead(self):
        photo=np.random.default_rng(1).integers(0,255,(1350,1080,3),dtype=np.uint8)
        footer=(150,1050,940,1250);boxes=SourceTextBoxes([footer],suspected_marks=[(11,11,155,155)],text_labels={footer:'Soulja Boy teases a 2028 presidential run'},text_confidences={footer:.99})
        profile={'credit_pattern':'billboard','allow_edge_zoom':True,'header_max_fraction':.24,'header_fraction':.17,'header_crop_padding':2,'footer_fraction':.72,'min_retained_fraction':.35,'corner_crop_max_fraction':.16}
        detector=MagicMock();detector.detectMultiScale.return_value=[(180,100,450,650)]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
            kept,top,bottom=extract_editorial_photo(photo,boxes,profile,'Soulja Boy teases a 2028 presidential run.')
        self.assertEqual(top,0);np.testing.assert_array_equal(kept,photo[:bottom,157:])
        detector.detectMultiScale.return_value=[(100,100,450,650)]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector),self.assertRaisesRegex(ValueError,'cut a face'):
            extract_editorial_photo(photo,boxes,profile,'Soulja Boy teases a 2028 presidential run.')
    def test_rewrite_rejects_a_valid_but_unfitting_model_headline(self):
        source='Netflix renewed the drama for Season 2.'
        response=MagicMock(status_code=200)
        response.json.return_value={'choices':[{'message':{'content':json.dumps({'headline':source.rstrip('.'),'rewritten_caption':source})}}]}
        with patch.dict('os.environ',{'GROQ_API_KEY':'test','GEMINI_API_KEY':'','OPENROUTER_API_KEY':''}),patch('modules.llm_transformer.requests.post',return_value=response):
            with self.assertRaises(ValueError):generate_social_payload(source,headline_accept=lambda title:False)


if __name__=='__main__':unittest.main()
