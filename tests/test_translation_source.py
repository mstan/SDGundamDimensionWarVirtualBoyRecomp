"""Negative authoring cases must fail before a package or header is emitted."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('translation', Path(__file__).resolve().parents[1]/'tools/build_translation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TextSourceTests(unittest.TestCase):
    def setUp(self):
        self.source={'format':1,'language':'en','glyphs':{'A':'41',' ':'20'},
                     'entries':[{'id':'line','offset':'0x20','capacity':4,'text':'A','padding':'space'}]}
    def test_native_padding_and_nul(self):
        self.assertEqual(m.encode_entries(self.source),[(32,b'A   ')])
        self.source['entries'][0]['padding']='nul'
        self.assertEqual(m.encode_entries(self.source),[(32,b'A\0\0\0')])
    def test_unsupported_glyph_rejected(self):
        self.source['entries'][0]['text']='B'
        with self.assertRaisesRegex(ValueError,'Unsupported glyph'):m.encode_entries(self.source)
    def test_overflow_rejected(self):
        self.source['entries'][0]['text']='AAAAA'
        with self.assertRaisesRegex(ValueError,'capacity'):m.encode_entries(self.source)
    def test_control_mapping_rejected(self):
        self.source['glyphs']['A']='00'
        with self.assertRaisesRegex(ValueError,'native codes'):m.encode_entries(self.source)
    def test_overlap_rejected(self):
        extra=copy.deepcopy(self.source['entries'][0]);extra.update(id='next',offset='0x22')
        self.source['entries'].append(extra)
        with self.assertRaisesRegex(ValueError,'Overlapping'):m.encode_entries(self.source)

if __name__=='__main__':unittest.main()
