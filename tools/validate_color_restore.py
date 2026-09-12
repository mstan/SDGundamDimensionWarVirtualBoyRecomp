"""Disable a persisted color selection, preserving English and stock presentation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
for name in ('exe','rom','framework','profile','out'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--port',type=int,default=4900)
args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
shutil.copytree(args.profile/'mods',out/'runner/mods')
sys.path.insert(0,str(args.framework.resolve()/'tools'))
from cosim import Runner
from _imgio import load_png
report={'passed':False,'runtime_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest()}
manifest=out/'runner/mods/packages/sd-gundam-color/0.2.0/manifest.toml'
assert manifest.exists(),'Expected the expanded color package in this profile'
report['color_version']='0.2.0'
report['installed_color_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(manifest.parent.iterdir()) if p.is_file()}
try:
    with Runner(args.exe,args.rom,'native',args.port,out/'runner',extra=['--disable-mod','sd-gundam-color:color']) as r:
        assert hashlib.sha256(r.memory(0x07000000,1048576)).hexdigest()=='a143fb582956ce1f2214c0122a6cdd1f832bc82fb598c4d8a6b21102ccaab906'
        for step in json.loads((ROOT/'tests/save-load-area3-route.json').read_text())[:13]:
            r.client.command('set_input',pad=step.get('pad',0));r.client.run_frames(step['frames'],timeout=60)
        for eye in (0,1):
            raw=out/f'raw-{eye}.png';presented=out/f'presented-{eye}.png'
            r.client.command('screenshot',path=raw.as_posix(),eye=eye)
            r.client.command('screenshot',path=presented.as_posix(),eye=eye,presented=1)
            assert load_png(raw)==load_png(presented)
        report['execution']=r.client.command('execution_stats')
        assert not report['execution']['fallback'] and not report['execution']['stopped']
    report['passed']=True
except Exception as exc:report['error']=repr(exc)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
