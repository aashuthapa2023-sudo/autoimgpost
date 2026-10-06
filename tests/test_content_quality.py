import unittest
from modules.content_quality import channel_accepts_post

class TopicTests(unittest.TestCase):
    def test_ocean_subjects_allowed(self):
        for caption in ['False killer whale calves seen alongside mothers', 'A deep-sea brine pool', 'Coral reefs recovering after bleaching']:
            self.assertTrue(channel_accepts_post({'channel_id':'oceans_secret'}, {'caption':caption}))
    def test_entertainment_and_tags_rejected(self):
        for caption in ['Actor joins a documentary as executive producer', 'New film released #Ocean', "Ocean's Eleven returns to cinemas", 'The singer greeted a sea of fans', 'Celebrity news https://ocean.example/story']:
            self.assertFalse(channel_accepts_post({'channel_id':'oceans_secret'}, {'caption':caption}))
    def test_music_relevance_and_teaser_gate(self):
        channel = {'channel_id':'Music Store'}
        for caption in ['Fuerza Regida wins a Billboard award', 'Slayyyter performs at a sold-out concert', 'The singer David Byrne announces an album']:
            self.assertTrue(channel_accepts_post(channel, {'caption':caption}))
        for caption in ['Avengers reclaims the box-office title', "John Oliver buys memorabilia", 'David Byrne art auction', 'We asked a Harvard Law professor what it would take to win in court']:
            self.assertFalse(channel_accepts_post(channel, {'caption':caption}))
    def test_other_channels_unchanged(self):
        self.assertTrue(channel_accepts_post({'channel_id':'cinema'}, {'caption':'New film'}))

    def test_all_screen_pages_reject_unrelated_material(self):
        for page in ['daily_netflix', 'Anisha', 'Daily Hollywood']:
            self.assertTrue(channel_accepts_post({'channel_id':page}, {'caption':'A new Netflix series premieres in May'}))
            self.assertFalse(channel_accepts_post({'channel_id':page}, {'caption':'Scientists discovered a coral reef'}))

    def test_ocean_metaphors_and_brand_mentions_are_not_topic_evidence(self):
        for caption in ['Baby Shark reaches a music milestone', 'The Shark Tank cast attended an event', 'A sea of applause greeted the singer', 'Sports update #MarineLife', 'Sports update ocean.example', 'Bitcoin whales buy more tokens']:
            self.assertFalse(channel_accepts_post({'channel_id':'oceans_secret'}, {'caption':caption}))

    def test_configured_screen_alias_rejects_ocean_source(self):
        self.assertFalse(channel_accepts_post({'content_topic': 'screen'}, {'caption': 'A whale calf swims beside its mother'}))
        self.assertTrue(channel_accepts_post({'content_topic': 'screen'}, {'caption': 'Bridgerton returns to Netflix for season six'}))
