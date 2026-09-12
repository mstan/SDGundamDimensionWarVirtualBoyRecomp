"""Explore artwork with ordinary controller input and retain a replayable route.

Each stdin JSON line contains a label and steps [{frames, pad}]. Send {quit:true}
to close the owned runner. All saves, images and source captures are private.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('framework', 'exe', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--route', type=Path, default=ROOT / 'tests/color-authoring-route.json')
    p.add_argument('--input-save', type=Path)
    p.add_argument('--port', type=int, default=4900)
    p.add_argument('--color', action='store_true')
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.framework.resolve() / 'tools'))
    from cosim import Runner
    extra = ['--install-mod', str(ROOT / 'dist/sd-gundam-english-0.1.0.vbmod'),
             '--enable-mod', 'sd-gundam-english:english', '--save', str(out / 'progress.sav')]
    if args.input_save:
        shutil.copy2(args.input_save, out / 'progress.sav')
    if args.color:
        extra += ['--install-mod', str(ROOT / 'dist/sd-gundam-color-0.2.2.vbmod'),
                  '--enable-mod', 'sd-gundam-color:color']
    route = []
    report = []
    with Runner(args.exe, ROOT / 'roms/sd_gundam.vb', 'native', args.port, out / 'runner', extra=extra) as r:
        r.client.socket.settimeout(60)

        def advance(steps):
            for step in steps:
                r.client.command('set_input', pad=step.get('pad', 0))
                r.client.run_frames(step['frames'], timeout=60)
                route.append(step)

        def capture(label):
            frame = r.client.command('frame')['frame']
            stem = f'{len(report):03}-{label}'
            for eye in (0, 1):
                r.client.command('screenshot', presented=1, eye=eye, path=(out / f'{stem}-{eye}.png').as_posix())
                r.client.command('source_dump', eye=eye, path=(out / f'{stem}-{eye}.src').as_posix())
            for name, base in (('wram', 0x05000000), ('sram', 0x06000000), ('vram', 0)):
                (out / f'{stem}.{name}').write_bytes(r.memory(base, 0x40000 if name == 'vram' else 65536))
            execution = r.client.command('execution_stats')
            if execution['stopped'] or execution['fallback'] or execution['interpreted']:
                raise RuntimeError(f'Native execution failed: {execution}')
            report.append({'frame': frame, 'label': label, 'stem': stem, 'execution': execution})
            if route:
                route[-1]['label'] = label
            (out / 'route.json').write_text(json.dumps(route, indent=2) + '\n')
            (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({'frame': frame, 'stem': stem}), flush=True)

        advance(json.loads(args.route.read_text()))
        capture('ready')
        for line in sys.stdin:
            command = json.loads(line)
            if command.get('quit'):
                break
            advance(command.get('steps', []))
            capture(command['label'])


if __name__ == '__main__':
    main()
