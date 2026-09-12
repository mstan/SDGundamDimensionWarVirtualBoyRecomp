"""Validate opt-in defaults, saved aspect selection, disabling and battery restart."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'framework', 'input-save', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--port', type=int, default=5024)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    profile = out / 'profile'; profile.mkdir()
    save = profile / 'battery.sav'; shutil.copy2(args.input_save, save)
    sys.path.insert(0, str(args.framework.resolve() / 'tools'))
    from cosim import Runner, compare_snapshots
    report = {'passed': False, 'runtime_sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest(), 'phases': []}
    install = []
    for name, version in (('english', '0.1.0'), ('color', '0.2.2'), ('widescreen', '0.1.0')):
        install += ['--install-mod', str(ROOT / f'dist/sd-gundam-{name}-{version}.vbmod')]
    install += ['--enable-mod', 'sd-gundam-english:english', '--enable-mod', 'sd-gundam-color:color']
    native = None; stock_color = None
    try:
        for phase, actions, width in [
            ('default-off', install, 384),
            ('enabled-32', ['--enable-mod', 'sd-gundam-widescreen:widescreen', '--set-mod-option',
                            'sd-gundam-widescreen:widescreen:aspect=32:9'], 796),
            ('persisted-32', [], 796),
            ('disabled', ['--disable-mod', 'sd-gundam-widescreen:widescreen'], 384),
            ('persisted-off', [], 384)]:
            before_save = save.read_bytes()
            with Runner(args.exe, ROOT / 'roms/sd_gundam.vb', 'native', args.port, profile,
                        extra=['--save', str(save), *actions]) as run:
                assert run.memory(0x06000000) == before_save
                for step in json.loads((ROOT / 'tests/save-load-area3-route.json').read_text()):
                    run.client.command('set_input', pad=step.get('pad', 0))
                    run.client.run_frames(step['frames'], timeout=60)
                state = run.client.command('viewport_state')
                assert state['width'] == width and state['active'] == (width > 384), (phase, state)
                frame = run.client.command('frame')['frame']
                snapshot = run.snapshot(frame, 'cpu,wram,sram,vram,vip,devices,video,video_right,audio'.split(','))
                if native is None: native = snapshot
                else: assert not compare_snapshots(native, snapshot), phase
                shot = out / (phase + '.png')
                run.client.command('screenshot', presented=1, path=shot.as_posix())
                if width == 384:
                    if stock_color is None: stock_color = shot.read_bytes()
                    else: assert stock_color == shot.read_bytes(), 'Disabled view changed English/color presentation'
                final_sram = run.memory(0x06000000)
                execution = run.client.command('execution_stats')
                assert not execution['interpreted'] and not execution['fallback'] and not execution['stopped']
            assert save.read_bytes() == final_sram == before_save
            saved = tomllib.loads((profile / 'mods/state.toml').read_text())
            report['phases'].append({'name': phase, 'viewport': state, 'settings': saved,
                                     'save_sha256': hashlib.sha256(final_sram).hexdigest(), 'execution': execution})
            print(phase, width, 'passed', flush=True)
        report['passed'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    print(json.dumps({'passed': report['passed'], 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
