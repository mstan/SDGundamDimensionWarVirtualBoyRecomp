"""Package authored color metadata. No ROM art or generated code is included."""
from pathlib import Path
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'dist/sd-gundam-color-0.1.0.vbmod'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.toml','palette.txt','materials.txt'):
            data=(ROOT/'mods/color'/name).read_bytes()
            entry=zipfile.ZipInfo(name,(2026,9,12,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,data)
    print(f'{output}: {hashlib.sha256(output.read_bytes()).hexdigest()}')

if __name__=='__main__':main()
