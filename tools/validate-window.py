"""Exercise a private Windows game window, physical key events and pause UI."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
for name in ('exe','rom','framework','route','out'): p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--port',type=int,default=4570)
args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(args.framework.resolve()/'tools'))
from debug_client import DebugClient
from _imgio import load_png

user=ctypes.WinDLL('user32',use_last_error=True)
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
def window_for(pid):
    found=[]
    @callback_type
    def visit(hwnd,_):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        name=ctypes.create_unicode_buffer(128);user.GetClassNameW(hwnd,name,128)
        if owner.value==pid and name.value=='SDL_app': found.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None

def key(hwnd,vk,down):
    scan=user.MapVirtualKeyW(vk,0)
    flags=1|(scan<<16)|((1<<24) if vk in (37,38,39,40) else 0)
    if not down: flags|=(1<<30)|(1<<31)
    if not user.PostMessageW(hwnd,0x100 if down else 0x101,vk,flags): raise ctypes.WinError()

def tap(hwnd,vk):
    key(hwnd,vk,True);time.sleep(.05);key(hwnd,vk,False);time.sleep(.08)

exe=out/args.exe.name;shutil.copy2(args.exe,exe)
assets=args.exe.parent/'assets'
if assets.exists(): shutil.copytree(assets,out/'assets',dirs_exist_ok=True)
(out/'settings.cfg').write_text('scale 2\nsource 1\naudio 0\nfullscreen 0\nfilter 0\n')
environment={k:v for k,v in os.environ.items() if not k.startswith('VBRECOMP_')}
startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
process=subprocess.Popen([str(exe),'--rom',str(args.rom.resolve()),'--no-launcher','--no-save','--paused',
    '--config',str(out/'settings.cfg'),'--mods-dir',str(out/'mods'),'--port',str(args.port)],
    cwd=out,env=environment,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW,
    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
client=None;report={'passed':False,'checks':[],'runtime_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
try:
    deadline=time.monotonic()+15;hwnd=None
    while time.monotonic()<deadline:
        if process.poll() is not None: raise RuntimeError('window process exited during startup')
        hwnd=window_for(process.pid)
        if hwnd: user.SetWindowPos(hwnd,None,-20000,-20000,0,0,0x0015)
        if client is None:
            try: client=DebugClient(args.port)
            except OSError: pass
        if client and hwnd: break
        time.sleep(.03)
    if not client or not hwnd: raise RuntimeError('window or debugger unavailable')
    # Posted messages target only this process's window; no focus or desktop
    # keyboard injection is used. SDL consumes its normal window event path.
    key(hwnd,ord('X'),True);time.sleep(.1)
    assert int(client.command('pad_state')['pad'],0)&4
    key(hwnd,ord('X'),False);time.sleep(.1)
    assert int(client.command('pad_state')['pad'],0)==2
    report['checks'].append('window keyboard press and release reaches controller')
    key(hwnd,9,True)  # existing Tab turbo shortcut
    for segment in json.loads(args.route.read_text()):
        client.command('set_input',pad=segment.get('pad',0))
        client.run_frames(segment['frames'],timeout=60)
    key(hwnd,9,False)
    client.command('screenshot',path=(out/'game.png').as_posix())
    client.command('screenshot',host=1,path=(out/'presented.png').as_posix())
    assert load_png(out/'game.png')==load_png(out/'presented.png')
    report['checks'].append('window presentation matches faithful framebuffer at route checkpoint')
    before=client.command('get_registers')
    tap(hwnd,27)
    client.command('screenshot',host=1,path=(out/'pause-menu.png').as_posix())
    assert load_png(out/'pause-menu.png')!=load_png(out/'game.png')
    client.command('continue');time.sleep(.2)
    after=client.command('get_registers')
    assert {k:v for k,v in before.items() if k!='id'}=={k:v for k,v in after.items() if k!='id'}
    report['checks'].append('Escape opens shared pause UI and holds CPU state')
    client.command('pause');tap(hwnd,27)
    client.command('screenshot',host=1,path=(out/'resumed.png').as_posix())
    assert load_png(out/'resumed.png')==load_png(out/'game.png')
    client.command('clear_input');time.sleep(.1)
    assert int(client.command('pad_state')['pad'],0)==2
    client.run_frames(2)
    report['checks'].append('Escape closes UI, physical input resumes and guest advances')
    report['passed']=True
except Exception as exc:
    report['error']=repr(exc)
finally:
    if client:
        try: client.command('quit')
        except Exception: pass
        client.close()
    try: _,err=process.communicate(timeout=5)
    except subprocess.TimeoutExpired: process.terminate();_,err=process.communicate(timeout=5)
    report['exit']=process.returncode
    if process.returncode: report['passed']=False;report['crash']=err.decode(errors='replace')[-4000:]
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
