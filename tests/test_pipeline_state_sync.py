import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sync_pipeline_state import (
    StateSyncError, capture_baseline, merge_pipeline_state, _read_json,
)


class PipelineStateSyncTests(unittest.TestCase):
    now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    first = '2026-10-07T01:00:00+00:00'
    second = '2026-10-07T02:00:00+00:00'
    third = '2026-10-07T03:00:00+00:00'
    fourth = '2026-10-07T04:00:00+00:00'

    def state(self, *, count=2, times=None, processed=None, last=None):
        times = [self.first, self.second] if times is None else times
        last = datetime.fromisoformat(times[-1]).timestamp() if last is None and times else (last or 0)
        return {
            'processed_ids': {'ocean': list(['source-a', 'source-b'] if processed is None else processed)},
            'daily_stats': {'ocean': {
                'date': '2026-10-07', 'count': count,
                'timestamps': list(times), 'last_published_time': last,
            }},
        }

    def merge(self, baseline, run, latest):
        return merge_pipeline_state(baseline, run, latest, now=self.now)

    def test_concurrent_distinct_posts_preserve_both_branches_and_newest_cadence(self):
        baseline = self.state()
        run = self.state(count=3, times=[self.first, self.second, self.third],
                         processed=['source-a', 'source-b', 'run-source'])
        latest = self.state(count=3, times=[self.first, self.second, self.fourth],
                            processed=['source-a', 'source-b', 'remote-source'])
        originals = copy.deepcopy((baseline, run, latest))

        merged = self.merge(baseline, run, latest)

        self.assertCountEqual(merged['processed_ids']['ocean'],
                              ['source-a', 'source-b', 'remote-source', 'run-source'])
        stats = merged['daily_stats']['ocean']
        self.assertEqual(stats['count'], 4)
        self.assertEqual(len(stats['timestamps']), 4)
        self.assertEqual(stats['last_published_time'], datetime.fromisoformat(self.fourth).timestamp())
        self.assertEqual((baseline, run, latest), originals)

    def test_same_meta_confirmation_in_two_branches_is_not_counted_twice(self):
        baseline = self.state(count=0, times=[], processed=[])
        run = self.state(count=1, times=[self.third], processed=['new-source'])
        latest = self.state(count=1, times=['2026-10-07T08:45:00+05:45'], processed=['new-source'])
        receipt = {'channel_id': 'ocean', 'post_id': 'new-source', 'published_id': '100_123',
                   'published_at': self.third}
        run['confirmed_publications'] = [receipt]
        latest['confirmed_publications'] = [dict(receipt, image_hash='known-photo')]

        merged = self.merge(baseline, run, latest)

        self.assertEqual(merged['daily_stats']['ocean']['count'], 1)
        self.assertEqual(merged['daily_stats']['ocean']['timestamps'],
                         ['2026-10-07T03:00:00.000000+00:00'])
        self.assertEqual(len(merged['confirmed_publications']), 1)
        self.assertEqual(merged['confirmed_publications'][0]['image_hash'], 'known-photo')
        self.assertEqual(merged['processed_ids']['ocean'].count('new-source'), 1)
        # A normal-push retry against the already merged remote state is idempotent.
        self.assertEqual(self.merge(baseline, run, merged), merged)

    def test_remote_count_correction_and_new_run_post_both_survive(self):
        baseline = self.state()
        run = self.state(count=3, times=[self.first, self.second, self.third])
        # Remote reconciled three older unlogged confirmations and added a new post.
        latest = self.state(count=6, times=[self.first, self.second, self.fourth])

        merged = self.merge(baseline, run, latest)

        self.assertEqual(merged['daily_stats']['ocean']['count'], 7)
        self.assertEqual(self.merge(baseline, run, merged), merged)

    def test_legacy_unlogged_baseline_counts_survive_parallel_posts(self):
        baseline = self.state(count=4)
        run = self.state(count=5, times=[self.first, self.second, self.third])
        latest = self.state(count=5, times=[self.first, self.second, self.fourth])

        merged = self.merge(baseline, run, latest)

        self.assertEqual(merged['daily_stats']['ocean']['count'], 6)

    def test_day_rollover_preserves_history_but_only_counts_current_utc_day(self):
        old_time = '2026-10-06T23:50:00+00:00'
        baseline = self.state(count=9, times=[old_time])
        baseline['daily_stats']['ocean']['date'] = '2026-10-06'
        run = copy.deepcopy(baseline)
        # This local Nepal timestamp falls on October 7 in UTC.
        latest = self.state(count=1, times=['2026-10-07T06:45:00+05:45'])

        merged = self.merge(baseline, run, latest)

        self.assertEqual(merged['daily_stats']['ocean']['date'], '2026-10-07')
        self.assertEqual(merged['daily_stats']['ocean']['count'], 1)
        self.assertEqual(len(merged['daily_stats']['ocean']['timestamps']), 2)
        self.assertEqual(merged['daily_stats']['ocean']['last_published_time'],
                         datetime.fromisoformat(self.first).timestamp())

    def test_latest_remote_channel_and_conflicting_unknown_scalar_are_preserved(self):
        baseline = self.state()
        run, latest = copy.deepcopy(baseline), copy.deepcopy(baseline)
        baseline['annotation'] = 'old'
        run['annotation'] = 'runner edit'
        latest['annotation'] = 'remote edit'
        latest['processed_ids']['new-page'] = ['remote-only-source']
        latest['daily_stats']['new-page'] = {
            'date': '2026-10-07', 'count': 1, 'timestamps': [self.fourth],
            'last_published_time': datetime.fromisoformat(self.fourth).timestamp(),
        }

        merged = self.merge(baseline, run, latest)

        self.assertEqual(merged['annotation'], 'remote edit')
        self.assertEqual(merged['processed_ids']['new-page'], ['remote-only-source'])
        self.assertEqual(merged['daily_stats']['new-page']['count'], 1)

    def test_conflicting_source_history_for_same_meta_confirmation_is_rejected(self):
        baseline, run, latest = self.state(), self.state(), self.state()
        run['confirmed_publications'] = [
            {'channel_id': 'ocean', 'published_id': '100_123', 'post_id': 'one-source'}]
        latest['confirmed_publications'] = [
            {'channel_id': 'ocean', 'published_id': '100_123', 'post_id': 'different-source'}]

        with self.assertRaisesRegex(StateSyncError, 'conflicting source history'):
            self.merge(baseline, run, latest)

    def test_malformed_state_is_rejected_without_mutating_evidence(self):
        invalid = [
            [],
            {'daily_stats': []},
            {'daily_stats': {'ocean': []}},
            {'daily_stats': {'ocean': {'timestamps': '2026-10-07T01:00:00Z'}}},
            {'daily_stats': {'ocean': {'timestamps': ['not-a-date']}}},
        ]
        for count in (-1, True, '3'):
            invalid.append({'daily_stats': {'ocean': {'count': count}}})
        for last in (float('nan'), float('inf'), True, '1791320400'):
            invalid.append({'daily_stats': {'ocean': {'last_published_time': last}}})
        for state in invalid:
            with self.subTest(state=state):
                encoded_before = json.dumps(state, sort_keys=True)
                with self.assertRaises(StateSyncError):
                    self.merge({}, state, {})
                self.assertEqual(json.dumps(state, sort_keys=True), encoded_before)


