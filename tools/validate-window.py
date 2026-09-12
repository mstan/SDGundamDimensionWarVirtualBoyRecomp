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
p.add_argument('--english-package',type=Path)
p.add_argument('--color-package',type=Path)
p.add_argument('--widescreen-package',type=Path)
p.add_argument('--stereo',action='store_true')
p.add_argument('--input-save',type=Path,help='Private source save copied into this test profile')
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
user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
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
extra=['--stereo'] if args.stereo else []
for package,feature in ((args.english_package,'sd-gundam-english:english'),(args.color_package,'sd-gundam-color:color'),
                        (args.widescreen_package,'sd-gundam-widescreen:widescreen')):
    if package:extra+=['--install-mod',str(package.resolve()),'--enable-mod',feature]
if args.input_save:
    save=out/'saves/sd-gundam-dimension-war.sav';save.parent.mkdir(exist_ok=True)
    shutil.copy2(args.input_save,save)
else:extra+=['--no-save']
process=subprocess.Popen([str(exe),'--rom',str(args.rom.resolve()),'--no-launcher',*extra,'--paused',
    '--config',str(out/'settings.cfg'),'--mods-dir',str(out/'mods'),'--port',str(args.port)],
    cwd=out,env=environment,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW,
    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
client=None;report={'passed':False,'checks':[],'runtime_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
if args.color_package:report['color_sha256']=hashlib.sha256(args.color_package.read_bytes()).hexdigest()
if args.english_package:report['english_sha256']=hashlib.sha256(args.english_package.read_bytes()).hexdigest()
if args.widescreen_package:report['widescreen_sha256']=hashlib.sha256(args.widescreen_package.read_bytes()).hexdigest()
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
    if args.input_save:
        initial=bytes.fromhex(client.command('read_ram',addr=0x06000000,len=65536)['hex'])
        assert initial==args.input_save.read_bytes()
        report['checks'].append('default save path loads exact battery file with selected mods')
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
    from PIL import Image
    def expected_capture(path):
        client.command('screenshot',presented=1,path=path.as_posix())
        if args.stereo:
            right=path.with_name(path.stem+'-right.png')
            client.command('screenshot',presented=1,eye=1,path=right.as_posix())
            left_image=Image.open(path).convert('RGB');right_image=Image.open(right).convert('RGB')
            combined=Image.new('RGB',(left_image.width,448))
            combined.paste(left_image,(0,0));combined.paste(right_image,(0,224));combined.save(path)
    if args.widescreen_package:
        report['resizes']=[]
        for name,width,height in [('16x9',960,540),('21x9',1260,540),('32x9',1600,450),
                                  ('arbitrary',1234,567),('narrow',600,800)]:
            if args.stereo:height*=2
            outer=wintypes.RECT();inner=wintypes.RECT()
            assert user.GetWindowRect(hwnd,ctypes.byref(outer)) and user.GetClientRect(hwnd,ctypes.byref(inner))
            assert user.SetWindowPos(hwnd,None,-20000,-20000,width+outer.right-outer.left-inner.right,
                                     height+outer.bottom-outer.top-inner.bottom,0x14)
            time.sleep(.25)
            assert user.GetClientRect(hwnd,ctypes.byref(inner))
            assert (inner.right,inner.bottom)==(width,height)
            state=client.command('viewport_state')
            expected_width=max(384,min(2048,int(width/(height//(2 if args.stereo else 1))*112+.5)*2))
            assert state['active'] and state['width']==expected_width,(name,state,expected_width)
            expected=out/(name+'-expected.png');actual=out/(name+'-host.png')
            expected_capture(expected);client.command('screenshot',host=1,path=actual.as_posix())
            assert load_png(actual)==load_png(expected),(name,'SDL presentation differs')
            report['resizes'].append({'name':name,'client_size':[width,height],'viewport_width':state['width']})
        # Leave the pause UI test on a wide image, exercising its dynamic texture.
        assert user.GetWindowRect(hwnd,ctypes.byref(outer)) and user.GetClientRect(hwnd,ctypes.byref(inner))
        assert user.SetWindowPos(hwnd,None,-20000,-20000,1260+outer.right-outer.left-inner.right,
                                 540*(2 if args.stereo else 1)+outer.bottom-outer.top-inner.bottom,0x14)
        time.sleep(.25)
        report['checks'].append('live adaptive resize: 16:9, 21:9, 32:9, arbitrary and narrow windows match both renderer eyes')
    client.command('screenshot',path=(out/'game.png').as_posix())
    client.command('screenshot',host=1,path=(out/'presented.png').as_posix())
    expected_capture(out/'expected-presented.png')
    assert load_png(out/'expected-presented.png')==load_png(out/'presented.png')
    if args.color_package:assert load_png(out/'game.png')!=load_png(out/'presented.png')
    elif not args.widescreen_package and not args.stereo:assert load_png(out/'game.png')==load_png(out/'presented.png')
    report['checks'].append('real window matches renderer output at route checkpoint')
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
    assert load_png(out/'resumed.png')==load_png(out/'expected-presented.png')
    client.command('clear_input');time.sleep(.1)
    assert int(client.command('pad_state')['pad'],0)==2
    client.run_frames(2)
    report['checks'].append('Escape closes UI, physical input resumes and guest advances')
    final_sram=bytes.fromhex(client.command('read_ram',addr=0x06000000,len=65536)['hex'])
    report['execution']=client.command('execution_stats')
    assert not report['execution']['fallback'] and not report['execution']['stopped']
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
if report['passed'] and args.input_save:
    report['save_sha256']=hashlib.sha256(save.read_bytes()).hexdigest()
    if save.read_bytes()!=final_sram:report['passed']=False;report['error']='Disk SRAM differs from clean-exit live SRAM'
    else:report['checks'].append('English and color enabled: clean exit publishes exact battery SRAM')
(out/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
