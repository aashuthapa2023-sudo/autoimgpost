import unittest
from modules.source_layout import get_source_layout

class SourceLayoutTests(unittest.TestCase):
    def test_page_default_is_preserved_when_source_has_no_override(self):
        self.assertEqual(get_source_layout({'poster_style':{'text_position':'bottom'}}, {'source_page_url':'https://www.facebook.com/newsource'}, 'top')['text_position'],'bottom')
    def test_source_can_return_branding_to_headline_panel(self):
        channel={'poster_style':{'logo_position':'top-right'},'source_layouts':{'example':{'logo_position':'with-text'}}}
        self.assertEqual(get_source_layout(channel,{'source_page_url':'https://www.facebook.com/example'})['logo_position'],'with-text')
    def setUp(self):
        self.channel = {'source_layouts': {'smartmedianp': {'text_position': 'top', 'source_header_fraction': 0.4}}}
    def test_smart_media_uses_top(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/smartmedianp/'}), {'text_position': 'top', 'source_header_fraction': 0.4})
    def test_logo_placement_is_forwarded(self):
        self.channel['source_layouts']['smartmedianp']['logo_position'] = 'top-right'
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/smartmedianp'})['logo_position'], 'top-right')
    def test_invalid_logo_placement_uses_default(self):
        self.channel['source_layouts']['smartmedianp']['logo_position'] = 'invalid'
        self.assertNotIn('logo_position', get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/smartmedianp'}))
    def test_auto_uses_detected_top(self):
        self.assertEqual(get_source_layout({}, {'source_page_url': 'https://www.facebook.com/example'}, 'top'), {'text_position': 'top'})
    def test_explicit_bottom_overrides_detection(self):
        channel = {'source_layouts': {'example': {'text_position': 'bottom'}}}
        self.assertEqual(get_source_layout(channel, {'source_page_url': 'https://www.facebook.com/example'}, 'top'), {'text_position': 'bottom'})
    def test_profile_ids_have_separate_layouts(self):
        channel = {'source_layouts': {'61587221117884': {'text_position': 'top'}, '61589616333583': {'text_position': 'bottom'}}}
        for page_id, position in [('61587221117884', 'top'), ('61589616333583', 'bottom')]:
            self.assertEqual(get_source_layout(channel, {'source_page_url': 'https://www.facebook.com/profile.php?id=' + page_id})['text_position'], position)
    def test_other_sources_keep_bottom(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://www.facebook.com/HimaliMedia'}), {'text_position': 'bottom'})
    def test_other_channels_keep_bottom(self):
        self.assertEqual(get_source_layout({}, {'source_page_url': 'https://www.facebook.com/smartmedianp'}), {'text_position': 'bottom'})
    def test_unrelated_domain_does_not_match(self):
        self.assertEqual(get_source_layout(self.channel, {'source_page_url': 'https://example.com/smartmedianp'}), {'text_position': 'bottom'})

if __name__ == '__main__': unittest.main()
