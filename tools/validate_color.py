"""Compare independent color-off/on processes through a declared game input route."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import sys
from PIL import Image

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('framework','exe','rom','route','english','color','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--port',type=int,default=4870)
    p.add_argument('--input-save',type=Path)
    p.add_argument('--language',choices=('en','ja'),default='en')
    args=p.parse_args()
    for name in ('framework','exe','rom','route','english','color','out'):setattr(args,name,getattr(args,name).resolve())
    args.out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(args.framework/'tools'))
    from cosim import Runner,compare_snapshots
    extra=['--install-mod',str(args.english),'--enable-mod' if args.language=='en' else '--disable-mod','sd-gundam-english:english',
           '--install-mod',str(args.color)]
    saves=[]
    if args.input_save:
        for side in ('off','on'):
            target=args.out/side/'progress.sav';target.parent.mkdir()
            shutil.copy2(args.input_save,target);saves.append(target)
    report={'passed':False,'language':args.language,'runtime_sha256':sha(args.exe),'rom_sha256':sha(args.rom),
            'color_sha256':sha(args.color),'english_sha256':sha(args.english),'checkpoints':[],'byte_audits':0}
    planes='cpu,wram,sram,vram,vip,devices,video,video_right,audio'.split(',')
    try:
        with Runner(args.exe,args.rom,'native',args.port,args.out/'off',extra=extra+['--disable-mod','sd-gundam-color:color']+(['--save',str(saves[0])] if saves else [])) as a, \
             Runner(args.exe,args.rom,'native',args.port+1,args.out/'on',extra=extra+['--enable-mod','sd-gundam-color:color']+(['--save',str(saves[1])] if saves else [])) as b:
            for r in (a,b):r.client.socket.settimeout(60)
            if saves:
                for r in (a,b):assert r.memory(0x06000000)==args.input_save.read_bytes()
            frame=0
            for step in json.loads(args.route.read_text()):
                for r in (a,b):
                    r.client.command('set_input',pad=step.get('pad',0))
                    r.client.run_frames(step['frames'],timeout=60)
                frame+=step['frames']
                if not step.get('label') and frame not in (300,400,800,1600,1800,2000,2600,3800,4000,4500):continue
                left,right=a.snapshot(frame,planes),b.snapshot(frame,planes)
                differences=compare_snapshots(left,right)
                report['byte_audits']+=sum(isinstance(v,bytes) for v in left.values())
                if differences:raise AssertionError(f'Guest/raw output divergence at {frame}: {differences}')
                changed=[]
                for eye,raw_name in ((0,'video'),(1,'video_right')):
                    images=[]
                    for r in (a,b):
                        path=r.directory/f'frame-{frame}-color-{eye}.png'
                        r.client.command('screenshot',path=path.as_posix(),eye=eye,presented=1)
                        im=Image.open(path).convert('RGB')
                        assert im.size==(384,224)
                        images.append(list(im.get_flattened_data()))
                    raw=Image.open(a.directory/f'frame-{frame}-{raw_name}.png').convert('RGB')
                    assert list(raw.get_flattened_data())==images[0],'Disabled renderer did not restore stock output'
                    count=0
                    for stock,color in zip(*images):
                        assert max(stock)==max(color),f'Brightness/visible mask changed at {frame}, eye {eye}'
                        count+=stock!=color
                    if frame==4500:
                        # Semantic coverage gate: every identified opening ally
                        # must actually receive color in EACH eye's artwork.
                        for name,box in (('GP01',(44,35,82,54)),('Gundam',(174,74,210,114)),('Rick Dias',(267,112,303,158))):
                            x,y,xx,yy=box
                            touched=sum(images[0][py*384+px]!=images[1][py*384+px]
                                        for py in range(y,yy) for px in range(x,xx))
                            assert touched>=20,f'{name} color missing in eye {eye}'
                    changed.append(count)
                report['checkpoints'].append({'frame':frame,'label':step.get('label',''),'recolored_pixels':changed})
                print(frame,step.get('label',''),changed,flush=True)
            report['execution']=[r.client.command('execution_stats') for r in (a,b)]
            assert all(not e['fallback'] and not e['interpreted'] and not e['stopped'] for e in report['execution'])
            assert sum(sum(c['recolored_pixels']) for c in report['checkpoints'])>0
            assert sha(args.rom)==report['rom_sha256']
        if saves:
            assert all(path.read_bytes()==left['sram'] for path in saves)
            report['persisted_sram_sha256']=sha(saves[0])
        report['passed']=True
    except Exception as exc:report['error']=repr(exc)
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
    print(json.dumps({'passed':report['passed'],'checkpoints':len(report['checkpoints']),'error':report.get('error')}))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
