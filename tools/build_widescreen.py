"""Package the opt-in viewport selection; implementation is linked into the game."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'dist/sd-gundam-widescreen-0.1.0.vbmod'
    output.parent.mkdir(exist_ok=True)
    entry = zipfile.ZipInfo('manifest.toml', (2026, 9, 12, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr(entry, (ROOT / 'mods/widescreen/manifest.toml').read_bytes())
    print(f'{output}: {hashlib.sha256(output.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
