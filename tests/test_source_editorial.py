import unittest
from unittest.mock import patch,MagicMock
import numpy as np
from modules.image_cleaner import SourceTextBoxes
from modules.source_editorial import extract_editorial_photo,source_profile
from modules.source_replacement import replacement_payload

class EditorialSourceTests(unittest.TestCase):
 def test_repeated_uniform_labels_are_kept_as_one_photographed_row(self):
  boxes=self.boxes([((80,250,200,300),'थुनुवा'),((400,250,520,300),'थुनुवा'),((310,720,490,770),'NEWS')])
  boxes.suspected_rows=[(80,250,520,300)]
  profile=dict(self.profile,scene_labels=['थुनुवा'],allow_edge_zoom=True,header_max_fraction=.35)
  photo,top,bottom=extract_editorial_photo(self.image,boxes,profile,'News about an arrest')
  self.assertEqual(top,0);np.testing.assert_array_equal(photo[250:300],self.image[250:300])
 def test_stage_hook_preserves_negation_without_guessing_a_fall(self):
  source='Celine Dion has been in the game long enough to know that a little stage mishap isn’t going to stop the show.'
  payload=replacement_payload(source,language='en',content_topic='music')
  self.assertIn("isn't going to stop the show",payload['headline']);self.assertNotIn('falls',payload['headline'].lower())
 def test_rating_hook_keeps_title_score_and_rating_source(self):
  caption='Ben Affleck’s ANIMALS currently holds a 42% critics score on Rotten Tomatoes, giving the new Netflix thriller a Rotten rating shortly after its release.'
  payload=replacement_payload(caption,language='en',content_topic='entertainment')
  self.assertEqual(payload['headline'],"Ben Affleck's ANIMALS currently holds a 42% critics score on Rotten Tomatoes")
 def test_streaming_hook_keeps_complete_fact_before_plot(self):
  caption='ANIMALS is now officially streaming on Netflix, starring Ben Affleck and Kerry Washington as a married couple whose seemingly perfect life is shattered when their son is kidnapped.'
  self.assertEqual(replacement_payload(caption,language='en',content_topic='entertainment')['headline'],'ANIMALS is now officially streaming on Netflix')
 def test_renewal_hook_names_show_and_new_season_before_premiere_comparison(self):
  caption=('THE HUNTING WIVES has officially been renewed for Season 3 on Netflix, more than a month before Season 2 even premieres on November 26.\n'
           'Season 3 will consist of another eight episodes, although Netflix has not yet announced its release date or returning cast.')
  payload=replacement_payload(caption,language='en',content_topic='entertainment')
  self.assertEqual(payload['headline'],'THE HUNTING WIVES has officially been renewed for Season 3 on Netflix')
  self.assertIn('November 26',payload['rewritten_caption'])
  self.assertIn('not yet announced',payload['rewritten_caption'])
  self.assertEqual(payload['rewritten_caption'].count('been renewed'),1)
 def test_renewal_comparison_never_converts_qualified_event_into_confirmation(self):
  caption='THE HUNTING WIVES may have been renewed for Season 3 on Netflix, more than a month before Season 2 premieres.'
  payload=replacement_payload(caption,language='en',content_topic='entertainment')
  self.assertIn('may',payload['headline'])
 def test_release_hook_keeps_full_date_and_title_without_appended_synopsis(self):
  caption="Netflix has set a November 12, 2026 release date for 'Never Surrender', a gritty new Indonesian home invasion thriller starring Lukman Sardi."
  payload=replacement_payload(caption,language='en',content_topic='film')
  self.assertEqual(payload['headline'],"Netflix has set a November 12, 2026 release date for 'Never Surrender'")
  self.assertEqual(payload['rewritten_caption'].count('release date'),1)
  self.assertIn('Lukman Sardi',payload['rewritten_caption'])
 def test_music_ranking_gets_complete_hook_without_needing_photo_text(self):
  caption='The 25 Best VMAs Performances of All Time: Critics’ Picks\n\nThe best VMAs performances of all time, from Madonna to Michael Jackson to Beyonce at the MTV Video Music Awards.'
  payload=replacement_payload(caption,language='en',content_topic='music')
  self.assertEqual(payload['headline'],'Critics pick the 25 best VMAs performances of all time')
  self.assertIn('Madonna',payload['rewritten_caption'])
 def test_reviewed_zoom_uses_caption_subject_when_news_badge_is_missing(self):
  boxes=self.boxes([((40,740,760,820),'ANIMALS starring Ben Affleck')])
  profile=dict(self.profile,allow_edge_zoom=True)
  photo,top,bottom=extract_editorial_photo(self.image,boxes,profile,'ANIMALS releases on Netflix')
  self.assertEqual(bottom,728);np.testing.assert_array_equal(photo,self.image[:728])
  with self.assertRaisesRegex(ValueError,'verified publisher anchor'):
   extract_editorial_photo(self.image,boxes,profile,'A completely different story')
 def test_release_hook_keeps_title_season_platform_and_caption_date(self):
  payload=replacement_payload('THE EMPRESS Season 3 officially releases on Netflix on November 12, bringing Elisabeth and Franz back for the final chapter.',language='en',content_topic='entertainment')
  self.assertEqual(payload['headline'],'THE EMPRESS Season 3 officially releases on Netflix on November 12')
 def test_cover_hook_keeps_complete_intro_and_removes_emoji(self):
  payload=replacement_payload("Pitbull is music's global party starter 🌎🎉 How Mr. Worldwide beat the odds, reset his career and keeps winning new fans.",language='en',content_topic='music')
  self.assertEqual(payload['headline'],"Pitbull is music's global party starter")
 def test_petry_hook_keeps_named_person_sacrifice_and_saved_rangers(self):
  caption='An enemy grenade landed next to three Army Rangers. Leroy Petry grabbed it with his bare hand and threw it back. He lost his hand and saved his fellow Army Rangers.'
  payload=replacement_payload(caption,language='en',content_topic='military')
  self.assertEqual(payload['headline'],'Leroy Petry lost his hand saving fellow Army Rangers from a grenade')
 def test_military_headline_keeps_complete_named_deployment_clause(self):
  caption='During the exercise Keen Sword, Marines will field the NMESIS anti-ship missile system on Yonaguni, Japan. NMESIS, the Navy-Marine Expeditionary Ship Interdiction System, is a ground-based launcher.'
  payload=replacement_payload(caption,language='en',content_topic='military')
  self.assertEqual(payload['headline'],'Marines will field the NMESIS anti-ship missile system on Yonaguni')
 def test_configured_footer_removes_short_fragment_only_with_publisher_anchor(self):
  boxes=self.boxes([((310,720,490,770),'NEWS'),((80,900,130,940),'Say')])
  profile=dict(self.profile,footer_start_fraction=.65)
  photo,top,bottom=extract_editorial_photo(self.image,boxes,profile)
  self.assertEqual(bottom,708)
 def setUp(self):
  self.image=np.random.default_rng(49).integers(30,220,(1000,800,3),dtype=np.uint8)
  self.profile={'credit_pattern':r'news|himali','scene_labels':['परम्पराको','१५']}
 def boxes(self,items):
  return SourceTextBoxes([box for box,text in items],text_labels=dict(items),text_confidences={box:.99 for box,text in items})
 def test_gradient_footer_is_removed_without_erasing_subject_pixels(self):
  boxes=self.boxes([((310,720,490,770),'NEWS'),((50,810,740,890),'An original source headline')])
  photo,top,bottom=extract_editorial_photo(self.image,boxes,self.profile)
  self.assertEqual((top,bottom),(0,708));np.testing.assert_array_equal(photo,self.image[:708])
 def test_source_sign_lettering_is_retained_while_source_headline_is_removed(self):
  boxes=self.boxes([((180,200,310,240),'परम्पराको'),((310,720,490,770),'NEWS'),((50,810,740,890),'Source headline')])
  boxes.suspected_rows=[(180,200,550,242)]
  photo,top,bottom=extract_editorial_photo(self.image,boxes,self.profile)
  np.testing.assert_array_equal(photo[200:242],self.image[200:242])
 def test_whitelist_cannot_authorize_large_headline_over_the_subject(self):
  boxes=self.boxes([((80,200,760,420),'परम्पराको'),((310,720,490,770),'NEWS')])
  with self.assertRaises(ValueError):extract_editorial_photo(self.image,boxes,self.profile)
 def test_unrecognized_middle_watermark_is_rejected(self):
  boxes=self.boxes([((310,720,490,770),'NEWS')]);boxes.suspected_rows=[(50,380,740,410)]
  with self.assertRaisesRegex(ValueError,'overlaps the subject'):extract_editorial_photo(self.image,boxes,self.profile)
 def test_mid_photo_publisher_lettering_is_never_a_scene_exception(self):
  profile={'credit_pattern':'himali','scene_labels':['HIMALI']}
  with self.assertRaisesRegex(ValueError,'overlaps the subject'):
   extract_editorial_photo(self.image,self.boxes([((300,300,480,350),'HIMALI')]),profile)
 def test_detector_only_waves_do_not_authorize_edge_crop(self):
  boxes=SourceTextBoxes([],suspected_rows=[(20,720,760,780)])
  with self.assertRaisesRegex(ValueError,'publisher anchor'):extract_editorial_photo(self.image,boxes,self.profile)
 def test_crop_cannot_cut_a_detected_face(self):
  boxes=self.boxes([((310,720,490,770),'NEWS')])
  detector=MagicMock();detector.detectMultiScale.return_value=[(250,660,90,100)]
  with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector),self.assertRaisesRegex(ValueError,'crop a face'):
   extract_editorial_photo(self.image,boxes,self.profile)
 def test_text_free_photo_keeps_its_entire_original_frame(self):
  photo,top,bottom=extract_editorial_photo(self.image,SourceTextBoxes(),self.profile)
  self.assertEqual((top,bottom),(0,1000));np.testing.assert_array_equal(photo,self.image)
 def test_explicit_header_and_footer_keep_faces_and_remove_all_event_graphics(self):
  profile={'credit_pattern':'billboard','header_fraction':.17,'footer_fraction':.72,'scene_labels':[]}
  image=np.random.default_rng(9).integers(30,220,(1350,1080,3),dtype=np.uint8)
  boxes=self.boxes([((400,30,680,90),'billboard'),((300,1200,780,1260),'LIVE AT FAENA THEATER')])
  photo,top,bottom=extract_editorial_photo(image,boxes,profile)
  self.assertEqual((top,bottom),(230,972));np.testing.assert_array_equal(photo,image[230:972])
 def test_source_profiles_do_not_cross_channels_or_foreign_domains(self):
  channel={'source_cleanup_profiles':{'example':self.profile}}
  self.assertEqual(source_profile(channel,{'source_page_url':'https://www.facebook.com/example/'}),self.profile)
  self.assertIsNone(source_profile({}, {'source_page_url':'https://www.facebook.com/example/'}))
  self.assertIsNone(source_profile(channel,{'source_page_url':'https://other.example/example'}))
 def test_repeated_event_branding_becomes_complete_source_supported_title(self):
  raw='ONE NIGHT ONLY 🚨 Billboard presents an intimate Santos Bravos show at Billboard Latin Music Week 2026 at Faena Theater in Miami.'
  data=replacement_payload(raw,language='en',channel_name='Music Store',channel_id='Music Store',content_topic='music')
  self.assertEqual(data['headline'],'Santos Bravos show at Billboard Latin Music Week 2026 at Faena Theater in Miami')
 def test_editorial_tail_can_be_removed_without_changing_the_concrete_fact(self):
  raw="More than a decade after making that statement, Cameron Diaz has returned to acting with projects including Netflix's BACK IN ACTION, while her old message about choosing natural aging still feels consistent with how she speaks."
  data=replacement_payload(raw,language='en',content_topic='film')
  self.assertEqual(data['headline'],"Cameron Diaz has returned to acting with projects including Netflix's BACK IN ACTION")
 def test_short_nepali_fact_keeps_native_page_language(self):
  raw='गगनको सर्वसम्मत सभापति बन्ने सपना अधुरै!\nनेपाली कांग्रेसको सभापतिमा प्रत्यक्ष प्रतिस्पर्धा हुने भएको छ।'
  data=replacement_payload(raw,language='ne',content_topic='news')
  self.assertEqual(data['headline'],'गगनको सर्वसम्मत सभापति बन्ने सपना अधुरै')
