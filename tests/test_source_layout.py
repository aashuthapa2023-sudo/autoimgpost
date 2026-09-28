import unittest
from modules.source_layout import get_source_layout

class SourceLayoutTests(unittest.TestCase):
    def setUp(self):
        self.channel = {'source_layouts': {'smartmedianp': {'text_position': 'top', 'source_header_fraction': 0.4}}}
    def test_smart_media_uses_top(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/smartmedianp/'}), {'text_position': 'top', 'source_header_fraction': 0.4})
    def test_other_sources_keep_bottom(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/HimaliMedia'}), {'text_position': 'bottom'})
    def test_other_channels_keep_bottom(self):
        self.assertEqual(get_source_layout({}, {'source_page_url': 'https://www.facebook.com/smartmedianp'}), {'text_position': 'bottom'})
    def test_unrelated_domain_does_not_match(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://example.com/smartmedianp'}), {'text_position': 'bottom'})

if __name__ == '__main__': unittest.main()
