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
