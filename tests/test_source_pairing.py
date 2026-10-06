import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from modules import ingestion


class SourcePairingTests(unittest.TestCase):
    def extract(self, story):
        html = ''.join('<script type="application/json">' + json.dumps(node) + '</script>'
                       for node in [{}, {}, {'story': story}])
        response = SimpleNamespace(status_code=200, url='https://www.facebook.com/source', text=html)
        with patch.object(ingestion.requests, 'get', return_value=response), patch.object(ingestion, 'fetch_facebook_mobile_playwright', return_value=[]):
            return ingestion.fetch_facebook_public_posts('source')

    def story(self, attachments, **extra):
        return dict(post_id='999999999', creation_time=int(time.time()),
                    message={'text': 'The complete caption belongs to this source photograph.'}, attachments=attachments, **extra)

    def photo(self, photo_id='111111111', url='https://cdn.example/first.jpg'):
        return {'media': {'__typename': 'Photo', 'id': photo_id, 'image': {'uri': url}}}

    def test_album_photo_id_and_url_belong_to_same_attachment(self):
        posts = self.extract(self.story([self.photo(), self.photo('222222222', 'https://cdn.example/second.jpg')]))
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['photo_id'], '111111111')
        self.assertEqual(posts[0]['image_url'], 'https://cdn.example/first.jpg')

    def test_shared_prefix_does_not_erase_a_changed_fact(self):
        prefix='The annual music report has updated its figures for releases and now records '
        first=self.story([self.photo()])
        first['message']={'text':prefix+'31000 songs.'}
        second=self.story([self.photo('222222222','https://cdn.example/second.jpg')])
        second['message']={'text':prefix+'32000 songs.'}
        self.assertNotEqual(self.extract(first)[0]['caption_fingerprint'],self.extract(second)[0]['caption_fingerprint'])

    def test_subattachment_photo_id_and_url_stay_together(self):
        album = {'subattachments': {'nodes': [self.photo(), self.photo('222222222', 'https://cdn.example/second.jpg')]}}
        posts = self.extract(self.story([album]))
        self.assertEqual(posts[0]['photo_id'], '111111111')
        self.assertEqual(posts[0]['image_url'], 'https://cdn.example/first.jpg')

    def test_video_and_link_previews_are_rejected(self):
        for attachment in [
            {'media': {'__typename': 'Video', 'id': '333333333', 'preview_image': {'uri': 'https://cdn.example/video.jpg'}}},
            {'__typename': 'ExternalLinkAttachment', 'large_share_image': {'uri': 'https://cdn.example/article.jpg'}, 'media': {'__typename': 'Photo', 'id': '333333333', 'image': {'uri': 'https://cdn.example/article.jpg'}}},
            {'media': {'id': '333333333', 'preview_image': {'uri': 'https://cdn.example/unknown-preview.jpg'}}},
            {'target': {'__typename': 'ExternalUrl'}, 'media': {'__typename': 'Photo', 'id': '333333333', 'image': {'uri': 'https://cdn.example/article.jpg'}}},
            {'target': {'__typename': 'Story', 'media': {'__typename': 'Photo', 'id': '333333333', 'image': {'uri': 'https://cdn.example/shared.jpg'}}}},
        ]:
            with self.subTest(attachment=attachment):
                self.assertEqual(self.extract(self.story([attachment])), [])

    def test_video_is_not_selected_when_later_real_photo_exists(self):
        video = {'media': {'__typename': 'Video', 'id': '333333333', 'preview_image': {'uri': 'https://cdn.example/video.jpg'}}}
        posts = self.extract(self.story([video, self.photo()]))
        self.assertEqual(posts[0]['photo_id'], '111111111')

    def test_nested_shared_caption_cannot_use_outer_photo(self):
        wrapper = {'__typename': 'CometFeedStoryDefaultContentStrategy', 'post_id': '777777777',
                   'creation_time': int(time.time()), 'story': {'message': {'text': 'Caption belonging to an inner shared story.'}},
                   'attachments': [self.photo()]}
        self.assertEqual(self.extract(wrapper), [])

    def test_complete_shared_story_is_extracted_as_one_object(self):
        inner = self.story([self.photo()])
        wrapper = {'__typename': 'CometFeedStoryDefaultContentStrategy', 'post_id': '777777777', 'story': inner,
                   'attachments': [self.photo('444444444', 'https://cdn.example/outer.jpg')]}
        posts = self.extract(wrapper)
        self.assertEqual(posts[0]['post_id'], '999999999')
        self.assertEqual(posts[0]['image_url'], 'https://cdn.example/first.jpg')

    def test_truncated_message_is_not_treated_as_full_caption(self):
        for message in [{'text': 'A cut-off source caption… See more'}, {'text': 'An incomplete caption with more text', 'is_truncated': True}]:
            story = self.story([self.photo()])
            story['message'] = message
            with self.subTest(message=message):
                self.assertEqual(self.extract(story), [])

    def test_exact_long_message_is_preserved(self):
        caption = 'A complete source fact. ' * 60
        story = self.story([self.photo()])
        story['message']['text'] = caption
        self.assertEqual(self.extract(story)[0]['caption'], caption.strip())

    def test_unknown_timestamp_is_not_invented_as_recent(self):
        story = self.story([self.photo()])
        story.pop('creation_time')
        self.assertEqual(self.extract(story), [])
        self.assertEqual(ingestion.parse_relative_time('unknown'), 0)
        self.assertEqual(ingestion.parse_relative_time('10 months'), 0)

    def test_numeric_profile_and_direct_post_mobile_urls(self):
        for source, expected in [
            ('https://www.facebook.com/example/posts/123456789', 'https://m.facebook.com/example/posts/123456789'),
            ('https://www.facebook.com/profile.php?id=61587221117884', 'https://m.facebook.com/profile.php?id=61587221117884'),
            ('https://www.facebook.com/story.php?story_fbid=123&id=456', 'https://m.facebook.com/story.php?story_fbid=123&id=456'),
            ('61587221117884', 'https://m.facebook.com/61587221117884'),
        ]:
            self.assertEqual(ingestion.facebook_mobile_url(source), expected)

    def test_nepali_and_week_relative_times(self):
        with patch('time.time', return_value=2000000):
            self.assertEqual(ingestion.parse_relative_time('२ घण्टा'), 2000000 - 7200)
            self.assertEqual(ingestion.parse_relative_time('2w'), 2000000 - 1209600)


