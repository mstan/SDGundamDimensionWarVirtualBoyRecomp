"""Compare native language-mod execution with a separately patched Beetle ROM."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

p=argparse.ArgumentParser(description=__doc__)
for name in ('framework','exe','oracle','rom','reference-rom','package','route','out'):
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--restore-from',type=Path,help='Previous enabled runtime directory; copy its private mod profile, then disable')
p.add_argument('--port',type=int,default=4740)
args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(args.framework.resolve()/'tools'))
from cosim import Runner,compare_snapshots

digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
original=digest(args.rom)
planes='cpu,wram,sram,vram,vip,devices,video,video_right,presented,audio'.split(',')
report={'passed':False,'language':'ja' if args.restore_from else 'en','planes':planes,
        'rom_sha256':original,'oracle_rom_sha256':digest(args.reference_rom),
        'runtime_sha256':digest(args.exe),'oracle_sha256':digest(args.oracle),
        'package_sha256':digest(args.package),'checkpoints':0,'byte_audits':0}
schedule=json.loads(args.route.read_text())
extra=['--install-mod',str(args.package.resolve()),'--enable-mod','sd-gundam-english:english']
if args.restore_from:
    shutil.copytree(args.restore_from.resolve()/'mods',out/'a/mods')
    extra=['--disable-mod','sd-gundam-english:english']
try:
    with Runner(args.exe,args.rom,'native',args.port,out/'a',extra=extra) as a, \
         Runner(args.oracle,args.reference_rom,'oracle',args.port+1,out/'b') as b:
        for runner in (a,b):runner.client.socket.settimeout(60)
        report['runtime_memory_rom_sha256']=hashlib.sha256(a.memory(0x07000000,args.rom.stat().st_size)).hexdigest()
        assert report['runtime_memory_rom_sha256']==report['oracle_rom_sha256'],'Live cartridge differs from reference'
        frame=0
        for segment in schedule:
            for runner in (a,b):
                runner.client.command('set_input',pad=segment.get('pad',0))
                runner.client.run_frames(segment['frames'],timeout=60)
            frame+=segment['frames']
            left,right=a.snapshot(frame,planes),b.snapshot(frame,planes)
            diffs=compare_snapshots(left,right)
            report['checkpoints']+=1;report['byte_audits']+=sum(isinstance(v,bytes) for v in left.values())
            if diffs:
                report['first_divergence']={'frame':frame,'differences':diffs}
                break
        report['execution']=a.client.command('execution_stats')
        assert not report['execution']['stopped'] and not report['execution']['fallback']
        report['last_frame']=frame
        report['passed']=report['checkpoints']==len(schedule) and 'first_divergence' not in report
except Exception as exc:
    report['error']=repr(exc);report['passed']=False
report['original_file_unchanged']=digest(args.rom)==original
report['passed'] &= report['original_file_unchanged']
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
