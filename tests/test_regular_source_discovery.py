"""Exercise exhausted landing feeds, later cards and temporary quality waits."""
import json,time,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from modules import ingestion
from modules.quality_log import unavailable_source_ids,record_rejection,profile_signature
import test_source_pairing


class RegularDiscoveryTests(unittest.TestCase):
    def story(self,pid='111111111',photo='222222222',age=0,owner='source'):
        return {'post_id':pid,'creation_time':int(time.time())-age,
                'actors':[{'url':'https://www.facebook.com/'+owner}],
                'message':{'text':'A complete source caption about the new photograph.'},
                'attachments':[{'media':{'__typename':'Photo','id':photo,'image':{'uri':'https://cdn.example/'+photo+'.jpg'}}}]}
    def response(self,stories,url='https://www.facebook.com/source'):
        return SimpleNamespace(status_code=200,url=url,text='<script type="application/json">'+json.dumps(stories)+'</script>')
    def test_waiting_first_pair_does_not_hide_new_pairs_in_posts_route(self):
        first=self.story();later=self.story('333333333','444444444')
        with patch.object(ingestion.requests,'get',side_effect=[self.response(first),self.response(later,'https://www.facebook.com/source/posts/')]) as fetch,patch.object(ingestion,'fetch_facebook_mobile_playwright') as browser:
            posts=ingestion.fetch_facebook_public_posts('source',min_candidates=1,excluded_ids=['111111111'])
        self.assertEqual([p['post_id'] for p in posts],['333333333'])
        self.assertEqual(fetch.call_count,2);browser.assert_not_called()
    def test_small_landing_batch_merges_posts_routes_without_losing_earlier_pair(self):
        first=self.story();later=self.story('333333333','444444444')
        with patch.object(ingestion.requests,'get',side_effect=[self.response(first),self.response([first,later])]),patch.object(ingestion,'fetch_facebook_mobile_playwright') as browser:
            posts=ingestion.fetch_facebook_public_posts('source',min_candidates=2)
        self.assertEqual({p['post_id'] for p in posts},{'111111111','333333333'});browser.assert_not_called()
    def test_single_fresh_nepali_pair_is_returned_after_deep_scan_cannot_fill_target(self):
        story=self.story('1159000000000001','1159000000000002',owner='smartmedianp')
        story['message']['text']='आज सार्वजनिक सेवासम्बन्धी नयाँ निर्णय सार्वजनिक गरिएको छ।'
        with patch.object(ingestion.requests,'get',side_effect=[self.response(story,'https://www.facebook.com/smartmedianp'),self.response([]),self.response([])]),patch.object(ingestion,'fetch_facebook_mobile_playwright',return_value=[]) as browser:
            posts=ingestion.fetch_facebook_public_posts('https://www.facebook.com/smartmedianp',min_candidates=12)
        self.assertEqual([p['post_id'] for p in posts],[story['post_id']])
        browser.assert_called_once()
    def test_small_fresh_landing_batch_survives_empty_deeper_views(self):
        story=self.story('1159000000000001','1159000000000002',owner='smartmedianp')
        story['message']['text']='आज सार्वजनिक सेवासम्बन्धी नयाँ निर्णय सार्वजनिक गरिएको छ।'
        with patch.object(ingestion.requests,'get',side_effect=[self.response(story,'https://www.facebook.com/smartmedianp'),self.response([]),self.response([])]),patch.object(ingestion,'fetch_facebook_mobile_playwright',return_value=[]) as browser:
            posts=ingestion.fetch_facebook_public_posts('https://www.facebook.com/smartmedianp',min_candidates=12)
        self.assertEqual([p['post_id'] for p in posts],[story['post_id']])
        browser.assert_called_once()
    def test_old_pairs_do_not_satisfy_fresh_discovery_target(self):
        old=self.story(age=80*3600);later=self.story('333333333','444444444')
        with patch.object(ingestion.requests,'get',side_effect=[self.response(old),self.response(later)]),patch.object(ingestion,'fetch_facebook_mobile_playwright') as browser:
            posts=ingestion.fetch_facebook_public_posts('source',min_candidates=1)
        self.assertEqual([p['post_id'] for p in posts],['333333333']);browser.assert_not_called()
    def test_later_scroll_collects_only_same_source_complete_pairs(self):
        setup=test_source_pairing.BrowserHydrationTests();first=self.story();later=self.story('333333333','444444444')
        outsider=self.story('555555555','666666666',owner='recommendation')
        modules,page,browser=setup.browser([])
        page.url='https://m.facebook.com/source'
        page.evaluate.side_effect=[[json.dumps(first)],[],None,[json.dumps([first,later,outsider])],[]]
        with patch.dict('sys.modules',modules):posts=ingestion.fetch_facebook_mobile_playwright('source',min_candidates=2)
        self.assertEqual({p['post_id'] for p in posts},{'111111111','333333333'});browser.close.assert_called_once()
    def test_scroll_stops_after_two_unchanged_snapshots(self):
        modules,page,browser=test_source_pairing.BrowserHydrationTests().browser([])
        page.evaluate.side_effect=[[],[],None,[],[],None,[],[]]
        with patch.dict('sys.modules',modules):self.assertEqual(ingestion.fetch_facebook_mobile_playwright('source',min_candidates=4),[])
        self.assertEqual(page.evaluate.call_count,8);browser.close.assert_called_once()
    def test_quality_wait_is_discovery_exclusion_and_never_publication_history(self):
        channel={'channel_id':'page','source_pages':['source']};signature=profile_signature(channel)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'quality.json'
            record_rejection('page','111','content_or_layout','Needs a safe image',path,signature)
            self.assertEqual(unavailable_source_ids(channel,path),{'111'})
            self.assertEqual(unavailable_source_ids(channel,path,now=time.time()+13*3600),set())
            self.assertEqual(unavailable_source_ids({**channel,'source_pages':['changed']},path),set())
        self.assertNotIn('processed_ids',channel)
    def test_deep_dom_discovery_requires_source_verified_permalink(self):
        card={'postId':'111111111','photoId':'222222222','imgUrl':'https://cdn.example/image.jpg','caption':'This is a complete photo caption.','createdTime':int(time.time()),'caption_verified':True,'caption_complete':True,'image_verified':True}
        self.assertEqual(ingestion._posts_from_mobile_cards([card],require_source=True),[])
        self.assertEqual(len(ingestion._posts_from_mobile_cards([{**card,'source_verified':True}],require_source=True)),1)


if __name__=='__main__':unittest.main()
