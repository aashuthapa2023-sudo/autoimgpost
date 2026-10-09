import json,tempfile,unittest
from pathlib import Path
from modules.source_cache import merge_source_candidates

class SourceCacheTests(unittest.TestCase):
 def test_empty_feed_recovers_exact_pair_but_not_published_or_stale_posts(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'cache.json';ch={'channel_id':'test','source_pages':['https://www.facebook.com/source']}
   post={'post_id':'123','photo_id':'456','caption':'Exact original caption','image_url':'https://cdn.example/photo.jpg','created_time':1000000,'source_page_url':ch['source_pages'][0]}
   self.assertEqual(merge_source_candidates(ch,[post],path=path,now=1000001),[post])
   self.assertEqual(merge_source_candidates(ch,[],path=path,now=1000100),[post])
   self.assertEqual(merge_source_candidates(ch,[],['456'],path=path,now=1000100),[])
   merge_source_candidates(ch,[post],path=path,now=1000001)
   self.assertEqual(merge_source_candidates(ch,[],path=path,now=1300000),[])
 def test_changed_config_never_recovers_an_unlinked_source(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'cache.json';post={'post_id':'123','photo_id':'456','caption':'Original','image_url':'https://cdn.example/photo.jpg','created_time':1000,'source_page_url':'https://www.facebook.com/old'}
   path.write_text(json.dumps({'test':[post]}))
   self.assertEqual(merge_source_candidates({'channel_id':'test','source_pages':['https://www.facebook.com/new']},[],path=path,now=1001),[])
