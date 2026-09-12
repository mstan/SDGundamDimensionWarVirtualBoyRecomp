"""Capture native draw-time source attribution; private owner assets stay ignored."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

p=argparse.ArgumentParser(description=__doc__)
for name in ('framework','exe','rom','route','out'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--port',type=int,default=4770)
p.add_argument('--english-package',type=Path)
args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(args.framework.resolve()/'tools'))
from cosim import Runner
extra=[]
if args.english_package:extra=['--install-mod',str(args.english_package.resolve()),'--enable-mod','sd-gundam-english:english']
report={'runtime_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'checkpoints':[]}
with Runner(args.exe,args.rom,'native',args.port,out/'runner',extra=extra) as r:
    r.client.socket.settimeout(60);frame=0
    for s in json.loads(args.route.read_text()):
        r.client.command('set_input',pad=s.get('pad',0));frame=r.client.run_frames(s['frames'],timeout=60)
        if not s.get('label') and frame not in (300,400,800,1600,1800,2000,2600,3800,4000,4500):continue
        stats=[]
        for eye in (0,1):
            stem=out/f'{frame:04}-{eye}'
            r.client.command('screenshot',path=stem.with_suffix('.png').as_posix(),eye=eye)
            r.client.command('source_dump',path=stem.with_suffix('.src').as_posix(),eye=eye)
            data=stem.with_suffix('.src').read_bytes()
            assert data[:8]==b'VBSRC001' and len(data)==24+384*224*16
            counts=Counter((row[7],row[6],row[9]) for row in struct.iter_unpack('<IHHHBBBBBB',data[24:]) if row[8])
            stats.append([{'kind':k,'map':m,'world':w,'pixels':n} for (k,m,w),n in counts.most_common()])
        report['checkpoints'].append({'frame':frame,'sources':stats})
        print(f'Captured native sources at {frame}',flush=True)
    report['execution']=r.client.command('execution_stats')
(out/'sources.json').write_text(json.dumps(report,indent=2)+'\n')
