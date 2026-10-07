import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from modules.publication_journal import record_publication, apply_publication_receipts


class PublicationJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'publication_journal.json'
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.post = {'post_id': '12345', 'photo_id': '67890',
                     'caption_fingerprint': 'caption_v2_abcdef', 'caption': 'A factual source caption.'}

    def record(self, **overrides):
        options = {'published_at': self.now.isoformat(), 'image_hash': '0123456789abcdef',
                   'clean_image_hash': 'abcdef0123456789', 'story_fingerprint': 'factual_source_caption',
                   'path': self.path}
        options.update(overrides)
        return record_publication('oceans_secret', self.post, '24680_13579', **options)

    def test_duplicate_replay_recovers_all_ledgers_once(self):
        self.record()
        self.record()
        self.assertEqual(len(json.loads(self.path.read_text())['publications']), 1)
        state = {}
        self.assertIs(apply_publication_receipts(state, self.path), state)
        first = copy.deepcopy(state)
        apply_publication_receipts(state, self.path)
        self.assertEqual(state, first)
        self.assertEqual(state['processed_ids']['oceans_secret'], ['12345','67890','caption_v2_abcdef'])
        self.assertEqual(state['global_processed_ids'], state['processed_ids']['oceans_secret'])
        self.assertEqual(state['daily_stats']['oceans_secret']['count'], 1)
        self.assertEqual(state['channel_image_hashes']['oceans_secret'], ['0123456789abcdef'])
        self.assertEqual(state['channel_clean_image_hashes']['oceans_secret'], ['abcdef0123456789'])
        self.assertEqual(state['global_story_fingerprints'], ['factual_source_caption'])
        self.assertEqual(state['channel_recent_source_captions']['oceans_secret'], ['A factual source caption.'])
        self.assertEqual(len(state['confirmed_publications']),1)
        self.assertEqual(state['confirmed_publications'][0]['published_id'],'24680_13579')

    def test_old_day_receipt_recovers_dedup_but_does_not_increment_today(self):
        old = self.now - timedelta(days=2)
        self.record(published_at=old.timestamp())
        state = {'daily_stats': {'oceans_secret': {'date': self.now.date().isoformat(),
                 'count': 3, 'timestamps': [self.now.isoformat()], 'last_published_time': self.now.timestamp()}}}
        apply_publication_receipts(state, self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['count'], 3)
        self.assertEqual(state['daily_stats']['oceans_secret']['timestamps'], [self.now.isoformat()])
        self.assertEqual(state['daily_stats']['oceans_secret']['last_published_time'], self.now.timestamp())
        self.assertIn('12345', state['processed_ids']['oceans_secret'])

    def test_processed_source_repairs_partial_ledgers_without_counting(self):
        self.record()
        state = {'processed_ids': {'oceans_secret': ['12345']},
                 'daily_stats': {'oceans_secret': {'date': self.now.date().isoformat(),
                 'count': 1, 'timestamps': [], 'last_published_time': 0}}}
        apply_publication_receipts(state, self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['count'], 1)
        self.assertEqual(state['daily_stats']['oceans_secret']['timestamps'], [self.now.isoformat()])
        self.assertEqual(state['daily_stats']['oceans_secret']['last_published_time'], self.now.timestamp())
        self.assertIn('67890', state['processed_ids']['oceans_secret'])
        self.assertIn('abcdef0123456789', state['channel_clean_image_hashes']['oceans_secret'])

    def test_new_current_day_receipt_resets_old_daily_count(self):
        self.record()
        state = {'daily_stats': {'oceans_secret': {'date': '2025-01-01', 'count': 9,
                 'timestamps': ['2025-01-01T00:00:00+00:00'], 'last_published_time': 0}}}
        apply_publication_receipts(state, self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['date'], self.now.date().isoformat())
        self.assertEqual(state['daily_stats']['oceans_secret']['count'], 1)
        self.assertEqual(state['daily_stats']['oceans_secret']['timestamps'], [self.now.isoformat()])

    def test_only_whitelisted_fields_survive_and_caption_is_bounded_utf8(self):
        self.post.update(access_token='SECRET_TOKEN', image_url='https://private.example/image',
                         source_page_url='https://facebook.com/source', token='OTHER_SECRET',
                         caption='समाचार' * 1200)
        self.record()
        raw = self.path.read_text(encoding='utf-8')
        self.assertNotIn('SECRET', raw)
        self.assertNotIn('https://', raw)
        receipt = json.loads(raw)['publications'][0]
        self.assertEqual(len(receipt['source_caption']), 4000)
        self.assertEqual(set(receipt), {'channel_id','post_id','published_id','published_at',
                         'processed_ids','story_fingerprint','source_caption','image_hash','clean_image_hash'})

    def test_invalid_receipts_fail_before_any_state_mutation(self):
        valid = self.record()
        for updates in ({'published_id': 'EAA-token'}, {'channel_id': '../bad'},
                        {'published_at': 'not-a-date'}, {'published_at': '2026-01-01T00:00:00'},
                        {'published_at': (self.now + timedelta(days=1)).isoformat()},
                        {'processed_ids': ['67890']}, {'token': 'secret'}, {'image_hash': 'https://secret'}):
            with self.subTest(updates=updates):
                self.path.write_text(json.dumps({'publications': [valid, {**valid, **updates}]}))
                state = {'processed_ids': {'untouched': ['original']}}
                before = copy.deepcopy(state)
                with self.assertRaises(ValueError):
                    apply_publication_receipts(state, self.path)
                self.assertEqual(state, before)

    def test_atomic_write_failure_preserves_old_receipt_file(self):
        self.record()
        old = self.path.read_bytes()
        self.post['post_id'] = '99999'
        with patch('modules.publication_journal.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                record_publication('nepal_speaks',self.post,'33333_44444',published_at=self.now.timestamp(),
                                   image_hash='',clean_image_hash='',story_fingerprint='',path=self.path)
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_missing_journal_is_a_noop(self):
        state = {'processed_ids': {'old': ['one']}}
        original = copy.deepcopy(state)
        apply_publication_receipts(state, self.path)
        self.assertEqual(state, original)

    def test_confirmation_archive_is_idempotent_and_rejects_conflicting_source(self):
        receipt = self.record()
        state = {'confirmed_publications': [receipt]}
        apply_publication_receipts(state,self.path)
        self.assertEqual(len(state['confirmed_publications']),1)
        state['confirmed_publications'][0]['post_id']='99999'
        state['confirmed_publications'][0]['processed_ids']=['99999']
        before=copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError,'another source post'):
            apply_publication_receipts(state,self.path)
        self.assertEqual(state,before)

    def test_missing_source_identifier_is_not_stringified_into_a_receipt(self):
        self.post['post_id']=None
        with self.assertRaisesRegex(ValueError,'source post identifier'):
            self.record()
        self.assertFalse(self.path.exists())

    def test_actual_spaced_channel_keys_are_valid_and_path_keys_are_not(self):
        for channel in ('Music Store','Daily Hollywood'):
            with self.subTest(channel=channel):
                record_publication(channel,self.post,'24680_13579',published_at=self.now.timestamp(),
                                   image_hash='',clean_image_hash='',story_fingerprint='',path=self.path)
        state={}
        apply_publication_receipts(state,self.path)
        self.assertEqual(set(state['processed_ids']),{'Music Store','Daily Hollywood'})
        for channel in ('../page','page/child','page\\child','page\nchild',' page','page ','x'*97):
            with self.subTest(channel=channel),self.assertRaises(ValueError):
                record_publication(channel,self.post,'111',published_at=self.now.timestamp(),
                                   image_hash='',clean_image_hash='',story_fingerprint='',path=self.path)

    def test_partial_processed_id_with_zero_count_recovers_once(self):
        self.record()
        state={'processed_ids':{'oceans_secret':['12345']},'daily_stats':{'oceans_secret':{
               'date':self.now.date().isoformat(),'count':0,'timestamps':[],'last_published_time':0}}}
        apply_publication_receipts(state,self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['count'],1)
        first=copy.deepcopy(state)
        apply_publication_receipts(state,self.path)
        self.assertEqual(state,first)

    def test_lost_source_ids_do_not_recount_an_existing_timestamp(self):
        self.record()
        state={'daily_stats':{'oceans_secret':{'date':self.now.date().isoformat(),
               'count':1,'timestamps':[self.now.isoformat().replace('+00:00','Z')],'last_published_time':0}}}
        apply_publication_receipts(state,self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['count'],1)
        self.assertEqual(len(state['daily_stats']['oceans_secret']['timestamps']),1)

    def test_distinct_confirmed_meta_ids_same_source_or_second_count_physically(self):
        self.record()
        record_publication('oceans_secret',self.post,'22222_33333',published_at=self.now.timestamp(),
                           image_hash='',clean_image_hash='',story_fingerprint='',path=self.path)
        state={}
        apply_publication_receipts(state,self.path)
        self.assertEqual(state['daily_stats']['oceans_secret']['count'],2)
        self.assertEqual(len(state['confirmed_publications']),2)
        before=copy.deepcopy(state)
        apply_publication_receipts(state,self.path)
        self.assertEqual(state,before)


if __name__ == '__main__':
    unittest.main()
