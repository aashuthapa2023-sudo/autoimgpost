import ast
import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

tree = ast.parse(Path('modules/llm_transformer.py').read_text(encoding='utf-8'))
namespace = dict(re=re, os=os, json=json)
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef))], type_ignores=[]), '<quality>', 'exec'), namespace)
validate = namespace['validate_model_payload']


class PayloadQualityTests(unittest.TestCase):
    source = 'Two false killer whale calves were documented alongside their mothers in coastal waters during a marine survey.'

    def payload(self, **changes):
        payload = {'headline': 'Two false killer whale calves swim beside their mothers in coastal waters',
                   'rewritten_caption': 'A marine survey documented two false killer whale calves alongside their mothers in coastal waters.'}
        payload.update(changes)
        return payload

    def test_complete_grounded_payload(self):
        result = validate(self.payload(), self.source, content_topic='ocean')
        self.assertIn('FALSE KILLER WHALE', namespace['overlay_text'](result['overlay_lines']))
        self.assertIn('#MarineLife', result['rewritten_caption'])

    def test_malformed_models_fail_closed(self):
        for payload in [[], 'caption', {}, {'headline': None}, self.payload(headline=['not', 'text']), self.payload(rewritten_caption=['not text'])]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate(payload, self.source)

    def test_invented_count_and_species_are_rejected(self):
        for headline in ['Three false killer whale calves swim beside their mothers in coastal waters', 'Two killer whale calves swim beside their mothers in coastal waters']:
            with self.subTest(headline=headline), self.assertRaises(ValueError):
                validate(self.payload(headline=headline), self.source)

    def test_unknown_artist_is_rejected(self):
        source = 'Taylor Swift released four songs.'
        with self.assertRaises(ValueError):
            validate({'headline': 'Adele releases four new songs', 'rewritten_caption': 'Adele has released four songs.'}, source, content_topic='music')

    def test_uncertainty_and_negation_cannot_be_dropped(self):
        for source, payload in [
            ('The study may identify a new coral species.', {'headline': 'Study identifies a new coral species', 'rewritten_caption': 'The study identifies a new coral species.'}),
            ('The film is not returning for another season.', {'headline': 'The film returns for another season', 'rewritten_caption': 'The film is returning for another season.'}),
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate(payload, source)

    def test_readability_and_complete_endings(self):
        for headline in ['The real story: Two whales are documented', 'Two whales swim near coastal waters and', ' '.join(['whales'] * 28), 'Two whales spotted...']:
            with self.subTest(headline=headline), self.assertRaises(ValueError):
                validate(self.payload(headline=headline), self.source)

    def test_grammatical_prefix_cannot_drop_essential_source_context(self):
        with self.assertRaises(ValueError):
            validate(self.payload(headline='Two false killer whale calves were documented'), self.source)

    def test_live_ranked_list_without_named_acts_is_skipped(self):
        source = 'These are the acts with the most Billboard 200 and Hot 100 No. 1s combined. See who made the list.'
        with self.assertRaises(ValueError):
            namespace['smart_heuristic_headline'](source, content_topic='music')

    def test_live_nepali_vague_preparation_is_not_a_headline(self):
        self.assertFalse(namespace['headline_is_usable']('नेपाल राष्ट्र बैंकको ठूलो तयारी', 'ne'))

    def test_removed_byline_is_not_available_as_a_story_fact(self):
        source = 'Overacting will debut on Netflix in November 2026. By Jacob Robinson • @JRobinsonWoN October 5th, 2026 - 6:18 am'
        with self.assertRaises(ValueError):
            validate({'headline': 'Jacob Robinson joins Netflix in November 2026', 'rewritten_caption': 'Jacob Robinson will join Netflix in November 2026.'}, source)

    def test_all_languages_receive_same_complete_headline_rules(self):
        prompt = namespace['build_system_prompt']('ne', 'Nepal Speaks', 'news')
        self.assertNotIn('strictly 2 lines', prompt)
        self.assertIn('do not truncate', prompt)
        with self.assertRaises(ValueError):
            namespace['smart_heuristic_headline']('काठमाडौंमा ' + 'विवरण ' * 35 + 'सुरु भएको छ।', language='ne')

    def test_invalid_provider_output_falls_back_to_source(self):
        response = SimpleNamespace(status_code=200, json=lambda: {'choices': [{'message': {'content': json.dumps(self.payload(headline='Three killer whale calves swim in coastal waters'))}}]})
        namespace['requests'] = SimpleNamespace(post=lambda *args, **kwargs: response)
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test', 'GEMINI_API_KEY': '', 'OPENROUTER_API_KEY': ''}):
            result = namespace['generate_social_payload'](self.source, channel_id='oceans_secret')
        self.assertIn('Two false killer whale calves', result['headline'])
        self.assertNotIn('Three', result['headline'])

    def test_invalid_first_provider_tries_next_provider(self):
        calls = []
        def post(url, **kwargs):
            calls.append(url)
            payload = [] if 'groq' in url else self.payload()
            return SimpleNamespace(status_code=200, json=lambda: {'choices': [{'message': {'content': json.dumps(payload)}}]})
        namespace['requests'] = SimpleNamespace(post=post)
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test', 'GEMINI_API_KEY': '', 'OPENROUTER_API_KEY': 'test'}):
            result = namespace['generate_social_payload'](self.source, channel_id='oceans_secret')
        self.assertEqual(len(calls), 2)
        self.assertIn('swim beside', result['headline'])

    def test_unrelated_source_is_rejected_before_ai(self):
        calls = []
        namespace['requests'] = SimpleNamespace(post=lambda *args, **kwargs: calls.append(args))
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test'}), self.assertRaises(ValueError):
            namespace['generate_social_payload']('A Netflix series has premiered.', channel_id='oceans_secret')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
