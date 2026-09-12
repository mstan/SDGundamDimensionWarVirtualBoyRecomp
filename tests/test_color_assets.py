"""Protect cartridge map semantics and source coordinates used for stereo masks."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from color_assets import Artwork, decode_map, fingerprint


class CartridgeArtworkTests(unittest.TestCase):
    def test_mixed_runs_and_word_wrap(self):
        # Literal, repeat, increasing and decreasing runs, including wraparound.
        words = [0x1001, 0x2000, 0x1000, 0x2001, 17,
                 0x3002, 65534, 0x4002, 1, 0x2ff5, 0, 0]
        cells, end = decode_map(struct.pack('<12H', *words), 0)
        self.assertEqual(cells[:10], [0x2000, 0x1000, 17, 17, 65534, 65535, 0, 1, 0, 65535])
        self.assertEqual(cells[10:], [0] * 4086)
        self.assertEqual(end, 24)

    def test_invalid_and_incomplete_maps(self):
        for words in ([0], [0x5000, 0, 0], [0x2fff, 0, 0x2000, 0, 0]):
            with self.subTest(words=words), self.assertRaises(ValueError):
                decode_map(struct.pack(f'<{len(words)}H', *words), 0)

    def test_stereo_flips_preserve_unflipped_identity(self):
        # One nonzero source texel, repeated with all four flip combinations.
        tile = struct.pack('<8H', 0, 0, 3 << 2, 0, 0, 0, 0, 0)
        art = Artwork('stereo', 2, 2, [0, 0x2000, 0x1000, 0x3000], tile, 0, 0, 3)
        texels = list(art.texels())
        self.assertEqual([(t[0], t[1]) for t in texels], [(1, 2), (14, 2), (1, 13), (14, 13)])
        self.assertTrue(all(t[2:] == (fingerprint(tile), 1, 2, 3, 0) for t in texels))

    def test_out_of_bank_tile_is_rejected(self):
        art = Artwork('invalid', 1, 1, [1], bytes(16), 0, 0, 3)
        with self.assertRaises(ValueError):
            list(art.texels())


if __name__ == '__main__':
    unittest.main()
