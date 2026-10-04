import ast
import re
import unittest
from pathlib import Path
module = ast.parse(Path('modules/llm_transformer.py').read_text(encoding='utf-8'))
namespace = {'re': re}
exec(compile(ast.Module(body=[n for n in module.body if isinstance(n, (ast.FunctionDef, ast.Assign))], type_ignores=[]), '<headlines>', 'exec'), namespace)
def join(lines):
    return ' '.join(''.join(t['text'] for t in line) for line in lines)
class CompleteHeadlineTests(unittest.TestCase):
    def test_full_key_information_survives_long_sentence(self):
        source = 'Two false killer whale calves were documented swimming alongside their mothers in coastal waters during a marine survey.'
        headline = join(namespace['format_factual_overlay'](source))
        self.assertIn('COASTAL WATERS', headline)
        self.assertIn('MARINE SURVEY', headline)
        self.assertIn('FALSE KILLER WHALE', headline)
    def test_generic_incomplete_ai_hook_falls_back_to_complete_source(self):
        source = 'Two false killer whale calves were documented alongside their mothers in coastal waters.'
        payload = {'overlay_lines': [[{'text': 'The real story: Two false killer whale calves were documented', 'type': 'white'}]]}
        headline = join(namespace['finalize_news_overlay'](payload, source, 'en'))
        self.assertNotIn('THE REAL STORY', headline)
        self.assertIn('COASTAL WATERS', headline)
    def test_complete_hook_is_preserved(self):
        payload = {'headline': 'Two false killer whale calves swim beside their mothers in coastal waters'}
        self.assertIn('THEIR MOTHERS', join(namespace['finalize_news_overlay'](payload, 'source', 'en')))
