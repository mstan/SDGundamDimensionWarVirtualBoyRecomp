"""Check shared menu materials at every captured position in both eyes.

Run after validate_color.py, which independently checks actual packaged RGB,
native brightness and unchanged guest/raw/audio planes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
from audit_color_coverage import Materials
from color_assets import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--captures', type=Path, nargs='+', required=True)
    p.add_argument('--metadata', type=Path, default=ROOT/'mods/color')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    rom = (ROOT/'roms/sd_gundam.vb').read_bytes()
    materials = Materials(args.metadata)
    # Independently identified original frame/fill/inset tiles, not screen boxes.
    panels = {fingerprint(rom[o:o+16]): rom[o:o+16]
              for o in range(0x63d70, 0x63e50, 16)}
    for h, tile in panels.items():
        for category in (0, 3):
            mask = materials.shared[(category, h)]
            for v, row in enumerate(struct.unpack('<8H', tile)):
                for u in range(8):
                    if (row >> (u*2)) & 3:
                        assert mask[v*8+u] == 10, f'Non-blue shared panel {h:08x}'
        assert not any(k[-1] == h for k in materials.exact), 'Position-specific panel override'
        assert not any(k[-1] == h for k in materials.catalog), 'Catalog panel override'
    rows = []
    for directory in args.captures:
        for path in sorted(directory.glob('*.src')):
            data = path.read_bytes()
            assert data[:8] == b'VBSRC001' and len(data) == 24+384*224*16
            panel, other = Counter(), Counter()
            for source in struct.iter_unpack('<IHHHBBBBBB', data[24:]):
                if not source[8] or not source[9]:
                    continue
                ink = materials.ink(source)
                if source[0] in panels:
                    assert ink == 10, f'Panel seam: {path.name}, {source}'
                    panel[f'{source[0]:08x}'] += 1
                else:
                    other[ink] += 1
            if panel:
                rows.append({'capture': f'{directory.name}/{path.name}',
                             'panel_texels': sum(panel.values()), 'panel_hashes': dict(panel),
                             'other_ink_counts': dict(other)})
    assert rows, 'No real panel captures were checked'
    result = {'passed': True, 'panel_tiles': len(panels), 'captures': rows,
              'metadata_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(args.metadata.glob('*.txt'))}}
    args.out.write_text(json.dumps(result, indent=2)+'\n', newline='\n')
    print(json.dumps({'passed': True, 'panel_tiles': len(panels), 'panel_captures': len(rows)}))


if __name__ == '__main__':
    main()
