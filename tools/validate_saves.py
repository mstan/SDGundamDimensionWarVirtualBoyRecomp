"""Validate game-created battery saves across processes, languages and the window host."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
PLANES='cpu,wram,sram,vram,vip,devices,video,video_right,presented,audio'.split(',')
SLOT_SIZE=0x5d0
COPY_SIZE=0x1f0

def sha(data):return hashlib.sha256(data).hexdigest()
def slot(data,index):return data[index*SLOT_SIZE:(index+1)*SLOT_SIZE]
def occupied(data,index):
    expected=b'VB-GUNDAMSAVEDATA'+f'{index:02}'.encode('ascii')
    return all(slot(data,index)[base+2:base+2+len(expected)*2:2]==expected
               for base in (0,COPY_SIZE,2*COPY_SIZE))
def position(data,index):
    block=slot(data,index)
    return [(block[base+0x52],block[base+0x54]) for base in (0,COPY_SIZE,2*COPY_SIZE)]
def tap(pad,wait=100,hold=20,label=None):
    steps=[{'frames':hold,'pad':pad},{'frames':wait,'pad':0}]
    if label:steps[-1]['label']=label
    return steps

def compare_route(args,name,language,route,input_save=None):
    from cosim import Runner,compare_snapshots
    directory=args.out/name;directory.mkdir()
    save=directory/'progress.sav'
    if input_save:shutil.copy2(input_save,save)
    initial=save.read_bytes() if input_save else bytes(65536)
    extra=['--save',str(save)]
    if language=='en':extra+=['--install-mod',str(args.package),'--enable-mod','sd-gundam-english:english']
    oracle_rom=args.reference_rom if language=='en' else args.rom
    report={'passed':False,'language':language,'checkpoints':[],
            'initial_sram_sha256':sha(initial),'byte_audits':0}
    prior_area1=None
    try:
        with Runner(args.exe,args.rom,'native',args.port,directory/'a',extra=extra) as a, \
             Runner(args.oracle,oracle_rom,'oracle',args.port+1,directory/'b') as b:
            for runner in (a,b):runner.client.socket.settimeout(60)
            assert a.memory(0x06000000)==initial,'Native host did not load the exact battery file'
            # The oracle frontend has no save-file option. Import only the
            # common battery-file input at frame zero, before any instruction.
            # CPU, work RAM, devices and video all remain at independent reset.
            assert b.memory(0x06000000)==bytes(65536)
            for offset,value in enumerate(initial):
                if value:b.client.command('write_ram',addr=0x06000000+offset,val=value)
            assert b.memory(0x06000000)==initial,'Oracle battery input import failed'
            frame=0
            for segment in route:
                for runner in (a,b):
                    runner.client.command('set_input',pad=segment.get('pad',0))
                    runner.client.run_frames(segment['frames'],timeout=60)
                frame+=segment['frames']
                label=segment.get('label')
                if not label:continue
                left,right=a.snapshot(frame,PLANES),b.snapshot(frame,PLANES)
                differences=compare_snapshots(left,right)
                report['byte_audits']+=sum(isinstance(v,bytes) for v in left.values())
                data=left['sram']
                record={'frame':frame,'label':label,'sram_sha256':sha(data),
                        'occupied':[occupied(data,i) for i in range(3)]}
                report['checkpoints'].append(record)
                (directory/(label+'.sram')).write_bytes(data)
                print(name,frame,label,record['occupied'],flush=True)
                if differences:
                    report['first_divergence']={'frame':frame,'differences':differences}
                    raise AssertionError('Independent oracle divergence')
                if label=='area1-saved':
                    assert occupied(data,0) and not occupied(data,1)
                    prior_area1=slot(data,0)
                if label=='area2-saved':
                    assert occupied(data,0) and occupied(data,1) and not occupied(data,2)
                    assert slot(data,0)==prior_area1,'Area2 overwrote Area1'
                    assert position(data,0)==[(8,11)]*3
                    assert position(data,1)==[(9,11)]*3,'Moved Gundam not represented in the save'
                if label=='area3-saved':
                    assert all(occupied(data,i) for i in range(3))
                    assert data[:2*SLOT_SIZE]==initial[:2*SLOT_SIZE],'Area3 overwrote an existing slot'
                    assert position(data,2)==position(initial,1),'Loaded unit position changed on resave'
            report['execution']=a.client.command('execution_stats')
            assert not report['execution']['stopped'] and not report['execution']['fallback']
            report['final_sram_sha256']=sha(data)
        assert save.stat().st_size==65536 and save.read_bytes()==data,'Clean exit did not publish exact SRAM'
        assert not save.with_suffix('.sav.tmp').exists(),'Temporary save was not published'
        report['save_file_sha256']=sha(save.read_bytes())
        report['passed']=True
    except Exception as exc:
        report['error']=repr(exc)
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
    if not report['passed']:raise RuntimeError(f'{name}: {report.get("error")}')
    return save,report

def window_default(args,input_save):
    from debug_client import DebugClient
    directory=args.out/'window-default';directory.mkdir()
    save=directory/'saves/sd-gundam-dimension-war.sav';save.parent.mkdir()
    shutil.copy2(input_save,save);expected=save.read_bytes();before=save.stat().st_mtime_ns
    config=directory/'settings.cfg';config.write_text('scale 2\nsource 1\naudio 0\nfullscreen 0\nfilter 0\n')
    env={k:v for k,v in os.environ.items() if not k.startswith('VBRECOMP_')}
    env['SDL_VIDEO_WINDOW_POS']='-20000,-20000'
    startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);probe.bind(('127.0.0.1',args.port+2))
    process=subprocess.Popen([str(args.exe),'--rom',str(args.rom),'--no-launcher','--paused','--execution','native',
        '--config',str(config),'--mods-dir',str(directory/'mods'),'--port',str(args.port+2)],
        cwd=directory,env=env,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    client=None;hwnd=None
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback_type
    def find_window(handle,_):
        nonlocal hwnd
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        name=ctypes.create_unicode_buffer(128);user.GetClassNameW(handle,name,128)
        if pid.value==process.pid and name.value=='SDL_app':hwnd=handle
        return True
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Window host exited at startup')
            user.EnumWindows(find_window,0)
            if not client:
                try:client=DebugClient(args.port+2,timeout=60)
                except OSError:pass
            if client and hwnd:break
            time.sleep(.05)
        assert client and hwnd,'Real SDL window did not start'
        raw=bytes.fromhex(client.command('read_ram',addr=0x06000000,len=65536)['hex'])
        assert raw==expected,'Default windowed save path did not load'
        assert user.PostMessageW(hwnd,0x10,0,0),'WM_CLOSE failed'
        stdout,stderr=process.communicate(timeout=15)
        assert process.returncode==0,stderr.decode(errors='replace')
        assert save.read_bytes()==expected and save.stat().st_mtime_ns>before
        assert not save.with_suffix('.sav.tmp').exists()
        return {'passed':True,'default_path':'<config directory>/saves/sd-gundam-dimension-war.sav',
                'save_sha256':sha(expected),'window_close_exit':process.returncode}
    finally:
        if client:client.close()
        if process.poll() is None:process.terminate();process.communicate(timeout=5)

def failure_checks(args,input_save):
    from cosim import Runner
    directory=args.out/'failure-checks';directory.mkdir()
    bad=directory/'truncated.sav';bad.write_bytes(b'invalid-size')
    try:
        with Runner(args.exe,args.rom,'native',args.port+3,directory/'truncated',extra=['--save',str(bad)]):
            raise AssertionError('Truncated save accepted')
    except RuntimeError:
        crash=json.loads((directory/'truncated/crash.json').read_text())
        assert crash['exit']==6
    assert bad.read_bytes()==b'invalid-size'
    good=directory/'protected.sav';shutil.copy2(input_save,good);expected=good.read_bytes()
    # A directory at the private temporary-file path forces publication failure.
    good.with_suffix('.sav.tmp').mkdir()
    try:
        with Runner(args.exe,args.rom,'native',args.port+3,directory/'write-failure',extra=['--save',str(good)]):pass
        raise AssertionError('Save failure was silently accepted')
    except RuntimeError:
        crash=json.loads((directory/'write-failure/crash.json').read_text())
        assert crash['exit']==6
    assert good.read_bytes()==expected,'Failed save replaced existing progress'
    return {'passed':True,'truncated_rejected_without_overwrite':True,'write_failure_preserved_prior_save':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('framework','exe','oracle','rom','reference-rom','package','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--port',type=int,default=4830)
    args=p.parse_args()
    for name in ('framework','exe','oracle','rom','reference_rom','package','out'):setattr(args,name,getattr(args,name).resolve())
    args.out.mkdir(parents=True,exist_ok=False);sys.path.insert(0,str(args.framework/'tools'))
    report={'passed':False,'runtime_sha256':sha(args.exe.read_bytes()),'oracle_sha256':sha(args.oracle.read_bytes()),
            'rom_sha256':sha(args.rom.read_bytes()),'package_sha256':sha(args.package.read_bytes()),'checks':{}}
    try:
        save,report['checks']['english_create']=compare_route(args,'english-create','en',json.loads((ROOT/'tests/save-create-route.json').read_text()))
        route=json.loads((ROOT/'tests/save-load-area2-route.json').read_text())
        route+=tap(8)+tap(8192)+tap(1024)+tap(4,600)+tap(8,80,8)
        route+=tap(256,80,8)+tap(256,80,8)+tap(4,160,8)+tap(4,600,8,'area3-saved')
        save,report['checks']['japanese_reload_and_save']=compare_route(args,'japanese-reload-save','ja',route,save)
        save,report['checks']['english_reload']=compare_route(args,'english-reload','en',json.loads((ROOT/'tests/save-load-area3-route.json').read_text()),save)
        report['checks']['window_default']=window_default(args,save)
        report['checks']['failures']=failure_checks(args,save)
        assert sha(args.rom.read_bytes())==report['rom_sha256']
        report['passed']=True
    except Exception as exc:report['error']=repr(exc)
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