class MobileCaptionTests(unittest.TestCase):
    def card(self, **changes):
        card = {'postId': '999999999', 'photoId': '111111111', 'imgUrl': 'https://cdn.example/photo.jpg',
                'caption': 'An exact English source caption for this photograph.',
                'caption_verified': True, 'caption_complete': True, 'image_verified': True,
                'createdTime': int(time.time())}
        card.update(changes)
        return card

    def test_verified_english_and_nepali_messages_are_preserved_in_full(self):
        for caption in ['The artist released four songs. ' * 40, 'काठमाडौंमा नयाँ बस सेवा सुरु भएको छ। ' * 40]:
            posts = ingestion._posts_from_mobile_cards([self.card(caption=caption)])
            self.assertEqual(posts[0]['caption'], caption.strip())

    def test_alt_and_unverified_or_incomplete_caption_are_rejected(self):
        for changes in [{'caption': '', 'alt': 'नेपालमा नयाँ गीत सार्वजनिक भएको छ'},
                        {'caption_verified': False}, {'caption_complete': False}, {'image_verified': False},
                        {'caption': 'The source caption is incomplete... See more'}]:
            self.assertEqual(ingestion._posts_from_mobile_cards([self.card(**changes)]), [])

    def test_unknown_mobile_timestamp_is_rejected(self):
        self.assertEqual(ingestion._posts_from_mobile_cards([self.card(createdTime=0, timeStr='unknown')]), [])


if __name__ == '__main__':
    unittest.main()
