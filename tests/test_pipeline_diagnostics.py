"""Exercise queue feedback without any rendering or publication calls."""
import ast
import contextlib
import datetime
import io
import json
import os
import tempfile
import time
import traceback
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class PipelineDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        cls.functions = compile(ast.Module(
            body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
            type_ignores=[]), 'main.py', 'exec')

    def run_isolated(self, posts, *, cooldown=False, topic='music', processed=(), paused=False):
        state = {'processed_ids': {'test': list(processed)}, 'daily_stats': {}}
        namespace = dict(os=os, time=time, json=json, copy=__import__('copy'),
                         apply_publication_receipts=lambda ledger: ledger, datetime=datetime.datetime,
                         timezone=datetime.timezone, traceback=traceback,
                         OUTPUT_DIR='output', MAX_DAILY_LIMIT_PER_PAGE=15,
                         WEB_SCRAPER_AVAILABLE=False)
        exec(self.functions, namespace)
        namespace.update(
            load_config=lambda: {'channels': [{'channel_id': 'test', 'channel_name': 'Test Page',
                'content_topic': topic, 'dest_access_token_env': 'EAA_test',
                'posting_paused': paused,
                'source_pages': ['https://www.facebook.com/source']}]},
            load_state=lambda: state, save_state=Mock(),
            fetch_source_posts=Mock(return_value=posts), download_image=Mock(return_value=None),
            publish_to_facebook=Mock(), send_telegram_alert=Mock())
        output = io.StringIO()
        previous_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch('modules.quality_log.ready_candidates',
                           side_effect=lambda channel, candidates, **kwargs: [] if cooldown else candidates), \
                     patch('modules.quality_log.record_rejection') as rejection, \
                     contextlib.redirect_stdout(output):
                    namespace['run_pipeline']()
                rejection_calls = rejection.call_args_list
            finally:
                os.chdir(previous_directory)
        namespace['publish_to_facebook'].assert_not_called()
        self.assertEqual(state['processed_ids']['test'], list(processed))
        return output.getvalue(), namespace, rejection_calls

    def post(self, caption='A singer released a new album today.', age=60):
        return {'post_id': 'story-123', 'photo_id': 'photo-456', 'caption': caption,
                'created_time': int(time.time()) - age, 'image_url': 'https://cdn.example/photo.jpg'}

    def test_quality_cooldown_is_waiting_not_up_to_date(self):
        output, namespace, _ = self.run_isolated([self.post()], cooldown=True)
        self.assertIn('[QUALITY WAIT]', output)
        self.assertIn('retry_wait=1', output)
        self.assertNotIn('[UP TO DATE]', output)
        namespace['download_image'].assert_not_called()

    def test_paused_page_does_not_fetch_or_publish(self):
        output, namespace, rejections = self.run_isolated([self.post()], paused=True)
        self.assertIn('[PAGE PAUSED]', output)
        namespace['fetch_source_posts'].assert_not_called()
        namespace['download_image'].assert_not_called()
        self.assertEqual(rejections, [])

    def test_topic_rejection_reports_why_queue_is_empty(self):
        output, namespace, rejections = self.run_isolated(
            [self.post('A car crashed on a highway in the mountains.')], topic='ocean')
        self.assertIn('[TOPIC WAIT]', output)
        self.assertIn('topic_rejected=1', output)
        self.assertNotIn('[UP TO DATE]', output)
        self.assertEqual(rejections[0].args[2], 'topic_or_caption')
        namespace['download_image'].assert_not_called()

    def test_empty_source_and_old_source_have_distinct_messages(self):
        empty_output, _, _ = self.run_isolated([])
        stale_output, namespace, _ = self.run_isolated([self.post(age=300000)])
        self.assertIn('[NO SOURCE CANDIDATES]', empty_output)
        self.assertIn('[STALE SOURCE]', stale_output)
        self.assertIn('outside_72h=1', stale_output)
        namespace['download_image'].assert_not_called()

    def test_actual_published_duplicate_is_up_to_date(self):
        output, namespace, _ = self.run_isolated([self.post()], processed=('story-123',))
        self.assertIn('[UP TO DATE]', output)
        self.assertIn('duplicates=1', output)
        namespace['download_image'].assert_not_called()

    def test_unavailable_image_reports_blocked_keeps_source_pending(self):
        output, namespace, rejections = self.run_isolated([self.post()])
        self.assertIn('[READY QUEUE]', output)
        self.assertIn('[PAGE BLOCKED]', output)
        self.assertNotIn('[UP TO DATE]', output)
        namespace['download_image'].assert_called_once()
        self.assertEqual(rejections[0].args[2], 'source_image')


if __name__ == '__main__':
    unittest.main()
