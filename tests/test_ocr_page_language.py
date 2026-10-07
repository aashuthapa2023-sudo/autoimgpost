import sys,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from modules import image_cleaner as cleaner

class PageOCRTests(unittest.TestCase):
    def test_language_models_are_reused_and_do_not_share_alphabets(self):
        factory=Mock(side_effect=[object(),object()]);threads=Mock()
        with patch.dict(sys.modules,{'easyocr':SimpleNamespace(Reader=factory),'torch':SimpleNamespace(set_num_threads=threads)}), \
             patch.object(cleaner,'_source_text_reader',None),patch.object(cleaner,'_english_text_reader',None):
            english=cleaner.source_text_reader('en');nepali=cleaner.source_text_reader('ne')
            self.assertIs(cleaner.source_text_reader('en'),english)
            self.assertIs(cleaner.source_text_reader('ne'),nepali)
            self.assertIsNot(english,nepali)
        self.assertEqual([call.args[0] for call in factory.call_args_list],[['en'],['en','ne','hi']])
        self.assertTrue(all(1<=call.args[0]<=4 for call in threads.call_args_list))

    def test_residual_scan_uses_the_same_page_language(self):
        image=np.random.default_rng(22).integers(30,220,(800,800,3),dtype=np.uint8)
        with patch.object(cleaner,'detect_source_text_boxes',return_value=cleaner.SourceTextBoxes()) as scan:
            self.assertIs(cleaner.erase_text_and_watermarks(image,[],language='en'),image)
        self.assertEqual(scan.call_args.kwargs['language'],'en')

if __name__=='__main__':unittest.main()
