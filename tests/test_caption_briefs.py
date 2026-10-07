import ast
import re
import unittest
from pathlib import Path

# Test the pure caption cleaner without loading optional network/AI dependencies.
source = Path('modules/llm_transformer.py').read_text(encoding='utf-8')
nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.Assign))]
namespace = {'re': re}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<caption cleaner>', 'exec'), namespace)
clean = namespace['clean_and_deduplicate_source_caption']

class CaptionTests(unittest.TestCase):
    def test_repeated_sentences_in_one_paragraph_are_removed(self):
        clean = namespace['clean_and_deduplicate_source_caption']('Scientists found coral near the coast. Scientists found coral near the coast! Scientists found coral near the coast again.', channel_name="Ocean's Secret")
        self.assertEqual(clean.lower().count('scientists found coral'), 1)
        self.assertNotIn('#Entertainment', clean)

    def test_user_example(self):
        result = clean('{: [**bit.ly/3TpQ4Vm**](https://l.facebook.com/l.php?u=https%3A%2F%2Fbit.ly%2F3TpQ4Vm)\nTaylor Swift just gave fans four new songs to pore over. But what are they about?}')
        self.assertIn('Taylor Swift just gave fans four new songs to pore over.', result)
        for unwanted in ['bit.ly', 'https', 'what are they about', '[', '{']:
            self.assertNotIn(unwanted, result)

    def test_links_only_are_not_restored(self):
        for text in ['https://example.com/story', 'bit.ly/abc', 'www.example.com', '[Read](https://example.com)']:
            self.assertEqual(clean(text), '')

    def test_short_facts_and_nepali_are_preserved(self):
        for text in ['Taylor Swift released four songs.', 'आज नयाँ गीत सार्वजनिक भएको छ।']:
            self.assertTrue(clean(text).startswith(text))

    def test_brief_is_limited_to_three_sentences(self):
        body = clean('One fact happened. Another event followed. A third event occurred. A fourth event happened.').split('\n\n')[0]
        self.assertEqual(body.count('.'), 3)

    def test_near_identical_sentences_with_new_counts_are_preserved(self):
        body = clean('The survey documented 2 dolphins near the reef. The survey documented 3 dolphins near the reef.').split('\n\n')[0]
        self.assertIn('2 dolphins', body)
        self.assertIn('3 dolphins', body)

    def test_changed_action_is_not_deduplicated(self):
        body = clean('The whale approached the boat. The whale left the boat.').split('\n\n')[0]
        self.assertIn('approached', body)
        self.assertIn('left', body)

    def test_period_abbreviations_keep_dates_and_decimals(self):
        body = clean('Dr. Smith documented 2.5 meters of coral. The survey began on Oct. 4.').split('\n\n')[0]
        self.assertIn('Dr. Smith', body)
        self.assertIn('2.5', body)
        self.assertIn('Oct. 4', body)

    def test_live_overacting_byline_and_timestamp_are_removed(self):
        caption = "Netflix Sets November 2026 Release Date for Thai Action-Comedy 'Overacting'. A retired cop's delusions force his daughter to stage fake missions. By Jacob Robinson • @JRobinsonWoN October 5th, 2026 - 6:18 am Following a string of Thai releases, Netflix is gearing up to drop Overacting."
        body = clean(caption).split('\n\n')[0]
        self.assertIn('November 2026', body)
        self.assertIn('Overacting', body)
        for debris in ['Jacob Robinson', '@JRobinsonWoN', '6:18 am', 'October 5th']:
            self.assertNotIn(debris, body)

    def test_live_hercule_page_chrome_is_removed(self):
        caption = "BritBox's six-part Hercule adds Toby Stephens, Ralf Little and Katherine Parkinson alongside Edward Bluemel. Hercule Like Mystery Drama Crime Directors Jonny Campbell Writers Benji Walters Cast Edward Bluemel Attachment(s) Please respect our community guidelines. No links, inappropriate language, or spam."
        body = clean(caption).split('\n\n')[0]
        self.assertIn('Toby Stephens', body)
        for debris in ['Directors', 'Writers', 'Attachment', 'guidelines', 'spam', 'Like Mystery']:
            self.assertNotIn(debris, body)

    def test_live_dolly_caption_loses_read_more_teaser(self):
        caption = "Billboard has rounded up Dolly Parton's 25 best songs. See the list"
        body = clean(caption).split('\n\n')[0]
        self.assertEqual(body, "Billboard has rounded up Dolly Parton's 25 best songs.")

    def test_inline_chart_name_is_kept_while_brand_hashtags_are_removed(self):
        result = clean("Over 31,000 songs have graced the Billboard #Hot100 in the chart's 65-year history.\n\n#MusicStore #MusicNews #LiveMusic", content_topic='music')
        body = result.split('\n\n')[0]
        self.assertIn('Billboard Hot100', body)
        self.assertNotIn('MusicStore', body)

    def test_live_shakira_title_does_not_merge_with_the_following_fact(self):
        source = ('Shakira’s Madrid Concert Sets an Amazon Music Livestreaming Record\n\n'
            "Shakira's Oct. 3 concert in Madrid, featuring surprise guest Dua Lipa, marked this milestone for livestreamed performances on Amazon Music.\n\nDetails in comments.")
        body = clean(source, content_topic='music').split('\n\n')[0]
        sentences = namespace['split_clean_sentences'](body)
        self.assertEqual(sentences[0], "Shakira's Madrid Concert Sets an Amazon Music Livestreaming Record.")
        self.assertIn('Oct. 3', sentences[1])
        self.assertIn('Dua Lipa', sentences[1])
        self.assertNotIn('Details in comments', body)

    def test_comment_promotions_are_removed_without_removing_the_story(self):
        for promotion in ['Details in comments.', 'Full story in the comments.', 'More info in comments.']:
            with self.subTest(promotion=promotion):
                body = clean('Shakira set a concert livestreaming record.\n\n'+promotion, content_topic='music').split('\n\n')[0]
                self.assertEqual(body, 'Shakira set a concert livestreaming record.')

if __name__ == '__main__':
    unittest.main()
