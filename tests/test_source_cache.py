import json,tempfile,unittest
from pathlib import Path
from modules.source_cache import merge_source_candidates

class SourceCacheTests(unittest.TestCase):
 def test_shared_pair_requires_configured_source_and_destination_uniqueness(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'cache.json';source='https://www.facebook.com/source'
   post={'post_id':'123','photo_id':'456','caption':'Exact original caption','image_url':'https://cdn.example/photo.jpg','created_time':1000000,'source_page_url':source}
   other={**post,'post_id':'124','source_page_url':'https://www.facebook.com/unlinked'}
   stale={**post,'post_id':'125','created_time':1}
   malformed={**post,'post_id':'126','photo_id':''}
   path.write_text(json.dumps({'other_page':[post,other,stale,malformed]}))
   ch={'channel_id':'target','source_pages':[source]}
   self.assertEqual(merge_source_candidates(ch,[],path=path,now=1000100),[post])
   self.assertEqual(merge_source_candidates(ch,[],processed_ids=['456'],path=path,now=1000101),[])
   self.assertEqual(json.loads(path.read_text())['other_page'],[post,other,stale,malformed])
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