class PipelineRecoverySnapshotTests(unittest.TestCase):
    def test_unreadable_snapshot_rejects_instead_of_silently_resetting_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(StateSyncError):
                _read_json(path, {})
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_invalid_prior_receipt_is_backed_up_and_never_cleared(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / 'checkout'
            repository.mkdir()
            recovery = Path(temporary) / 'recovery'
            state = {'processed_ids': {'ocean': ['already-posted']}}
            (repository / 'state.json').write_text(json.dumps(state), encoding='utf-8')
            journal = repository / 'publication_journal.json'
            original = json.dumps({'publications': [{'published_id': 'invalid-receipt'}]})
            journal.write_text(original, encoding='utf-8')

            with patch('sync_pipeline_state._git', return_value=SimpleNamespace(stdout='verified-head\n')):
                with self.assertRaisesRegex(ValueError, 'invalid field schema'):
                    capture_baseline(repository, recovery)

            self.assertEqual(journal.read_text(encoding='utf-8'), original)
            self.assertEqual((recovery / 'prior_publication_journal.json').read_text(encoding='utf-8'), original)
            self.assertEqual(json.loads((repository / 'state.json').read_text(encoding='utf-8')), state)
            self.assertEqual(json.loads((recovery / 'baseline.json').read_text(encoding='utf-8'))['state'], state)


if __name__ == '__main__':
    unittest.main()
