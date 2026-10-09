import json,tempfile,unittest
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from modules.image_cleaner import SourceTextBoxes
from modules.source_replacement import review_source_replacement,render_source_replacement,replacement_payload
from modules.poster_quality import verify_publishable_poster

class SourceReplacementTests(unittest.TestCase):
 def test_leading_emoji_does_not_hide_the_main_marine_outcome(self):
  caption='💔 A beloved bottlenose dolphin named Carl has died at Sendai Uminomori Aquarium in Japan.\nThe aquarium previously shared stories about Carl’s favorite toys.'
  self.assertIn('Carl has died',replacement_payload(caption,content_topic='ocean')['headline'])
 def test_reviewed_source_seal_is_covered_by_png_circle_without_square_backing(self):
  image=self.image();boxes=SourceTextBoxes([(1050,110,1154,164)])
  review=review_source_replacement(image,boxes,corner_template={'seal_bounds':[.85,.018,.98,.13]})
  self.assertTrue(review['corner_covered'])
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'poster.jpg'
   render_source_replacement(image,review,self.payload(),path,logo_path='assets/branding/oceans_secret.png')
   verify_publishable_poster(path,self.payload()['rewritten_caption'])
 def test_source_seal_outside_reviewed_template_stays_blocked(self):
  with self.assertRaisesRegex(ValueError,'exceeds'):
   review_source_replacement(self.image(),SourceTextBoxes([(950,30,1170,170)]),corner_template={'seal_bounds':[.85,.018,.98,.13]})
 def test_owned_panel_does_not_cover_photo_above_original_footer(self):
  review=review_source_replacement(self.image(),SourceTextBoxes([(80,1100,1100,1180)]))
  self.assertEqual(review['panel_top'],972)
 def test_octopus_hook_names_the_subject_from_the_exact_source_caption(self):
  caption='Deep beneath the Pacific, researchers captured a creature that looks almost unreal.\nIt’s a Dumbo octopus — a deep-sea animal named for the ear-like fins on its head.'
  self.assertEqual(replacement_payload(caption,content_topic='ocean')['headline'],'Researchers captured a Dumbo octopus deep beneath the Pacific')
 def test_original_png_alpha_is_preserved_without_black_backing(self):
  with Image.open('assets/branding/oceans_secret.png') as logo:
   self.assertEqual(logo.mode,'RGBA');self.assertEqual(logo.getpixel((0,0))[3],0)
  with self.assertRaisesRegex(ValueError,'opaque cover'):
   review_source_replacement(self.image(),SourceTextBoxes([(1030,30,1170,170)]))
 def test_logo_has_no_square_backing_when_source_corner_is_clear(self):
  image=self.image();review=review_source_replacement(image,SourceTextBoxes([]))
  self.assertFalse(review['corner_present'])
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'poster.jpg'
   render_source_replacement(image,review,self.payload(),path,logo_path='assets/branding/oceans_secret.png')
   with Image.open(path) as poster:
    self.assertGreater(max(poster.getpixel((810,40))),20)
    self.assertGreater(max(poster.getpixel((1010,70))),20)
   self.assertEqual(json.loads(path.with_suffix('.quality.json').read_text())['logo_shape'],'circle')
 def image(self):
  y,x=np.indices((1400,1200))
  return np.stack((x%170+30,y%170+30,(x+y)%170+30),axis=2).astype(np.uint8)
 def boxes(self):
  return SourceTextBoxes([(15,802,570,874),(55,920,1150,1300)],
                         suspected_rows=[(720,1360,1190,1390)])
 def payload(self):
  return {'headline':'Whale calves swim offshore beside their mothers',
          'overlay_lines':[[{'text':'Whale calves swim offshore beside their mothers','type':'white'}]],
          'rewritten_caption':'Whale calves swim offshore beside their mothers.'}
 def test_complete_coverage_and_safe_4_by_5_geometry(self):
  image=self.image();original=image.copy();review=review_source_replacement(image,self.boxes())
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'poster.jpg';payload=self.payload()
   render_source_replacement(image,review,payload,path,logo_path='assets/branding/oceans_secret.png')
   manifest=verify_publishable_poster(path,payload['rewritten_caption'])
   self.assertEqual(manifest['size'],[1080,1350]);self.assertGreaterEqual(manifest['font_size'],68)
   self.assertEqual(manifest['logo_bounds'],[824,64,1016,256])
   for l,t,r,b in manifest['source_overlay_bounds']:
    self.assertTrue(any(a<=l and c>=r and y<=t and d>=b for a,y,c,d in manifest['replacement_bounds']))
   np.testing.assert_array_equal(image,original)
   with Image.open(path) as poster:
    # Original source news badge, lower headline, and corner logo areas are
    # opaque black backing; subjects outside those zones remain photographed.
    self.assertLess(max(poster.getpixel((20,735))),8)
    self.assertGreater(max(poster.getpixel((1050,70))),20)
    self.assertGreater(max(poster.getpixel((350,350))),20)
 def test_subject_lettering_and_excessive_cover_are_rejected(self):
  for boxes in [SourceTextBoxes([(80,300,900,400)]),SourceTextBoxes([(80,710,900,800)])]:
   with self.subTest(boxes=boxes),self.assertRaises(ValueError):
    review_source_replacement(self.image(),boxes)
 def test_low_confidence_footer_is_covered_without_guessing_its_words(self):
  boxes=SourceTextBoxes([],suspected_rows=[(80,1100,1100,1180)],suspected_marks=[])
  self.assertTrue(review_source_replacement(self.image(),boxes)['source_overlay_bounds'])
 def test_source_pixel_change_invalidates_review(self):
  image=self.image();review=review_source_replacement(image,self.boxes());image[0,0]^=255
  with tempfile.TemporaryDirectory() as folder,self.assertRaisesRegex(ValueError,'changed'):
   render_source_replacement(image,review,self.payload(),Path(folder)/'poster.jpg',logo_path='assets/branding/oceans_secret.png')
 def test_manifest_with_insufficient_coverage_is_rejected(self):
  image=self.image();review=review_source_replacement(image,self.boxes());payload=self.payload()
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'poster.jpg';render_source_replacement(image,review,payload,path,logo_path='assets/branding/oceans_secret.png')
   report=path.with_suffix('.quality.json');data=json.loads(report.read_text());data['replacement_bounds']=[[0,1300,1080,1350]]
   report.write_text(json.dumps(data))
   with self.assertRaisesRegex(ValueError,'not completely covered'):verify_publishable_poster(path,payload['rewritten_caption'])
 def test_caption_leads_with_main_marine_outcome_without_losing_species(self):
  source=('A rescue effort ended in tragedy in Malaysia.\nA female false killer whale was found stranded on a beach.\n'
          'The false killer whale died after the rescue.\nAuthorities may review the incident.')
  payload=replacement_payload(source,language='en',channel_name="Ocean's Secret",channel_id='oceans_secret',content_topic='ocean')
  self.assertEqual(payload['headline'],'The false killer whale died after the rescue')
  self.assertTrue(payload['rewritten_caption'].startswith(payload['headline']))
 def test_nonmarine_caption_is_never_accepted(self):
  with self.assertRaises(ValueError):replacement_payload('A Netflix show released a new season.',content_topic='ocean')
 def test_condensed_outcome_keeps_species_condition_and_approximate_time(self):
  source=('The false killer whale was already in a weakened condition and died at around 2 p.m.\n'
          'The whale was found stranded on a beach in Malaysia.')
  data=replacement_payload(source,language='en',content_topic='ocean')
  self.assertEqual(data['headline'],'A weakened false killer whale died at around 2 p.m')
  self.assertIn('around 2 p.m',data['rewritten_caption'])
 def test_footer_at_exact_image_edge_is_fully_covered(self):
  review=review_source_replacement(self.image(),SourceTextBoxes([(0,1100,1200,1400)]))
  self.assertEqual(review['source_overlay_bounds'][0],[0,990,1080,1260])
 def test_all_ocean_sources_use_destination_replacement_layout(self):
  config=json.loads(Path('config.json').read_text(encoding='utf-8'))
  page=next(c for c in config['channels'] if c['channel_id']=='oceans_secret')
  self.assertIn('https://www.facebook.com/livingoceans000',page['source_pages'])
  self.assertEqual(page['poster_style']['layout_kind'],'source_replacement')
  self.assertFalse(page['preserve_readable_source_cards'])
  self.assertTrue(all(s['logo_position']=='top-right' and s['text_position']=='bottom' for s in page['source_layouts'].values()))
