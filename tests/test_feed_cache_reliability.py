"""Keep a usable source feed through an empty refresh, without live fetching."""
import ast
import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


class FeedCacheReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(Path('build_rich_feed_cache.py').read_text(encoding='utf-8'))
        cls.builder = compile(ast.Module(body=[node for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)], type_ignores=[]), 'build_rich_feed_cache.py', 'exec')

    def build(self, previous):
        namespace = dict(json=json, os=os, datetime=datetime.datetime, timezone=datetime.timezone,
                         fetch_facebook_public_posts=Mock(return_value=[]))
        exec(self.builder, namespace)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'feed_cache.json'
            if previous is not None:
                cache.write_text(json.dumps(previous), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                result = namespace['build_rich_feed_cache'](
                    'https://www.facebook.com/requested', limit=7, cache_path=str(cache))
            saved = json.loads(cache.read_text(encoding='utf-8'))
        namespace['fetch_facebook_public_posts'].assert_called_once_with(
            'https://www.facebook.com/requested', limit=7)
        self.assertEqual(result, saved)
        return saved

    def test_empty_refresh_retains_original_pairs_and_explains_staleness(self):
        original = {'success': True, 'updated_at': '2026-10-06T10:00:00+00:00',
                    'page': 'https://www.facebook.com/previous', 'channel_id': 'music', 'count': 1,
                    'posts': [{'post_id': '1', 'caption': 'An exact source caption.',
                               'image_url': 'https://cdn.example/source.jpg', 'created_time': 123}]}
        saved = self.build(original)
        for key, value in original.items():
            self.assertEqual(saved[key], value)
        self.assertEqual(saved['last_refresh']['status'], 'source_unavailable')
        self.assertEqual(saved['last_refresh']['requested_page'], 'https://www.facebook.com/requested')

    def test_empty_refresh_without_previous_posts_never_invents_pairs(self):
        saved = self.build(None)
        self.assertEqual(saved['count'], 0)
        self.assertEqual(saved['posts'], [])
        self.assertEqual(saved['page'], 'https://www.facebook.com/requested')

    def test_cli_honors_exact_manual_source_and_limit(self):
        # Extract only the CLI entry point so optional vision imports stay isolated.
        entry = next(node for node in self.tree.body if isinstance(node, ast.If))
        builder = Mock()
        namespace = {'__name__': '__main__', 'json': json, 'build_rich_feed_cache': builder}
        from unittest.mock import patch
        with patch('sys.argv', ['build_rich_feed_cache.py', 'https://www.facebook.com/music-source', '7']):
            exec(compile(ast.Module(body=[entry], type_ignores=[]), 'cli', 'exec'), namespace)
        builder.assert_called_once_with('https://www.facebook.com/music-source', 7)

    def test_blank_manual_source_uses_configured_source(self):
        entry = next(node for node in self.tree.body if isinstance(node, ast.If))
        builder = Mock()
        namespace = {'__name__': '__main__', 'json': json, 'build_rich_feed_cache': builder}
        from unittest.mock import patch
        previous_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path('config.json').write_text(json.dumps({'channels': [
                    {'source_pages': ['https://www.facebook.com/configured-source']}]}), encoding='utf-8')
                with patch('sys.argv', ['build_rich_feed_cache.py', '', '15']):
                    exec(compile(ast.Module(body=[entry], type_ignores=[]), 'cli', 'exec'), namespace)
            finally:
                os.chdir(previous_directory)
        builder.assert_called_once_with('https://www.facebook.com/configured-source', 15)

    def test_normal_publishing_workflow_never_fetches_hardcoded_extra_source(self):
        workflow = Path('.github/workflows/pipeline.yml').read_text(encoding='utf-8')
        self.assertNotIn('NetflixDailyUpdates', workflow)
        self.assertIn('python build_rich_feed_cache.py "$FEED_SOURCE_URL" 15', workflow)
        normal_branch = workflow.split('else\n', 1)[1].split('fi\n', 1)[0]
        self.assertNotIn('build_rich_feed_cache.py', normal_branch)


if __name__ == '__main__':
    unittest.main()
