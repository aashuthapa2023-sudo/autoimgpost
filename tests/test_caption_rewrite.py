import ast
import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

module = ast.parse(Path('modules/llm_transformer.py').read_text(encoding='utf-8'))
nodes = [n for n in module.body if isinstance(n, (ast.FunctionDef, ast.Assign))]
namespace = dict(os=os, re=re, json=json)
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<rewrite>', 'exec'), namespace)

class CaptionRewriteTests(unittest.TestCase):
    def test_nepali_caption_reaches_ai_unchanged(self):
        caption = 'काठमाडौंमा नयाँ बस सेवा सुरु भएको छ।' + ' थप स्रोत तथ्य।' * 30
        calls = []
        def post(url, **kwargs):
            calls.append(kwargs['json'])
            return SimpleNamespace(status_code=200, json=lambda: {'choices': [{'message': {'content': json.dumps({'headline': 'काठमाडौंमा नयाँ बस सेवा सञ्चालनमा आएको छ', 'rewritten_caption': 'काठमाडौंमा नयाँ बस सेवा सञ्चालनमा आएको छ।'}, ensure_ascii=False)}}]})
        namespace['requests'] = SimpleNamespace(post=post)
        from unittest.mock import patch
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test'}):
            result = namespace['generate_social_payload'](caption, language='ne')
        self.assertTrue(calls)
        self.assertIn(caption, calls[0]['messages'][1]['content'])
        self.assertIn('सञ्चालनमा', result['rewritten_caption'])
