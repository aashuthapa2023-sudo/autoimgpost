import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import numpy as np
from modules.image_cleaner import SourceTextBoxes
from modules.source_editorial import extract_editorial_photo
from modules.source_replacement import replacement_payload,prepare_source_replacement,render_source_replacement,replacement_photo_region,_complete_caption_hooks
from modules.llm_transformer import check_source_grounding
from modules.content_quality import channel_accepts_post
from modules.poster_quality import verify_publishable_poster


class QualityRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.image=np.random.default_rng(26).integers(30,100,(1000,800,3),dtype=np.uint8)
 def boxes(self,items,marks=(),rows=()):
  return SourceTextBoxes([box for box,text in items],suspected_marks=list(marks),suspected_rows=list(rows),text_labels=dict(items),text_confidences={box:.99 for box,text in items})
 def test_reviewed_narrow_edge_crop_preserves_pixels_and_removes_footer(self):
  boxes=self.boxes([((300,780,500,820),'Frontline Diary')],marks=[(0,180,42,220)])
  profile={'credit_pattern':'frontline|diary','side_crop_max_fraction':.08,'footer_start_fraction':.65}
  detector=MagicMock();detector.detectMultiScale.return_value=[]
  with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
   photo,top,bottom=extract_editorial_photo(self.image,boxes,profile)
  self.assertEqual((top,bottom),(0,768));np.testing.assert_array_equal(photo,self.image[:768,50:])
  with self.assertRaisesRegex(ValueError,'overlaps the subject'):
   extract_editorial_photo(self.image,boxes,{'credit_pattern':'frontline|diary'})
 def test_side_crop_cannot_remove_a_face_or_a_wide_watermark(self):
  profile={'credit_pattern':'news','side_crop_max_fraction':.08}
  boxes=self.boxes([((300,780,500,820),'NEWS')],marks=[(0,180,42,220)])
  detector=MagicMock();detector.detectMultiScale.return_value=[(35,180,80,100)]
  with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector),self.assertRaisesRegex(ValueError,'cut a face'):
   extract_editorial_photo(self.image,boxes,profile)
  boxes.suspected_marks=[(0,180,180,220)]
  with self.assertRaisesRegex(ValueError,'overlaps the subject'):extract_editorial_photo(self.image,boxes,profile)
 def backdrop(self):
  items=[((x,y,x+60,y+28),name) for x,y,name in [(40,20,'tiff'),(200,20,'VISA'),(400,20,'Bell'),(600,20,'tiff'),(40,350,'tiff'),(200,350,'VISA'),(400,350,'Bell'),(600,350,'tiff'),(40,680,'tiff')]]
  profile={'credit_pattern':'billboard','event_backdrop_labels':{'tiff':['tiff'],'visa':['VISA'],'bell':['Bell']}}
  return items,profile
 def test_repeated_physical_sponsor_wall_is_kept_without_wiping(self):
  items,profile=self.backdrop();boxes=self.boxes(items,rows=[(0,350,720,384)])
  photo,top,bottom=extract_editorial_photo(self.image,boxes,profile)
  self.assertEqual((top,bottom),(0,1000));np.testing.assert_array_equal(photo,self.image)
 def test_backdrop_exception_requires_multiple_brands_and_rejects_unknown_text(self):
  items,profile=self.backdrop()
  for evidence in [items[:2],[(box,'tiff') for box,name in items],items+[((300,480,440,510),'Publisher')]]:
   with self.subTest(evidence=evidence),self.assertRaises(ValueError):extract_editorial_photo(self.image,self.boxes(evidence),profile)
  with self.assertRaisesRegex(ValueError,'outside the reviewed'):
   extract_editorial_photo(self.image,self.boxes(items,rows=[(100,500,650,540)]),profile)
 def test_caption_hook_uses_complete_romance_fact_without_ocr(self):
  caption='BREAKING: A new BRIDGERTON limited series following the romance of young Violet and Viscount Edmund Bridgerton is officially on the way at Netflix.'
  result=replacement_payload(caption,content_topic='entertainment')
  self.assertEqual(result['headline'],'Netflix’s new BRIDGERTON series follows young Violet and Viscount Edmund’s romance')
  self.assertEqual(result['rewritten_caption'].count('limited series'),1)
  self.assertEqual(_complete_caption_hooks(caption.replace('is officially','may be officially'),'entertainment'),[])
 def test_source_opinion_is_kept_as_attributed_opinion(self):
  source='Gene Simmons says actors and other celebrities should stop lecturing people about politics and focus on their art instead, arguing that the public does not need political guidance from wealthy entertainers.'
  data=replacement_payload(source,content_topic='entertainment')
  self.assertEqual(data['headline'],'Gene Simmons says celebrities should focus on their art instead of politics')
  self.assertIn('does not need',data['rewritten_caption'])
 def test_named_release_keeps_complete_date_without_promotional_review(self):
  source='Brad Bird’s new retrofuturistic noir, Ray Gunn (The Incredibles, The Iron Giant), is coming to Netflix on December 18, 2026, starring Sam Rockwell. Here’s why this is a must-watch in our full review:'
  data=replacement_payload(source,content_topic='film')
  self.assertEqual(data['headline'],'Brad Bird’s Ray Gunn is coming to Netflix on December 18, 2026')
  self.assertNotIn('full review',data['rewritten_caption'])
 def test_announcement_hook_does_not_repeat_source_title_in_caption(self):
  source='Nickelback Announces Dates For Huge 2027 Everything Under the Sun World Tour\nNickelback announced the dates for an extensive 2027 world arena tour in support of their upcoming "Everything Under the Sun" album; see the dates.'
  data=replacement_payload(source,content_topic='music')
  self.assertEqual(data['headline'],'Nickelback announces its 2027 Everything Under the Sun world tour')
  self.assertEqual(data['rewritten_caption'].count('Nickelback'),1)
  self.assertNotIn('see the dates',data['rewritten_caption'])
 def test_homecoming_hook_names_ship_and_duration_without_generic_filler(self):
  source='Just before noon on Thursday, the USS Abraham Lincoln slid up to the pier in San Diego. They had waited a long time. Redirected to the Middle East, the carrier ended up away from home for 322 days. The ship came home with no lives lost.'
  data=replacement_payload(source,content_topic='military')
  self.assertEqual(data['headline'],'USS Abraham Lincoln returns home after 322 days away')
  self.assertNotIn('They had waited',data['rewritten_caption'])
  self.assertEqual(_complete_caption_hooks(source.replace('The ship came home','The ship may come home'),'military'),[])
 def test_species_names_pass_ocean_filter_without_accepting_unrelated_topics(self):
  for species in ('beluga','belugas','narwhal','porpoise','dugong','manatee'):
   self.assertTrue(channel_accepts_post({'content_topic':'ocean'},{'caption':f'A {species} was rescued.'}))
  self.assertFalse(channel_accepts_post({'content_topic':'ocean'},{'caption':'Ocean’s Eleven is now streaming on Netflix.'}))
  self.assertFalse(channel_accepts_post({'content_topic':'ocean'},{'caption':'A Beluga cryptocurrency wallet was released.'}))
 def test_possessives_of_source_names_are_grounded_but_invented_names_are_not(self):
  self.assertTrue(check_source_grounding('Viscount Edmund’s romance will appear on Netflix.','Viscount Edmund has a romance in the new Netflix series.'))
  self.assertFalse(check_source_grounding('Viscount Edward’s romance will appear on Netflix.','Viscount Edmund has a romance in the new Netflix series.'))
 def test_replacement_header_crop_has_complete_proof_and_unchanged_subject_pixels(self):
  profile={'credit_pattern':'(?!)','allow_edge_zoom':True,'header_max_fraction':.34,'min_retained_fraction':.5}
  boxes=self.boxes([((60,30,730,210),'Two beluga whales near Alaska')])
  detector=MagicMock();detector.detectMultiScale.return_value=[]
  with patch('modules.source_editorial.cv2.CascadeClassifier',return_value=detector):
   photo,review,top,bottom=prepare_source_replacement(self.image,boxes,profile,'Two beluga whales were found near Alaska.')
  np.testing.assert_array_equal(photo,self.image[222:]);self.assertEqual(top,222)
  self.assertEqual(review['source_extraction']['crop_bounds'],[0,222,800,1000])
  payload=replacement_payload('Two beluga whales were found near Alaska.',content_topic='ocean')
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fixed.jpg';render_source_replacement(photo,review,payload,path,'assets/branding/oceans_secret.png')
   manifest=verify_publishable_poster(path,payload['rewritten_caption'])
   self.assertEqual(manifest['source_extraction'],review['source_extraction'])
   manifest['source_extraction']['crop_bounds'][1]=100
   path.with_suffix('.quality.json').write_text(json.dumps(manifest))
   with self.assertRaisesRegex(ValueError,'leaves lettering'):verify_publishable_poster(path,payload['rewritten_caption'])
  boxes.suspected_rows=[(100,450,680,490)]
  with self.assertRaisesRegex(ValueError,'overlaps the subject'):prepare_source_replacement(self.image,boxes,profile,'Two beluga whales were found near Alaska.')
 def test_replacement_quality_excludes_covered_footer_in_native_coordinates(self):
  review={'panel_top':800,'photo_y':80,'scale':.9}
  np.testing.assert_array_equal(replacement_photo_region(self.image,review),self.image[:800])


if __name__=='__main__':unittest.main()
