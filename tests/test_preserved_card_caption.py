import ast
import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


tree = ast.parse(Path('modules/llm_transformer.py').read_text(encoding='utf-8'))
namespace = dict(re=re, os=os, json=json)
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))],
                        type_ignores=[]), '<preserved-caption>', 'exec'), namespace)
generate = namespace['generate_preserved_card_payload']


class PreservedCardCaptionTests(unittest.TestCase):
    headline = 'Marine researchers document two whale calves near the Pacific coast'
    source = (headline + ' after a lengthy expedition involving multiple observation teams who collected photographs '
              'and detailed measurements for a continuing survey of local marine wildlife.')
    empty_keys = {'GROQ_API_KEY': '', 'GEMINI_API_KEY': '', 'OPENROUTER_API_KEY': ''}

    def payload(self, source=None, headline=None, **options):
        return generate(self.source if source is None else source, self.headline if headline is None else headline,
                        channel_name="Ocean's Secret", channel_id='oceans_secret', content_topic='ocean', **options)

    def test_long_complete_caption_keeps_its_reviewed_card_headline_without_another_headline(self):
        self.assertGreater(len(self.source.split()), 22)
        provider = Mock(side_effect=AssertionError('No provider should be required'))
        with patch.dict(os.environ, self.empty_keys), patch.dict(namespace, generate_social_payload=provider):
            result = self.payload()
        self.assertEqual(result['headline'], self.headline)
        self.assertEqual(result['rewritten_caption'].split('\n\n')[0], self.source)
        self.assertEqual(result['headline_origin'], 'preserved_source_card')
        self.assertEqual(namespace['overlay_text'](result['overlay_lines']).lower(), self.headline.lower())
        provider.assert_not_called()

    def test_usable_existing_provider_caption_keeps_the_reviewed_headline(self):
        rewritten = 'Marine researchers document two whale calves near the Pacific coast during a survey.'
        provider = Mock(return_value={'headline': 'A different unused display title', 'rewritten_caption': rewritten})
        with patch.dict(os.environ, {**self.empty_keys, 'GROQ_API_KEY': 'test'}), patch.dict(namespace, generate_social_payload=provider):
            result = self.payload(editorial_style='Marine discoveries')
        self.assertEqual(result['headline'], self.headline)
        self.assertEqual(result['rewritten_caption'].split('\n\n')[0], rewritten)
        provider.assert_called_once_with(self.source, 'en', "Ocean's Secret", 'oceans_secret', 'ocean', 'Marine discoveries')

    def test_provider_headline_failure_falls_back_to_the_clean_source_caption(self):
        provider = Mock(side_effect=ValueError('Source needs editorial review: no complete readable headline'))
        with patch.dict(os.environ, {**self.empty_keys, 'GROQ_API_KEY': 'test'}), patch.dict(namespace, generate_social_payload=provider):
            result = self.payload()
        self.assertEqual(result['rewritten_caption'].split('\n\n')[0], self.source)
        self.assertEqual(result['headline'], self.headline)

    def test_provider_caption_with_changed_facts_is_rejected_in_favor_of_source(self):
        provider = Mock(return_value={'rewritten_caption': 'Marine researchers document three whale calves near the Pacific coast.'})
        with patch.dict(os.environ, {**self.empty_keys, 'GEMINI_API_KEY': 'test'}), patch.dict(namespace, generate_social_payload=provider):
            result = self.payload()
        self.assertIn('two whale calves', result['rewritten_caption'])
        self.assertNotIn('three whale calves', result['rewritten_caption'])

    def test_source_caption_cleanup_removes_repetition_and_promotion(self):
        with patch.dict(os.environ, self.empty_keys):
            result = self.payload(source=self.source + '\n\n' + self.source + '\nDetails in comments.')
        self.assertEqual(result['rewritten_caption'].count('lengthy expedition'), 1)
        self.assertNotIn('Details in comments', result['rewritten_caption'])

    def test_unusable_or_changed_reviewed_titles_are_rejected_before_providers(self):
        provider = Mock()
        bad_titles = [self.headline.replace('two', 'three'), self.headline.replace('Pacific', 'Atlantic'),
                      'Marine researchers document two whale calves and', self.headline + '...', 'Marine whales']
        with patch.dict(os.environ, {**self.empty_keys, 'GROQ_API_KEY': 'test'}), patch.dict(namespace, generate_social_payload=provider):
            for headline in bad_titles:
                with self.subTest(headline=headline), self.assertRaises(ValueError):
                    self.payload(headline=headline)
        provider.assert_not_called()

    def test_missing_qualifiers_and_negations_cannot_be_approved(self):
        with patch.dict(os.environ, self.empty_keys):
            for source in [self.source.replace('document', 'may document'), self.source.replace('document', 'do not document')]:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    self.payload(source=source)

    def test_empty_teaser_and_offtopic_sources_are_rejected(self):
        with patch.dict(os.environ, self.empty_keys):
            for source in ['', 'Read more about marine whales.', 'Comment below about marine whales.',
                           'A Netflix series is returning with a new season.']:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    self.payload(source=source)

    def test_wrong_page_language_is_rejected(self):
        with patch.dict(os.environ, self.empty_keys), self.assertRaises(ValueError):
            self.payload(language='ne')


if __name__ == '__main__':
    unittest.main()
