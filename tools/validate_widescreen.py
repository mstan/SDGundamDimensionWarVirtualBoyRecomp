"""Compare opt-in viewport presentation against the committed native baseline."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import shutil
import sys
from PIL import Image
from audit_color_coverage import Materials

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('framework', 'exe', 'baseline', 'route', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--aspect', choices=('16:9', '21:9', '32:9', 'adaptive'), default='adaptive')
    p.add_argument('--language', choices=('en', 'ja'), default='en')
    p.add_argument('--no-color', action='store_true')
    p.add_argument('--input-save',type=Path)
    p.add_argument('--port', type=int, default=5010)
    args = p.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.framework.resolve() / 'tools'))
    from cosim import Runner, compare_snapshots
    english = ROOT / 'dist/sd-gundam-english-0.1.0.vbmod'
    color = ROOT / 'dist/sd-gundam-color-0.2.2.vbmod'
    wide = ROOT / 'dist/sd-gundam-widescreen-0.1.0.vbmod'
    rom = ROOT / 'roms/sd_gundam.vb'
    shared = ['--install-mod', str(english), '--enable-mod' if args.language == 'en' else '--disable-mod',
              'sd-gundam-english:english', '--install-mod', str(color),
              '--disable-mod' if args.no_color else '--enable-mod', 'sd-gundam-color:color']
    report = {'passed': False, 'aspect': args.aspect, 'language': args.language, 'color': not args.no_color,
              'runtime_sha256': sha(args.exe), 'baseline_sha256': sha(args.baseline), 'rom_sha256': sha(rom),
              'color_sha256': sha(color), 'widescreen_sha256': sha(wide), 'route_sha256': sha(args.route),
              'checkpoints': []}
    materials = Materials(ROOT / 'mods/color')
    palette = {int(i): tuple(bytes.fromhex(rgb)) for i, rgb in
               (line.split() for line in (ROOT / 'mods/color/palette.txt').read_text().splitlines())}
    planes = 'cpu,wram,sram,vram,vip,devices,video,video_right,audio'.split(',')
    save_args = [[], []]
    if args.input_save:
        for i, name in enumerate(('baseline', 'wide')):
            path = out / name / 'battery.sav'; path.parent.mkdir(exist_ok=True)
            shutil.copy2(args.input_save, path); save_args[i] = ['--save', str(path)]
    try:
        with Runner(args.baseline, rom, 'native', args.port, out / 'baseline', extra=shared+save_args[0]) as base, \
             Runner(args.exe, rom, 'native', args.port + 1, out / 'wide', extra=shared + save_args[1] + [
                 '--install-mod', str(wide), '--enable-mod', 'sd-gundam-widescreen:widescreen',
                 '--set-mod-option', 'sd-gundam-widescreen:widescreen:aspect=' + args.aspect]) as view:
            for r in (base, view):
                r.client.socket.settimeout(60)
            if args.aspect == 'adaptive':
                view.client.command('viewport_state', window_width=2100, window_height=900)
            frame = 0
            for step in json.loads(args.route.read_text()):
                for r in (base, view):
                    r.client.command('set_input', pad=step.get('pad', 0))
                    r.client.run_frames(step['frames'], timeout=60)
                frame += step['frames']
                if not step.get('label') and frame not in (1600, 2600, 4500):
                    continue
                a, b = base.snapshot(frame, planes), view.snapshot(frame, planes)
                differences = compare_snapshots(a, b)
                assert not differences, (frame, differences)
                state = view.client.command('viewport_state')
                extent = state['width']; margin = (extent - 384) // 2
                expected_width = {'16:9': 398, '21:9': 522, '32:9': 796, 'adaptive': 522}[args.aspect]
                assert state['active'] and extent in (384, expected_width), state
                captures = []
                for eye, raw_name in ((0, 'video'), (1, 'video_right')):
                    prefix = out / f'{frame}-{eye}'
                    native = Image.open(view.directory / f'frame-{frame}-{raw_name}.png').convert('RGB')
                    replay = prefix.with_name(prefix.name + '-replay.png')
                    view.client.command('screenshot', viewport_raw=1, width=384, eye=eye, path=replay.as_posix())
                    reproduced = Image.open(replay).convert('RGB')
                    if list(native.get_flattened_data()) != list(reproduced.get_flattened_data()):
                        bad = sum(a != b for a, b in zip(native.get_flattened_data(), reproduced.get_flattened_data()))
                        raise AssertionError(f'Native VIP replay differs at frame {frame}, eye {eye}: {bad} pixels')
                    raw_path = prefix.with_name(prefix.name + '-wide-raw.png')
                    rgb_path = prefix.with_name(prefix.name + '-wide-color.png')
                    src_path = prefix.with_suffix('.src')
                    view.client.command('screenshot', viewport_raw=1, eye=eye, path=raw_path.as_posix())
                    view.client.command('screenshot', presented=1, eye=eye, path=rgb_path.as_posix())
                    view.client.command('source_dump', presented=1, eye=eye, path=src_path.as_posix())
                    raw = Image.open(raw_path).convert('RGB'); rgb = Image.open(rgb_path).convert('RGB')
                    assert raw.size == rgb.size == (extent, 224)
                    data = src_path.read_bytes()
                    assert data[:8] == b'VBSRC001' and struct.unpack_from('<II', data, 8) == (extent, 224)
                    assert len(data) == 24 + extent * 224 * 16
                    sources = struct.iter_unpack('<IHHHBBBBBB', data[24:])
                    coverage = Counter(); edge_pixels = 0; seen = set()
                    for i, (raw_rgb, colored, source) in enumerate(zip(raw.get_flattened_data(), rgb.get_flattened_data(), sources)):
                        assert max(raw_rgb) == max(colored), (frame, eye, i, 'brightness changed')
                        if not max(raw_rgb):
                            continue
                        ink = materials.ink(source); coverage[ink] += 1
                        if not args.no_color:
                            assert ink, (frame, eye, i, 'missing source color', source)
                            c = palette[ink]
                            assert colored == tuple(v * max(raw_rgb) // max(c) for v in c)
                        else:
                            assert colored == raw_rgb
                        edge_pixels += i % extent < margin or i % extent >= margin + 384
                        seen.add(source[0])
                    captures.append({'eye': eye, 'visible': sum(coverage.values()), 'unclassified': coverage[0],
                                     'side_pixels': edge_pixels, 'source_hashes': len(seen)})
                report['checkpoints'].append({'frame': frame, 'label': step.get('label', ''),
                                              'width': extent, 'eyes': captures})
                print(frame, extent, [c['side_pixels'] for c in captures], flush=True)
            report['execution'] = [r.client.command('execution_stats') for r in (base, view)]
            assert all(not e['fallback'] and not e['interpreted'] and not e['stopped'] for e in report['execution'])
            assert any(c['width'] > 384 and all(e['side_pixels'] for e in c['eyes']) for c in report['checkpoints'])
            assert sha(rom) == report['rom_sha256']
        report['passed'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    print(json.dumps({'passed': report['passed'], 'checkpoints': len(report['checkpoints']), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
