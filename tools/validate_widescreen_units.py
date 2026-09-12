"""Check projected units against native OAM and the displayed wide source plane."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from color_assets import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rom = (ROOT / 'roms/sd_gundam.vb').read_bytes()
    report = {'passed': False, 'rom_sha256': hashlib.sha256(rom).hexdigest(), 'scenes': []}
    try:
        for name in ('3500', 'pan-still', 'grid-on'):
            ram = (args.captures / (name + '.wram')).read_bytes()
            vram = (args.captures / (name + '.vram')).read_bytes()
            count = struct.unpack_from('<H', ram, 0x68d2)[0]
            objects = set(struct.iter_unpack('<hHHH', vram[0x3e000:0x3e000 + count * 8]))
            sources = []
            for eye in (0, 1):
                data = (args.captures / f'{name}-wide-{eye}.src').read_bytes()
                assert data[:8] == b'VBSRC001'
                width, height = struct.unpack_from('<II', data, 8)
                assert height == 224
                sources.append(list(struct.iter_unpack('<IHHHBBBBBB', data[24:])))
            camera_x, camera_y = struct.unpack_from('<bb', ram, 0x420)
            scene = {'name': name, 'camera': [camera_x, camera_y], 'units': []}
            for actor in range(12):
                record = ram[0x42c + actor * 20:0x440 + actor * 20]
                descriptor = struct.unpack_from('<I', record)[0] & 0xfffff
                if not 0xe8000 <= descriptor < 0xf2000: continue
                fields = struct.unpack_from('<22I', rom, descriptor)
                depth = camera_y + 5 - record[14]; column = record[13] - camera_x
                if not 0 <= depth < 6: continue
                unit_name = rom[fields[0] & 0xfffff:descriptor].split(b'\0')[0].decode().strip()
                projection = struct.unpack_from('<11h', rom, 0xdd5c8 + depth * 22)
                original_x = projection[column] if 0 <= column < 11 else 0
                valid = [i for i, x in enumerate(projection) if x]
                pitch = (projection[valid[-1]] - projection[valid[0]]) / (valid[-1] - valid[0])
                center = original_x or round(191 + (column - 5) * pitch)
                scale = 2 - depth // 2
                tw, th = rom[0xdd670 + fields[1] * 6 + scale * 2:0xdd672 + fields[1] * 6 + scale * 2]
                sx = center - tw * 4
                sy = struct.unpack_from('<h', rom, 0xdd64c + (depth * 3 + record[15]) * 2)[0] - th * 8
                parallax = struct.unpack_from('<b', rom, 0xdd5c2 + 5 - depth)[0]
                base = struct.unpack_from('<H', rom, 0xdd586 + actor // 6 * 30 + actor % 6 * 2)[0]
                bank_field = (6, 4, 2)[scale]; bank = fields[bank_field] & 0xfffff
                result = {'name': unit_name, 'depth': depth, 'column': column, 'originally_culled': not original_x, 'eyes': []}
                for eye, field in enumerate(((12, 12), (10, 11), (8, 9))[scale]):
                    cells = struct.unpack_from(f'<{tw * th}H', rom, fields[field] & 0xfffff)
                    if original_x:
                        expected = {(sx + i % tw * 8, (parallax & 0x3fff) | (0x4000 if eye else 0x8000),
                                     (sy + i // tw * 8) & 65535, (cell + base) & 65535) for i, cell in enumerate(cells)}
                        assert expected <= objects, (name, unit_name, eye, 'native OAM differs from projection')
                        result['eyes'].append({'eye': eye, 'native_tiles_equal': len(expected)})
                    else:
                        visible = matched = 0
                        for i, cell in enumerate(cells):
                            tile = rom[bank + (cell & 2047) * 16:bank + (cell & 2047) * 16 + 16]
                            for v, row in enumerate(struct.unpack('<8H', tile)):
                                for u in range(8):
                                    raw = row >> (u * 2) & 3
                                    x = sx + (parallax if eye else -parallax) + i % tw * 8 + (7 - u if cell & 0x2000 else u) + (width - 384) // 2
                                    y = sy + i // tw * 8 + (7 - v if cell & 0x1000 else v)
                                    if not raw or not (0 <= x < width and 0 <= y < 224): continue
                                    visible += 1
                                    sample = sources[eye][y * width + x]
                                    matched += (sample[0], sample[4], sample[5], sample[7], sample[8]) == (fingerprint(tile), u, v, 3, raw)
                        if visible: assert matched == visible, (name, unit_name, eye, matched, visible)
                        result['eyes'].append({'eye': eye, 'candidate_texels': visible, 'visible_source_matches': matched})
                scene['units'].append(result)
            assert any(u['originally_culled'] and all(e['visible_source_matches'] for e in u['eyes']) for u in scene['units'])
            report['scenes'].append(scene)
        report['passed'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    args.out.write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
