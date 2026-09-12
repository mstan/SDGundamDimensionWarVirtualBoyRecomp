"""Capture reproducible load-menu and camera-pan evidence in a private profile."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('framework', 'exe', 'input-save', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--port', type=int, default=5018)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.framework.resolve() / 'tools'))
    from cosim import Runner
    save = out / 'battery.sav'; shutil.copy2(args.input_save, save)
    extra = ['--save', str(save)]
    for name, version in (('english', '0.1.0'), ('color', '0.2.2'), ('widescreen', '0.1.0')):
        extra += ['--install-mod', str(ROOT / f'dist/sd-gundam-{name}-{version}.vbmod'),
                  '--enable-mod', f'sd-gundam-{name}:{name}']
    extra += ['--set-mod-option', 'sd-gundam-widescreen:widescreen:aspect=32:9']
    report = {'passed': False, 'runtime_sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest(), 'captures': []}
    try:
        with Runner(args.exe, ROOT / 'roms/sd_gundam.vb', 'native', args.port, out / 'runner', extra=extra) as run:
            def capture(name):
                (out / (name + '.vram')).write_bytes(run.memory(0, 0x40000))
                (out / (name + '.wram')).write_bytes(run.memory(0x05000000))
                run.client.command('source_dump', path=(out / (name + '.src')).as_posix())
                for eye in (0, 1):
                    run.client.command('source_dump', presented=1, eye=eye, path=(out / f'{name}-wide-{eye}.src').as_posix())
                    run.client.command('screenshot', presented=1, eye=eye, path=(out / f'{name}-wide-{eye}.png').as_posix())
                    run.client.command('screenshot', eye=eye, path=(out / f'{name}-native-{eye}.png').as_posix())
                report['captures'].append({'name': name, 'viewport': run.client.command('viewport_state')})
            frame = 0
            for step in json.loads((ROOT / 'tests/save-load-area3-route.json').read_text()):
                run.client.command('set_input', pad=step.get('pad', 0))
                run.client.run_frames(step['frames'], timeout=60); frame += step['frames']
                if step.get('label'): capture(str(frame))
            for pad, frames, name in ((8, 10, 'b-down'), (0, 80, 'grid-off'), (2048, 20, 'pan-up'),
                                      (0, 100, 'pan-still'), (4, 10, 'a-down'), (0, 80, 'grid-on')):
                run.client.command('set_input', pad=pad); run.client.run_frames(frames, timeout=60)
                capture(name)
            report['execution'] = run.client.command('execution_stats')
            assert not report['execution']['fallback'] and not report['execution']['interpreted'] and not report['execution']['stopped']
        report['passed'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    print(json.dumps({'passed': report['passed'], 'captures': len(report['captures']), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
