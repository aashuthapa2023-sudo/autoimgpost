import ast
import re
import unittest
from pathlib import Path

module = ast.parse(Path('modules/llm_transformer.py').read_text(encoding='utf-8'))
namespace = {'re': re}
nodes = [n for n in module.body if isinstance(n, (ast.FunctionDef, ast.Assign))]
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<overlay>', 'exec'), namespace)

class NepaliOverlayTests(unittest.TestCase):
    def test_preserves_subject_numbers_and_final_action(self):
        text = 'नेपाल क्रिकेट संघले दुई नयाँ खेलाडीलाई राष्ट्रिय टोलीमा समावेश गरेको छ'
        lines = namespace['extract_meaningful_nepali_overlay'](text + '।')
        joined = ' '.join(''.join(t['text'] for t in line) for line in lines)
        self.assertEqual(joined, text + '...')
        self.assertEqual(len(lines), 3)

    def test_short_complete_headline(self):
        text = 'काठमाडौंमा नयाँ बस सेवा सुरु भएको छ'
        lines = namespace['extract_meaningful_nepali_overlay'](text)
        self.assertEqual(len(lines), 2)
        self.assertEqual(' '.join(''.join(t['text'] for t in line) for line in lines), text + '...')

    def test_no_generic_filler_for_empty_source(self):
        with self.assertRaises(ValueError):
            namespace['extract_meaningful_nepali_overlay']('https://example.com')

if __name__ == '__main__':
    unittest.main()
