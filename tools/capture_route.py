"""Capture exact route checkpoints through the framework's owned TCP runner."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

p = argparse.ArgumentParser(description=__doc__)
for name in ('framework', 'exe', 'rom', 'route', 'out'):
    p.add_argument('--' + name, type=Path, required=True)
p.add_argument('--mode', choices=('hybrid', 'native', 'interpreter', 'oracle'), default='hybrid')
p.add_argument('--port', type=int, default=4694)
args = p.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(args.framework.resolve() / 'tools'))
from cosim import Runner

report = {'mode': args.mode, 'passed': False, 'checkpoints': [],
          'rom_sha256': hashlib.sha256(args.rom.read_bytes()).hexdigest(),
          'exe_sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest()}
try:
    with Runner(args.exe, args.rom, args.mode, args.port, out / 'runner') as runner:
        # Allow slow screenshot I/O while keeping a bounded request deadline.
        runner.client.socket.settimeout(60)
        frame = 0
        for segment in json.loads(args.route.read_text()):
            runner.client.command('set_input', pad=segment.get('pad', 0))
            frame = runner.client.run_frames(segment['frames'], timeout=60)
            shot = out / f'{frame:06d}.png'
            runner.client.command('screenshot', eye=0, path=shot.as_posix())
            checkpoint = {'frame': frame, 'pad': segment.get('pad', 0),
                          'label': segment.get('label', ''), 'image': shot.name,
                          'cpu': runner.client.command('get_registers')}
            if args.mode != 'oracle':
                checkpoint['execution'] = runner.client.command('execution_stats')
                if checkpoint['execution']['stopped']:
                    raise RuntimeError(f'Execution stopped at frame {frame}')
            report['checkpoints'].append(checkpoint)
        report['passed'] = True
except Exception as exc:
    report['passed'] = False
    report['error'] = repr(exc)
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': report['passed'], 'checkpoints': len(report['checkpoints']),
                  'error': report.get('error'), 'out': str(out)}, indent=2))
raise SystemExit(0 if report['passed'] else 1)
