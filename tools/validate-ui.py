"""Render the real launcher offscreen, preserving the user's settings."""
import argparse
import json
import os
from pathlib import Path
import subprocess


p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--exe',type=Path,required=True)
p.add_argument('--rom',type=Path)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--visible',action='store_true',help='Inspect screenshots from a visible launcher window')
args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
environment={k:v for k,v in os.environ.items() if not k.startswith('VBRECOMP_')}
if not args.visible: environment['SDL_VIDEO_WINDOW_POS']='-20000,-20000'
script=[]
for view in ['dashboard','settings','controller','mods']:
    script += ['view:'+view,'wait:30','shot:'+(out/(view+'.png')).as_posix()]
environment['LNG_SCRIPT']=';'.join(script+['quit'])
startup=None
if os.name=='nt' and not args.visible:
    startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
rom_args=['--rom',str(args.rom.resolve())] if args.rom else []
result=subprocess.run([str(args.exe.resolve()),*rom_args,'--launcher','--no-save',
    '--config',str(out/'settings.cfg'),'--mods-dir',str(out/'mods')],cwd=out,env=environment,
    capture_output=True,timeout=30,startupinfo=startup,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
report={'passed':result.returncode==0,'exit':result.returncode,'screenshots':[]}
for view in ['dashboard','settings','controller','mods']:
    shot=out/(view+'.png')
    if not shot.exists() or shot.stat().st_size<1000: report['passed']=False
    else: report['screenshots'].append(str(shot))
if not report['passed']: report['error']=result.stderr.decode(errors='replace')[-4000:]
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
