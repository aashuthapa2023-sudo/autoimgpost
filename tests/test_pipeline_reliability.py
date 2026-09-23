import ast
import os
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from modules import ingestion, publisher

class DiscoveryTests(unittest.TestCase):
    def test_embedded_story_is_scanned_and_cdn_image_preserved(self):
        story = {'post_id': '123', 'creation_time': int(time.time()),
                 'message': {'text': 'A real source story caption'},
                 'attachments': [{'media': {'id': '456', 'image': {'uri': 'https://cdn.example/photo.jpg'}}}]}
        html = ''.join('<script type="application/json">' + json.dumps(x) + '</script>' for x in [{}, {}, {'story': story}])
        with patch.object(ingestion.requests, 'get', return_value=SimpleNamespace(status_code=200, url='https://www.facebook.com/source', text=html)), patch.object(ingestion, 'fetch_facebook_mobile_playwright') as browser:
            posts = ingestion.fetch_facebook_public_posts('source')
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['image_url'], 'https://cdn.example/photo.jpg')
        browser.assert_not_called()

    def test_each_source_gets_full_scan_budget(self):
        with patch.object(ingestion, 'fetch_facebook_public_posts', return_value=[]) as fetch:
            ingestion.fetch_source_posts(source_pages=['one', 'two', 'three'], limit=60)
        self.assertEqual([c.kwargs['limit'] for c in fetch.call_args_list], [60, 60, 60])

    def test_missing_publish_confirmation_is_failure(self):
        with tempfile.NamedTemporaryFile(delete=False) as image:
            image.write(b"dummy")
            image_path = image.name
        try:
            with patch.object(publisher.requests, 'post', return_value=SimpleNamespace(status_code=500, json=lambda: {})):
                with self.assertRaises(RuntimeError):
                    publisher.publish_to_facebook('page', 'token', image_path, 'caption')
        finally:
            if os.path.exists(image_path):
                os.remove(image_path)

class PipelineTests(unittest.TestCase):
    def test_failed_fresh_image_retries_older_candidate_without_poisoning_state(self):
        # Execute pipeline functions with external rendering and publishing isolated.
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        functions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[])
        import os, datetime, traceback
        state = {'processed_ids': {}, 'daily_stats': {}}
        now = int(time.time())
        posts = [{'post_id': str(i), 'photo_id': str(i), 'caption': 'caption '+str(i), 'image_url': 'image'+str(i), 'created_time': now-age} for i, age in [(1, 60), (2, 90000)]]
        ns = dict(os=os, time=time, json=json, datetime=datetime.datetime, timezone=datetime.timezone, traceback=traceback,
                  OUTPUT_DIR=tempfile.gettempdir(), MAX_DAILY_LIMIT_PER_PAGE=15, WEB_SCRAPER_AVAILABLE=False)
        exec(compile(functions, 'main.py', 'exec'), ns)
        ns.update(load_config=lambda: {'channels': [{'channel_id': 'test', 'dest_access_token_env': 'EAA_test'}]},
                  load_state=lambda: state, save_state=Mock(), fetch_source_posts=Mock(return_value=posts),
                  download_image=Mock(return_value=None), send_telegram_alert=Mock())
        ns['run_pipeline']()
        self.assertEqual(ns['download_image'].call_count, 2)
        self.assertEqual(state['processed_ids']['test'], [])
        ns['save_state'].reset_mock()
        ns['run_pipeline'](mode='dry_run')
        ns['save_state'].assert_not_called()

if __name__ == '__main__':
    unittest.main()
