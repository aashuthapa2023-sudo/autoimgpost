import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from modules.quality_log import record_rejection,ready_candidates,profile_signature


class QualityRetryTests(unittest.TestCase):
    def test_bad_candidate_does_not_starve_next_candidate(self):
        channel={'channel_id':'test','poster_style':{'min_font_size':68}}
        posts=[{'post_id':'bad'}, {'post_id':'next'}]
        with tempfile.TemporaryDirectory() as directory, patch('modules.quality_log.time.time',return_value=1000):
            report=Path(directory)/'quality.json'
            record_rejection('test','bad','photo_extraction','Text covers the photo',path=report,policy_signature=profile_signature(channel))
            self.assertEqual(ready_candidates(channel,posts,path=report),[posts[1]])
            self.assertEqual(ready_candidates(channel,posts,path=report,bypass=True),posts)
            changed={**channel,'poster_style':{'min_font_size':70}}
            self.assertEqual(ready_candidates(changed,posts,path=report),posts)

    def test_transient_download_recovers_without_marking_processed(self):
        channel={'channel_id':'test'}
        posts=[{'post_id':'failed'}]
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'quality.json'
            with patch('modules.quality_log.time.time',return_value=1000):
                record_rejection('test','failed','source_image','Unavailable',path=report,policy_signature=profile_signature(channel))
                self.assertEqual(ready_candidates(channel,posts,path=report),[])
            with patch('modules.quality_log.time.time',return_value=3701):
                self.assertEqual(ready_candidates(channel,posts,path=report),posts)

    def test_generic_processing_failure_waits_only_fifteen_minutes(self):
        channel={'channel_id':'test'}
        posts=[{'post_id':'failed'}, {'post_id':'next'}]
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'quality.json'
            with patch('modules.quality_log.time.time',return_value=1000):
                record_rejection('test','failed','transient_processing','Unconfirmed runtime failure',
                                 path=report,policy_signature=profile_signature(channel))
                self.assertEqual(ready_candidates(channel,posts,path=report),[posts[1]])
            with patch('modules.quality_log.time.time',return_value=1899):
                self.assertEqual(ready_candidates(channel,posts,path=report),[posts[1]])
            with patch('modules.quality_log.time.time',return_value=1901):
                self.assertEqual(ready_candidates(channel,posts,path=report),[posts[1],posts[0]])

    def test_expired_transient_retries_keep_relative_order_after_untried_candidates(self):
        channel={'channel_id':'test'}
        posts=[{'post_id':value} for value in ['retry-one','new-one','retry-two','new-two']]
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'quality.json'
            with patch('modules.quality_log.time.time',return_value=1000):
                for post_id in ['retry-one','retry-two']:
                    record_rejection('test',post_id,'transient_processing','Unconfirmed failure',
                                     path=report,policy_signature=profile_signature(channel))
            with patch('modules.quality_log.time.time',return_value=1901):
                self.assertEqual(ready_candidates(channel,posts,path=report),[posts[1],posts[3],posts[0],posts[2]])
                self.assertEqual(ready_candidates(channel,posts,path=report,bypass=True),posts)
                changed={**channel,'content_topic':'music'}
                self.assertEqual(ready_candidates(changed,posts,path=report),posts)
