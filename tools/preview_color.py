"""Open a prepared color preview using a new, isolated save/profile directory."""
import argparse
import ctypes
from ctypes import wintypes
import json
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exe','rom','framework','profile'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--input-save',type=Path)
    p.add_argument('--route',type=Path,help='Optional native controller route for the preview scene')
    p.add_argument('--widescreen',choices=('16:9','21:9','32:9','adaptive'))
    p.add_argument('--port',type=int,default=4890)
    p.add_argument('--title',default='SD Gundam Color Preview - separate save profile')
    args=p.parse_args()
    profile=args.profile.resolve();profile.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(args.framework.resolve()/'tools'))
    from debug_client import DebugClient
    if args.input_save:
        save=profile/'saves/sd-gundam-dimension-war.sav';save.parent.mkdir()
        shutil.copy2(args.input_save,save)
    config=profile/'vbrecomp.cfg'
    config.write_text('scale 3\nsource 1\naudio 1\nfullscreen 0\nfilter 0\n')
    env={k:v for k,v in os.environ.items() if not k.startswith('VBRECOMP_')}
    env['SDL_VIDEO_WINDOW_POS']='-20000,-20000'
    command=[str(args.exe.resolve()),'--rom',str(args.rom.resolve()),'--no-launcher','--paused','--execution','native',
             '--config',str(config),'--mods-dir',str(profile/'mods'),'--port',str(args.port)]
    for name,feature,version in (('english','english','0.1.0'),('color','color','0.2.2')):
        command+=['--install-mod',str(ROOT/f'dist/sd-gundam-{name}-{version}.vbmod'),'--enable-mod',f'sd-gundam-{name}:{feature}']
    if args.widescreen:
        command+=['--install-mod',str(ROOT/'dist/sd-gundam-widescreen-0.1.0.vbmod'),
                  '--enable-mod','sd-gundam-widescreen:widescreen','--set-mod-option',
                  'sd-gundam-widescreen:widescreen:aspect='+args.widescreen]
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);probe.bind(('127.0.0.1',args.port))
    with (profile/'host.log').open('wb') as log:
        process=subprocess.Popen(command,cwd=profile,env=env,creationflags=subprocess.CREATE_NO_WINDOW,stdout=log,stderr=log)
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user.SetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPCWSTR]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    hwnd=None;client=None
    @callback
    def find(handle,_):
        nonlocal hwnd
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        name=ctypes.create_unicode_buffer(128);user.GetClassNameW(handle,name,128)
        if pid.value==process.pid and name.value=='SDL_app':hwnd=handle
        return True
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Preview exited at startup; see host.log')
            user.EnumWindows(find,0)
            if not client:
                try:client=DebugClient(args.port,timeout=60)
                except OSError:pass
            if client and hwnd:break
            time.sleep(.05)
        assert client and hwnd
        route=args.route or ROOT/'tests'/('save-load-area3-route.json' if args.input_save else 'first-mission-route.json')
        for step in json.loads(route.read_text()):
            client.command('set_input',pad=step.get('pad',0));client.run_frames(step['frames'],timeout=60)
        if args.widescreen:
            ratio={'16:9':16/9,'21:9':21/9,'32:9':32/9,'adaptive':21/9}[args.widescreen]
            assert user.SetWindowPos(hwnd,None,-20000,-20000,round(560*ratio)+16,599,0x14)
            time.sleep(.2)
        client.command('screenshot',presented=1,path=(profile/'preview.png').as_posix())
        client.command('screenshot',presented=1,eye=1,path=(profile/'preview-right.png').as_posix())
        execution=client.command('execution_stats')
        assert not execution['fallback'] and not execution['stopped']
        user.SetWindowTextW(hwnd,args.title)
        assert user.SetWindowPos(hwnd,None,160,100,0,0,0x45)
        client.command('clear_input');client.command('continue')
        report={'pid':process.pid,'profile':str(profile),'execution':execution,'preview':str(profile/'preview.png'),
                'runtime_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),
                'color_sha256':hashlib.sha256((ROOT/'dist/sd-gundam-color-0.2.2.vbmod').read_bytes()).hexdigest()}
        if args.widescreen:report['viewport']=client.command('viewport_state')
        (profile/'preview.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    except Exception:
        if client:
            try:client.command('quit')
            except Exception:pass
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        raise
    finally:
        if client:client.close()
    # The visible game is intentionally left running for the owner.

if __name__=='__main__':main()
