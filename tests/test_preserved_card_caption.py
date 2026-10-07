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

    def test_uncertainty_in_an_unrelated_followup_does_not_change_the_reviewed_fact(self):
        followup = 'The marine survey may continue next year to document more whales.'
        source = self.headline + '.\n\n' + followup
        with patch.dict(os.environ, self.empty_keys):
            result = self.payload(source=source)
        self.assertEqual(result['headline'], self.headline)
        self.assertIn(self.headline + '.', result['rewritten_caption'])
        self.assertIn(followup, result['rewritten_caption'])

    def test_negation_in_an_unrelated_followup_remains_in_caption_without_invalidating_title(self):
        followup = 'The marine survey is not finished and will continue next year.'
        source = self.headline + '.\n\n' + followup
        with patch.dict(os.environ, self.empty_keys):
            result = self.payload(source=source)
        self.assertEqual(result['headline'], self.headline)
        self.assertIn(followup, result['rewritten_caption'])

    def test_a_contradictory_matching_fact_is_rejected_despite_a_definite_matching_sentence(self):
        for followup in [self.headline + ' is not confirmed.',
                         'Reports that ' + self.headline.lower() + ' are unconfirmed.']:
            with patch.dict(os.environ, self.empty_keys), self.subTest(followup=followup), self.assertRaises(ValueError):
                self.payload(source=self.headline + '.\n\n' + followup)

    def test_empty_teaser_and_offtopic_sources_are_rejected(self):
        with patch.dict(os.environ, self.empty_keys):
            for source in ['', 'Read more about marine whales.', 'Comment below about marine whales.',
                           'A Netflix series is returning with a new season.']:
                with self.subTest(source=source), self.assertRaises(ValueError):
                    self.payload(source=source)

    def test_later_uncertainty_outside_the_brief_does_not_reject_copied_facts(self):
        source = (self.headline + '.\nScientists photographed the calves in coastal waters.\n'
                  'The team completed a marine survey.\nThe next marine survey may not happen this year.')
        with patch.dict(os.environ, self.empty_keys):
            result = self.payload(source=source)
        self.assertNotIn('may not happen', result['rewritten_caption'])
        self.assertIn('completed a marine survey', result['rewritten_caption'])

    def test_uppercase_contractions_preserve_negation_and_reject_opposite_claim(self):
        fact = "SCIENTISTS STILL CAN'T IDENTIFY THIS ANIMAL"
        source = fact + '\nScientists recorded the animal beneath the Pacific Ocean.'
        with patch.dict(os.environ, self.empty_keys):
            self.assertEqual(self.payload(source=source, headline=fact)['headline'], fact)
        grounding = namespace['check_source_grounding']
        for negative in ["can't", "won't", "doesn't", 'cannot']:
            with self.subTest(negative=negative):
                self.assertFalse(grounding('Scientists identify this animal',
                                           'Scientists '+negative+' identify this animal'))

    def test_exact_source_excerpt_joined_across_ellipsis_and_newline_is_supported(self):
        headline = "SCIENTISTS STILL CAN'T IDENTIFY THIS ANIMAL"
        source = (headline + '\nScientists went nearly 9,100 meters beneath the Pacific Ocean…\n\n'
                  'And their cameras recorded something they still cannot confidently identify.\n\n'
                  'The strange animal slowly glided toward the seafloor in the Izu-Ogasawara Trench.')
        with patch.dict(os.environ, self.empty_keys):
            result = self.payload(source=source, headline=headline)
        self.assertIn('9,100 meters', result['rewritten_caption'])
        self.assertIn('cannot confidently identify', result['rewritten_caption'])

    def test_wrong_page_language_is_rejected(self):
        with patch.dict(os.environ, self.empty_keys), self.assertRaises(ValueError):
            self.payload(language='ne')


if __name__ == '__main__':
    unittest.main()
