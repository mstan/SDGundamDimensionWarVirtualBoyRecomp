"""Package committed production sources, opt-in mods and native dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GAME = 'SDGundamDimensionWarVirtualBoyRecomp'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', type=Path, default=ROOT / 'build-release')
p.add_argument('--framework', type=Path, default=ROOT / 'vbrecomp')
p.add_argument('--ui', type=Path, default=ROOT / 'recomp-ui')
p.add_argument('--toolchain', type=Path, default=Path('C:/msys64/mingw64/bin'))
p.add_argument('--out', type=Path, default=ROOT / 'dist')
p.add_argument('--git', default='C:/Program Files/Git/cmd/git.exe')
args = p.parse_args()
for name in ('build', 'framework', 'ui', 'toolchain', 'out'):
    setattr(args, name, getattr(args, name).resolve())
args.out.mkdir(parents=True, exist_ok=True)
cache = (args.build / 'CMakeCache.txt').read_text(encoding='utf-8')
for flag, value in [('SD_GUNDAM_UI', 'ON'), ('SD_GUNDAM_FAST_BUILD', 'OFF'),
                    ('VBRECOMP_DEBUG_TOOLS', 'OFF'), ('VBRECOMP_CPUHOOK', 'OFF')]:
    if f'{flag}:BOOL={value}' not in cache:
        raise SystemExit(f'Expected production configuration {flag}={value}')
if 'CMAKE_BUILD_TYPE:STRING=Release' not in cache:
    raise SystemExit('Expected Release build')
for key, expected in [('CMAKE_HOME_DIRECTORY', ROOT), ('VBRECOMP_ROOT', args.framework),
                      ('RECOMP_UI_ROOT', args.ui)]:
    match = re.search(rf'^{key}:[^=]+=(.+)$', cache, re.MULTILINE)
    if not match or Path(match[1]).resolve() != expected:
        raise SystemExit(f'Build cache does not match source directory: {key}')


def git(path, *command):
    return subprocess.check_output([args.git, '-C', str(path), *command],
                                   text=True, encoding='utf-8').strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for tree in (ROOT, args.framework, args.ui):
    if git(tree, 'status', '--porcelain'):
        raise SystemExit(f'Commit source changes before packaging: {tree}')
for name, tree in [('vbrecomp', args.framework), ('recomp-ui', args.ui)]:
    commit = git(tree, 'rev-parse', 'HEAD')
    if git(ROOT, 'rev-parse', f'HEAD:{name}') != commit or (ROOT / f'{name}.pin').read_text().strip() != commit:
        raise SystemExit(f'Build dependency does not match committed pin: {name}')

exe = args.build / f'vbrecomp/runtime/{GAME}.exe'
packages = []
for kind in ('english', 'color', 'widescreen'):
    source = ROOT / 'mods' / kind
    manifest = tomllib.loads((source / 'manifest.toml').read_text(encoding='utf-8'))
    if any(feature.get('default_enabled', False) for feature in manifest['feature']):
        raise SystemExit(f'The bundled {kind} mod must be opt-in')
    package = ROOT / 'dist' / f"{manifest['id']}-{manifest['version']}.vbmod"
    expected = {path.name: path for path in source.iterdir() if path.is_file()}
    if kind == 'english':
        expected['source/english.json'] = ROOT / 'translations/english.json'
    with zipfile.ZipFile(package) as z:
        if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected) or any(
            z.read(name) != path.read_bytes() for name, path in expected.items()
        ):
            raise SystemExit(f'Rebuild {kind}: package contents differ from source')
    packages.append((package, {'file': package.name, 'id': manifest['id'],
                              'version': manifest['version'], 'sha256': sha(package),
                              'default_enabled': False}))

info = {'version': (ROOT / 'VERSION').read_text().strip(), 'early_prototype': True,
        'game_commit': git(ROOT, 'rev-parse', 'HEAD'),
        'framework_commit': git(args.framework, 'rev-parse', 'HEAD'),
        'ui_commit': git(args.ui, 'rev-parse', 'HEAD'),
        'configuration': 'Release, full optimization, recomp-ui, hybrid fallback, TCP/CPU trace disabled',
        'executable_sha256': sha(exe), 'optional_mods': [item for _, item in packages]}
with tempfile.TemporaryDirectory(prefix='sd-gundam-release-', dir=args.out) as temp:
    stage = Path(temp).resolve()
    # Verify the absolute cleanup target before TemporaryDirectory removes it.
    if not stage.is_relative_to(args.out) or stage == args.out:
        raise SystemExit('Unexpected packaging staging directory')
    shutil.copy2(exe, stage / exe.name)
    for source in sorted((exe.parent / 'assets').rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(exe.parent / 'assets')
        if source.suffix.lower() not in ('.tga', '.ttf', '.md'):
            # Current recomp-ui includes a PNG flag atlas. Only accept PNGs
            # byte-identical to the clean, pinned shared common asset tree.
            original = args.ui / 'assets/common' / relative
            if source.suffix.lower() != '.png' or not original.is_file() or sha(source) != sha(original):
                raise SystemExit(f'Unexpected runtime asset: {source.name}')
        target = stage / 'assets' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for package, _ in packages:
        shutil.copy2(package, stage / package.name)
    licenses = stage / 'licenses'
    shutil.copytree(ROOT / 'assets/licenses', licenses)
    for source, name in [
        (ROOT / 'LICENSE.md', 'project.txt'),
        (args.framework / 'LICENSE', 'vbrecomp.txt'),
        (args.ui / 'LICENSE', 'recomp-ui.txt'),
        (args.framework / 'runtime/licenses/snes-mod-runtime.txt', 'snes-mod-runtime.txt'),
        (args.ui / 'src/third_party/imgui/LICENSE.txt', 'imgui.txt'),
        (args.ui / 'assets/common/fonts/NOTICE.md', 'recomp-ui-fonts.md'),
        (args.toolchain.parent / 'share/licenses/SDL2/LICENSE.txt', 'SDL2.txt'),
    ]:
        shutil.copy2(source, licenses / name)
    for name in ('gcc-libs', 'libwinpthread'):
        shutil.copytree(args.toolchain.parent / 'share/licenses' / name, licenses / name)
    third_party = args.ui / 'src/third_party'
    stb = (third_party / 'stb_image.h').read_text(encoding='utf-8')
    (licenses / 'stb.txt').write_text(stb[stb.rindex('This software is available under 2 licenses'):]
                                     .removesuffix('*/\n'), encoding='utf-8')
    tinyfd = (third_party / 'tinyfiledialogs.c').read_text(encoding='utf-8')
    (licenses / 'tinyfiledialogs.txt').write_text(tinyfd[2:tinyfd.index('*/')], encoding='utf-8')
    queue, copied = [exe], set()
    while queue:
        binary = queue.pop()
        imports = subprocess.check_output([str(args.toolchain / 'objdump.exe'), '-p', str(binary)], text=True)
        for name in re.findall(r'DLL Name:\s*(\S+)', imports):
            if name.lower() in copied:
                continue
            candidate = next((folder / name for folder in (exe.parent, args.toolchain)
                              if (folder / name).is_file()), None)
            if candidate:
                copied.add(name.lower())
                shutil.copy2(candidate, stage / name)
                queue.append(candidate)
            elif not (Path(os.environ['SystemRoot']) / 'System32' / name).is_file() and not name.lower().startswith(('api-ms-', 'ext-ms-')):
                raise SystemExit(f'Unresolved dependency: {name}')
    info['dlls'] = {path.name: sha(path) for path in stage.glob('*.dll')}
    (stage / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    # Only committed public documentation is eligible for the distribution.
    for name in git(ROOT, 'ls-files', 'README.md', 'LICENSE.md', 'VERSION', 'docs').splitlines():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (stage / 'README.txt').write_text(
        'SD Gundam: Dimension War Recompiled ' + info['version'] + '\n\n'
        'EARLY PROTOTYPE. BUGS ARE EXPECTED.\n\n'
        f'Extract everything. Run {GAME}.exe, select your own original\n'
        'Japanese .vb cartridge, and press Play. No ROM is included.\n'
        'In Mods, install any included .vbmod packages, then enable English\n'
        'story text, Gundam reference colors or Adaptive widescreen. All are\n'
        'OFF by default. Restart after changing language. Widescreen supports\n'
        '16:9, 21:9, 32:9 and Adaptive (fit window).\n'
        'Keyboard: arrows, WASD, X/Z, Q/E, Enter/Right Shift. Escape: settings.\n'
        'Keep vbrecomp.cfg, keybinds.ini, saves/ and mods/ when updating.\n'
        'See docs/RELEASE.md and licenses/ for details and component notices.\n', encoding='utf-8')
    archive = args.out / f'{GAME}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for source in sorted(stage.rglob('*')):
            if source.is_file():
                if source.suffix.lower() in ('.vb', '.vboy', '.cfg', '.ini', '.sav', '.sram',
                                             '.src', '.ips', '.zip', '.gpr', '.pdb', '.dmp', '.pem', '.key'):
                    raise SystemExit(f'Unexpected private/profile data in release: {source.name}')
                entry = zipfile.ZipInfo(source.relative_to(stage).as_posix(), (2026, 9, 12, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(entry, source.read_bytes())
for package, _ in packages:
    target = args.out / package.name
    if package.resolve() != target.resolve():
        shutil.copy2(package, target)
(args.out / 'SHA256SUMS.txt').write_text(''.join(
    f'{sha(path)}  {path.name}\n' for path in [archive, *(args.out / path.name for path, _ in packages)]),
    encoding='utf-8')
print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, **info}, indent=2))
