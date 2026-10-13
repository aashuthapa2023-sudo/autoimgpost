"""Recover complete source events without weakening publication quality gates."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import numpy as np
from modules.editorial_facts import complete_event_hooks
from modules.image_cleaner import SourceTextBoxes
from modules.llm_transformer import format_balanced_overlay,headline_is_usable,generate_preserved_card_payload
from modules.poster_engine import (headline_fits_poster,headline_display_words,
    _select_title_rows,render_final_poster)
from modules.poster_quality import verify_publishable_poster
from modules.source_editorial import prepare_editorial_photo,cover_intersects_frontal_face
from modules.source_replacement import replacement_payload,replacement_headline_fits,_replacement_title_rows
from modules.source_artwork import inspect_film_artwork
from modules.source_card import render_preserved_source_card


class CompleteEventTests(unittest.TestCase):
    def test_optional_tail_keeps_complete_event_and_full_caption_fact_once(self):
        source='THE RIVER Season 4 is now well into production at Netflix, with filming scheduled to wrap on November 20 before the series returns in 2027.'
        title='THE RIVER Season 4 is now well into production at Netflix'
        self.assertIn((title,[source]),complete_event_hooks(source,'entertainment'))
        payload=replacement_payload(source,content_topic='entertainment',headline_accept=lambda t:len(t)<80)
        self.assertEqual(payload['headline'],title)
        self.assertEqual(payload['rewritten_caption'].count('filming scheduled'),1)
        self.assertEqual(payload['rewritten_caption'].count('THE RIVER'),1)

    def test_comma_cut_cannot_discard_uncertainty_negation_or_correction(self):
        for tail in ['with the report later refuted','and may return instead','with no release confirmed']:
            source='THE RIVER returns to Netflix in 2027, '+tail+'.'
            titles=[t for t,s in complete_event_hooks(source,'entertainment')]
            self.assertNotIn('THE RIVER returns to Netflix in 2027',titles)

    def test_quoted_comma_and_possessive_are_not_mistaken_for_tail_boundaries(self):
        source="The Beatles' 'Rubber Soul' reenters the Billboard 200 at No. 4, thanks to its anniversary release."
        self.assertIn("The Beatles' 'Rubber Soul' reenters the Billboard 200 at No. 4",[t for t,s in complete_event_hooks(source,'music')])
        source='THE RIVER returns with "Life, and the Sea" on Netflix.'
        self.assertNotIn('THE RIVER returns with "Life',[t for t,s in complete_event_hooks(source,'entertainment')])

    def test_reporting_clause_retains_named_attribution_and_object(self):
        source='Catherine Vautrin told reporters on Monday that France will begin training Ukrainian pilots on Rafale combat aircraft.'
        hooks=complete_event_hooks(source,'military')
        self.assertIn(('Catherine Vautrin says France will begin training Ukrainian pilots on Rafale combat aircraft',[source]),hooks)

    def test_industry_context_is_taken_from_source_without_filler(self):
        source='Aero Systems says its ejection seats have saved 7,837 lives. The company supplies ejection seats to 93 air forces.'
        title,support=complete_event_hooks(source,'military')[0]
        self.assertIn('7,837 lives',title)
        self.assertIn('93 air forces',' '.join(support))
        self.assertEqual(len(support),2)

    def test_animal_observation_does_not_change_species_or_year(self):
        source='An extraordinarily rare all-white killer whale captured the attention of researchers in 2012 when scientists documented a mature male orca near Russia.'
        titles=[t for t,s in complete_event_hooks(source,'ocean')]
        self.assertIn('Rare all-white killer whale documented near Russia in 2012',titles)
        source=source.replace('all-white killer whale','all-white false killer whale')
        self.assertFalse(any(t.startswith('Rare ') for t,s in complete_event_hooks(source,'ocean')))

    def test_anonymous_sequel_and_question_teaser_are_not_display_hooks(self):
        self.assertEqual(complete_event_hooks('It returns on Netflix in 2027.','entertainment'),[])
        self.assertFalse(headline_is_usable('What is better than a new song? Two new songs'))


class ActualDisplayFitTests(unittest.TestCase):
    def test_uppercase_preview_matches_final_display_width(self):
        title='Art of Play says it has reached out to the singer directly in hopes of clearing up the misunderstanding'
        # The old lowercase preview accepted this; its uppercase display cannot
        # fit three lines at the required font size.
        _select_title_rows([(w,'white') for w in title.split()],'en',(255,200,59),{})
        self.assertFalse(headline_fits_poster(title))
        with self.assertRaises(ValueError):_select_title_rows(headline_display_words(title),'en',(255,200,59),{})

    def test_four_line_setting_is_honored_without_reducing_readability(self):
        title='Art of Play has released a new statement after Clarkson accused the shop of giving her the Pretty Woman treatment'
        self.assertFalse(headline_fits_poster(title,max_lines=3))
        self.assertTrue(headline_fits_poster(title,max_lines=4))
        size,rows=_select_title_rows(headline_display_words(title),'en',(255,200,59),{'max_lines':4})
        self.assertEqual(len(rows),4);self.assertGreaterEqual(size,68)

    def test_ocean_preview_uses_same_uppercase_tokens_as_replacement(self):
        review={'panel_top':960}
        for title in ['Scientists filmed a rare whale near Hawaii','An exceptionally important scientific research team documented remarkable marine animals beside an extraordinarily large underwater volcanic formation']:
            with self.subTest(title=title):
                try:_replacement_title_rows(headline_display_words(title),review,(255,200,59));fits=True
                except ValueError:fits=False
                self.assertEqual(replacement_headline_fits(title,review),fits)


class LocalizedCornerTests(unittest.TestCase):
    def photo(self):return np.random.default_rng(7).integers(0,255,(1350,1080,3),dtype=np.uint8)
    def evidence(self):
        footer=(180,1060,920,1250)
        return SourceTextBoxes([footer],suspected_marks=[(10,10,150,150)],
            text_labels={footer:'Aurora Lane releases a new song'},text_confidences={footer:.99})
    def profile(self):return {'credit_pattern':'billboard','allow_edge_zoom':True,'cover_corner_branding':True,'footer_fraction':.72,'min_retained_fraction':.35}

    def test_cover_preserves_native_pixels_and_replaces_only_reviewed_corner(self):
        image=self.photo();detector=MagicMock();detector.detectMultiScale.return_value=[]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
            kept,top,bottom,review=prepare_editorial_photo(image,self.evidence(),self.profile(),'Aurora Lane releases a new song.')
        np.testing.assert_array_equal(kept,image[:bottom]);self.assertEqual(top,0)
        self.assertEqual(review['native_sha256'],hashlib.sha256(kept.tobytes()).hexdigest())
        review['render_input_sha256']=review['native_sha256']
        caption='Aurora Lane releases a new song.'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'poster.jpg'
            options=dict(base_img=kept,overlay_lines=format_balanced_overlay(caption.rstrip('.')),caption=caption,
                dest_page_name='Music Store',source_checked=True,source_corner_review=review,output_path=path)
            render_final_poster(**options);manifest=verify_publishable_poster(path,caption)
            self.assertTrue(manifest['source_corner_replacement'])
            report=path.with_suffix('.quality.json');manifest['source_corner_replacement']['cover_bounds']=[0,0,1,1]
            report.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'not fully covered'):verify_publishable_poster(path,caption)
            review['render_input_sha256']='changed'
            with self.assertRaisesRegex(ValueError,'changed'):render_final_poster(**options)

    def test_face_features_are_protected_but_empty_rectangle_corners_are_allowed(self):
        self.assertFalse(cover_intersects_frontal_face([0,0,158,160],[120,128,396,404]))
        self.assertTrue(cover_intersects_frontal_face([0,0,158,160],[50,50,220,220]))
        detector=MagicMock();detector.detectMultiScale.return_value=[(30,30,150,150)]
        with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector),self.assertRaisesRegex(ValueError,'hide a face'):
            prepare_editorial_photo(self.photo(),SourceTextBoxes([],suspected_marks=[(10,10,150,150)]),self.profile())

    def test_body_watermark_cannot_be_excused_by_corner_profile(self):
        with self.assertRaisesRegex(ValueError,'overlaps the subject'):
            prepare_editorial_photo(self.photo(),SourceTextBoxes([(200,350,600,410)],suspected_marks=[(10,10,150,150)]),self.profile())


class FilmArtworkTests(unittest.TestCase):
    def photo(self):return np.random.default_rng(8).integers(0,255,(1400,1000,3),dtype=np.uint8)
    def boxes(self):
        title=(140,900,860,1050)
        return SourceTextBoxes([title],text_labels={title:'THE RIVER'},text_confidences={title:.99})
    def test_named_released_artwork_remains_intact_without_second_headline(self):
        image=self.photo();caption='The first poster for THE RIVER has dropped. The trailer is coming tomorrow.'
        review=inspect_film_artwork(image,self.boxes(),caption)
        self.assertNotIn('tomorrow',review['caption_source'])
        self.assertEqual(review['caption_source'],'The first poster for THE RIVER has dropped.')
        payload=generate_preserved_card_payload(caption,review['headline'],content_topic='film',
            caption_source=review['caption_source'])
        self.assertNotIn('tomorrow',payload['rewritten_caption'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'poster.jpg'
            render_preserved_source_card(image,review,review['caption_source'],'HOLLYWOOD',path)
            manifest=verify_publishable_poster(path,review['caption_source'])
            self.assertEqual(manifest['layout_kind'],'preserved_source_card')
            self.assertEqual(len(manifest['text_bounds']),1)
            self.assertEqual(manifest['size'],[1080,1350])

    def test_mismatched_clipped_or_watermarked_artwork_is_not_preserved(self):
        image=self.photo();caption='The first poster for THE RIVER has dropped.'
        boxes=self.boxes();box=(10,50,300,110);boxes.append(box);boxes.text_labels[box]='PUBLISHER DAILY'
        for evidence,source in [(boxes,caption),(self.boxes(),caption.replace('THE RIVER','THE OCEAN')),
                (SourceTextBoxes([(0,900,860,1050)],text_labels={(0,900,860,1050):'THE RIVER'},text_confidences={(0,900,860,1050):.99}),caption)]:
            with self.subTest(source=source),self.assertRaises(ValueError):inspect_film_artwork(image,evidence,source)


if __name__=='__main__':unittest.main()
