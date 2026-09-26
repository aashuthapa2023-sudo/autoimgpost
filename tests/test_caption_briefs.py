import ast
import re
import unittest
from pathlib import Path

# Test the pure caption cleaner without loading optional network/AI dependencies.
source = Path('modules/llm_transformer.py').read_text(encoding='utf-8')
node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'clean_and_deduplicate_source_caption')
namespace = {'re': re}
exec(compile(ast.Module(body=[node], type_ignores=[]), '<caption cleaner>', 'exec'), namespace)
clean = namespace[node.name]

class CaptionTests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
