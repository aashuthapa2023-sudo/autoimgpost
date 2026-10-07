"""Unconfirmed runtime failures yield candidate slots without retrying confirmations."""
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
from types import SimpleNamespace
from unittest.mock import Mock, patch


class TransientPipelineRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        cls.functions = compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
                                           type_ignores=[]), 'main.py', 'exec')

    def isolated_pipeline(self, count=7):
        state = {'processed_ids': {'test': []}, 'daily_stats': {}}
        image = SimpleNamespace(shape=(768, 768, 3))
        namespace = dict(os=os, time=time, json=json, copy=__import__('copy'),
                         apply_publication_receipts=lambda ledger: ledger, datetime=datetime.datetime,
                         timezone=datetime.timezone, traceback=traceback,
                         OUTPUT_DIR='output', MAX_DAILY_LIMIT_PER_PAGE=15, WEB_SCRAPER_AVAILABLE=False)
        exec(self.functions, namespace)
        posts = [{'post_id':str(number), 'photo_id':'photo-'+str(number),
                  'caption':f'A singer released a new album with {number} songs.',
                  'image_url':'image-'+str(number), 'created_time':int(time.time())-60}
                 for number in range(1, count+1)]
        namespace.update(
            load_config=lambda:{'channels':[{'channel_id':'test','channel_name':'Test Page','content_topic':'music',
                'language':'en','dest_page_id':'page','dest_access_token_env':'EAA_test',
                'source_pages':['https://www.facebook.com/source'],'max_candidates_per_run':6}]},
            load_state=lambda:state, save_state=Mock(), fetch_source_posts=Mock(return_value=posts),
            download_image=Mock(return_value=image), validate_image_quality=Mock(return_value=(True,'Valid source')),
            compute_image_dhash=Mock(return_value=''), erase_text_and_watermarks=Mock(return_value=(image,0,768)),
            apply_cinematic_grade=Mock(return_value=image), generate_social_payload=Mock(return_value={
                'headline':'A singer releases a new album',
                'overlay_lines':[[{'text':'A singer releases a new album','type':'white'}]],
                'rewritten_caption':'A singer released a new album.'}),
            render_final_poster=Mock(), publish_to_facebook=Mock(return_value='meta-confirmed'),
            record_publication=Mock(), send_telegram_alert=Mock())
        return namespace, state, posts

    @contextlib.contextmanager
    def without_external_work(self):
        previous_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as directory, \
                patch('modules.poster_engine.detect_image_text_position',return_value='bottom'), \
                patch('modules.image_cleaner.detect_source_text_boxes',return_value=[]), \
                patch('modules.source_headline.render_with_source_fallback',side_effect=lambda payload,*args,**kwargs:payload), \
                patch('update_cache.update_posters_cache'), contextlib.redirect_stdout(io.StringIO()):
            try:
                os.chdir(directory)
                yield
            finally:
                os.chdir(previous_directory)

    def test_six_generic_failures_yield_to_seventh_candidate_on_next_cycle(self):
        namespace,state,posts = self.isolated_pipeline()
        image = namespace['download_image'].return_value
        namespace['download_image'].side_effect = [RuntimeError('OCR temporarily unavailable')]*6 + [image]
        with self.without_external_work():
            namespace['run_pipeline']()
            namespace['publish_to_facebook'].assert_not_called()
            self.assertEqual(namespace['download_image'].call_count,6)
            self.assertEqual(state['processed_ids']['test'],[])
            report=json.loads(Path('quality_report.json').read_text(encoding='utf-8'))
            self.assertEqual(len(report['rejections']),6)
            self.assertTrue(all(item['stage']=='transient_processing' for item in report['rejections']))
            namespace['run_pipeline']()
        self.assertEqual(namespace['download_image'].call_count,7)
        self.assertEqual(namespace['download_image'].call_args.args,('image-7',))
        namespace['publish_to_facebook'].assert_called_once()
        self.assertIn('7',state['processed_ids']['test'])
        self.assertTrue(all(str(number) not in state['processed_ids']['test'] for number in range(1,7)))
        self.assertEqual(state['daily_stats']['test']['count'],1)

    def test_unconfirmed_publish_error_is_retry_delayed_and_another_candidate_can_publish(self):
        namespace,state,posts = self.isolated_pipeline(count=2)
        namespace['publish_to_facebook'].side_effect=[RuntimeError('Temporary Graph response failure'),'meta-confirmed']
        with self.without_external_work():
            namespace['run_pipeline']()
            report=json.loads(Path('quality_report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['rejections'][0]['post_id'],'1')
        self.assertEqual(report['rejections'][0]['stage'],'transient_processing')
        self.assertNotIn('1',state['processed_ids']['test'])
        self.assertIn('2',state['processed_ids']['test'])
        namespace['record_publication'].assert_called_once()

    def test_seventh_candidate_is_prioritized_even_after_front_failure_waits_expire(self):
        namespace,state,posts = self.isolated_pipeline()
        image = namespace['download_image'].return_value
        namespace['download_image'].side_effect = [RuntimeError('OCR temporarily unavailable')]*6 + [image]
        with self.without_external_work():
            namespace['run_pipeline']()
            report=json.loads(Path('quality_report.json').read_text(encoding='utf-8'))
            after_expiry=max(item['retry_after'] for item in report['rejections'])+1
            with patch('modules.quality_log.time.time',return_value=after_expiry):
                namespace['run_pipeline']()
        self.assertEqual(namespace['download_image'].call_count,7)
        self.assertEqual(namespace['download_image'].call_args.args,('image-7',))
        namespace['publish_to_facebook'].assert_called_once()
        self.assertIn('7',state['processed_ids']['test'])
        self.assertTrue(all(str(number) not in state['processed_ids']['test'] for number in range(1,7)))

    def test_confirmed_publish_save_error_stops_without_a_retry_rejection(self):
        namespace,state,posts = self.isolated_pipeline(count=2)
        namespace['record_publication'].side_effect=OSError('Confirmation ledger unavailable')
        with self.without_external_work(), patch('modules.quality_log.record_rejection') as rejection:
            with self.assertRaisesRegex(RuntimeError,'Confirmed publication receipt/state could not be saved'):
                namespace['run_pipeline']()
            self.assertFalse(Path('quality_report.json').exists())
        rejection.assert_not_called()
        namespace['publish_to_facebook'].assert_called_once()
        namespace['download_image'].assert_called_once()
        namespace['send_telegram_alert'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
