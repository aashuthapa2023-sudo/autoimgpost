"""Hourly receipts and detailed entertainment posts without filler or unsafe media."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from modules.cadence import publication_wait
from modules.content_quality import channel_accepts_post
from modules.ingestion import _select_photo_from_attachment
from modules.llm_transformer import clean_and_deduplicate_source_caption, format_balanced_overlay
from modules.poster_engine import headline_display_words, headline_fits_poster, render_final_poster
from modules.poster_quality import verify_publishable_poster
from modules.source_replacement import replacement_payload


class HourlyReceiptTests(unittest.TestCase):
    channel={'post_interval_hours':1,'cadence_mode':'hourly_slots'}

    def test_setup_jitter_does_not_lose_next_hour(self):
        last=20*3600+5*60+20
        self.assertEqual(publication_wait(self.channel,last,21*3600+3*60),0)
        self.assertGreater(publication_wait({'post_interval_hours':1},last,21*3600+3*60),0)

    def test_receipt_in_same_hour_cannot_publish_twice(self):
        self.assertEqual(publication_wait(self.channel,20*3600+120,20*3600+3500),100)

    def test_late_receipt_has_45_minute_guard(self):
        last=20*3600+58*60
        self.assertEqual(publication_wait(self.channel,last,21*3600+3*60),40*60)
        self.assertEqual(publication_wait(self.channel,last,21*3600+43*60),0)

    def test_first_receipt_and_day_rollover(self):
        self.assertEqual(publication_wait(self.channel,0,1000),0)
        self.assertEqual(publication_wait(self.channel,23*3600+120,24*3600+120),0)

    def test_two_hour_pages_keep_existing_interval(self):
        ch={'post_interval_hours':2,'cadence_mode':'hourly_slots'}
        self.assertEqual(publication_wait(ch,10000,13599),3481)
        self.assertEqual(publication_wait(ch,10000,17080),0)


class EntertainmentFactsTests(unittest.TestCase):
    channel={'content_topic':'us_entertainment'}

    def caption(self,source):
        return clean_and_deduplicate_source_caption(source,channel_name='Music Store',content_topic='us_entertainment')

    def test_artist_news_without_literal_music_word_is_eligible(self):
        for source in ['Britney Spears praised Janet Jackson in a new statement.',
                       '50 Cent trolled Diddy after his reported prison transfer.',
                       'Taylor Swift wore a gold dress to the Academy Museum Gala.',
                       'A new Hollywood documentary has opened in theaters.']:
            self.assertTrue(channel_accepts_post(self.channel,{'caption':source}))
        self.assertFalse(channel_accepts_post({'content_topic':'music'},{'caption':'A Hollywood actor has died.'}))

    def test_broad_publisher_is_not_a_license_for_off_topic_or_shopping(self):
        for source in ['A turtle has died after a long illness.',
                       'A Canadian military base has caught fire.',
                       'A nanny earns extra income from social media.',
                       'A hiring manager has shared resume advice.',
                       'Shop these Bogg bags inspired by Taylor Swift.']:
            self.assertFalse(channel_accepts_post(self.channel,{'caption':source}))

    def test_distinct_source_detail_exceeds_old_cap_without_padding(self):
        facts=[
            'Aurora Lane released her new album on Friday after recording the collection in Nashville with a team of longtime collaborators.',
            'The singer wrote twelve songs for the project and worked with producer Alice Harper during sessions that began last summer.',
            'The first single reached number four on the Billboard chart and features a guest performance from guitarist David Stone.',
            'Her upcoming concert tour opens in Chicago next month before visiting theaters in New York, Los Angeles and several other cities.',
            'Lane said the record draws on her childhood memories and includes acoustic arrangements performed by members of her touring band.'
        ]
        result=self.caption(' '.join(facts));body=result.split('\n\n#')[0]
        self.assertGreater(len(body.split()),80);self.assertLessEqual(len(body.split()),160)
        for fact in facts:self.assertEqual(body.count(fact),1)
        self.assertIn(facts[0]+'\n\n'+facts[1],result)

    def test_duplicate_title_is_replaced_by_complete_fact(self):
        result=self.caption('Taylor Swift wore a gold dress. Taylor Swift wore a gold dress at the Academy Museum Gala. 📷: Getty Images\nClick the link for more. https://example.com')
        self.assertEqual(result.count('Taylor Swift'),1)
        self.assertIn('Academy Museum Gala',result)
        self.assertNotIn('Getty',result);self.assertNotIn('Click',result)

    def test_overlong_fact_cannot_erase_usable_lead(self):
        lead='Taylor Swift released her new album on Friday.'
        long=lead[:-1]+' with '+' '.join(['additional']*170)+'.'
        self.assertIn(lead,self.caption(lead+' '+long))

    def test_short_source_stays_brief_and_qualifiers_remain(self):
        source='Drake reportedly faces a lawsuit over a song. Has a verdict been reached?'
        result=self.caption(source)
        self.assertIn('reportedly faces a lawsuit',result)
        self.assertLess(len(result.split()),30)
        self.assertNotIn('verdict',result)

    def test_quotes_are_not_cut_into_anonymous_headlines_or_half_captions(self):
        source='Taylor Swift released a new album on Friday.\n"We recorded the songs in Nashville. The sessions took place last summer," Swift said.\nThe album includes twelve songs.'
        result=self.caption(source)
        self.assertEqual(result.count('"')%2,0)
        self.assertIn('The sessions took place last summer," Swift said.',result)
        from modules.llm_transformer import headline_is_usable
        for title in ['Then I would be hidden behind the wide camera','"I have not spoken to Johnny in years','The show is bringing back its most iconic item']:
            self.assertFalse(headline_is_usable(title))
        payload=replacement_payload(source,content_topic='us_entertainment')
        self.assertEqual(payload['headline'],'Taylor Swift released a new album on Friday')

    def test_explicit_season_reference_keeps_followup_renewal_uncertainty(self):
        source='Finished your binge of The River Season 4? The political thriller returned to Netflix this week, but the path to Season 5 looks different.\nNetflix is waiting on performance data before making an official call.'
        payload=replacement_payload(source,content_topic='screen')
        self.assertEqual(payload['headline'],'The River Season 4 returned to Netflix this week')
        self.assertIn('waiting on performance data',payload['rewritten_caption'])
        self.assertNotIn('renewed',payload['headline'])

    def test_quoted_film_title_is_not_confused_with_anonymous_you(self):
        from modules.llm_transformer import headline_is_usable
        title='"You Can See Everything" has generated $15 million over its opening weekend'
        self.assertTrue(headline_is_usable(title))
        source=title+'. The documentary opened in theaters on Friday.'
        self.assertEqual(replacement_payload(source,content_topic='us_entertainment')['headline'],title)

    def test_ocean_event_precedes_geographic_background_and_drops_source_promotion(self):
        source="On July 23, 2026, orcas damaged the rudder of the sailing yacht Idem off Estaca de Bares in Galicia, Spain, and it sank 1.3 nautical miles from the coast. The two crew were rescued by a nearby motorboat. Spain's sea rescue service logged four orca incidents with yachts within a few hours.\nEstaca de Bares is the northernmost point of the Iberian Peninsula.\nFollow Blue Depths for more real ocean moments."
        payload=replacement_payload(source,content_topic='ocean')
        self.assertEqual(payload['headline'],"Orcas damaged yacht Idem's rudder off Spain; the yacht sank")
        self.assertIn('two crew were rescued',payload['rewritten_caption'])
        self.assertNotIn('Follow',payload['rewritten_caption'])

    def test_hype_and_fragments_cannot_replace_news_facts(self):
        from modules.llm_transformer import headline_is_usable
        self.assertFalse(headline_is_usable("Nathan Fielder's documentary has everyone talking"))
        source='Taylor Swift released a new album. But how do you even begin to explain the whole... thing? These five essential TV episodes are a good place to start.'
        self.assertNotIn('explain',self.caption(source))
        self.assertNotIn('place to start',self.caption(source))

    def test_red_carpet_event_drops_only_optional_anniversary_tail(self):
        source='Jessica Biel and Justin Timberlake were among the stars who walked the red carpet at the sixth annual Academy Museum Gala, just a few weeks after celebrating their 14th wedding anniversary.'
        payload=replacement_payload(source,content_topic='us_entertainment',headline_accept=lambda t:headline_fits_poster(t,max_lines=4,headline_case='source'))
        self.assertEqual(payload['headline'],'Jessica Biel and Justin Timberlake walked the red carpet at the sixth annual Academy Museum Gala')
        self.assertIn('14th wedding anniversary',payload['rewritten_caption'])


class NativePhotoSelectionTests(unittest.TestCase):
    def test_largest_variant_stays_bound_to_same_photo(self):
        first={'__typename':'Photo','id':'123456789',
               'large_image':{'uri':'https://cdn.example/small.jpg','width':650,'height':430},
               'photo_image':{'uri':'https://cdn.example/native.jpg','width':1600,'height':1000}}
        second={'__typename':'Photo','id':'987654321','image':{'uri':'https://cdn.example/other.jpg','width':4000,'height':4000}}
        self.assertEqual(_select_photo_from_attachment({'subattachments':{'nodes':[first,second]}}),
                         ('123456789','https://cdn.example/native.jpg'))

    def test_unknown_dimensions_preserve_priority_and_video_is_excluded(self):
        photo={'__typename':'Photo','id':'123456789','large_image':{'uri':'https://cdn.example/large.jpg'},
               'image':{'uri':'https://cdn.example/small.jpg','width':'1600','height':True}}
        self.assertEqual(_select_photo_from_attachment(photo)[1],'https://cdn.example/large.jpg')
        self.assertIsNone(_select_photo_from_attachment({**photo,'__typename':'Video'}))


class EntertainmentLayoutTests(unittest.TestCase):
    def test_preview_and_render_preserve_names_case_and_centered_safe_bounds(self):
        headline='Taylor Swift released a new album on Friday'
        overlay=format_balanced_overlay(headline,preserve_case=True)
        self.assertEqual(' '.join(word for word,_ in headline_display_words(headline,preserve_case=True)),headline)
        style={'headline_case':'source','edition_label':'U.S. ENTERTAINMENT','max_lines':4,
               'panel_color':'#10131B','safe_margin':64}
        self.assertTrue(headline_fits_poster(headline,**style))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'poster.jpg';caption=headline+'.'
            render_final_poster(base_img=np.full((1000,1300,3),95,np.uint8),overlay_lines=overlay,
                caption=caption,dest_page_name='MUSIC STORE',source_checked=True,output_path=path,**style)
            manifest=verify_publishable_poster(path,caption)
            self.assertEqual(manifest['headline'],headline)
            self.assertEqual(manifest['size'],[1080,1350])
            self.assertGreaterEqual(manifest['font_size'],68)
            self.assertLess(manifest['edition_bounds'][3],manifest['text_bounds'][0][1])
            for left,top,right,bottom in manifest['text_bounds']:
                self.assertAlmostEqual((left+right)/2,540,delta=1)
                self.assertGreaterEqual(left,64);self.assertLessEqual(right,1016)
            report=path.with_suffix('.quality.json');manifest['edition_bounds'][2]=1081
            report.write_text(json.dumps(manifest),encoding='utf8')
            with self.assertRaises(ValueError):verify_publishable_poster(path,caption)
