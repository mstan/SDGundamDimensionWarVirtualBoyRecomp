"""Audit local cartridge and IPS inputs without changing either file."""
import hashlib
import argparse
import json
from pathlib import Path
import zipfile
import zlib

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--write-reference-rom', action='store_true',
                    help='Write an ignored, patched oracle input under reference/')
args = parser.parse_args()
rom = (root / 'roms/sd_gundam.vb').read_bytes()
if hashlib.sha256(rom).hexdigest() != '98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92':
    raise ValueError('Expected original Japanese cartridge')
archive = root / 'reference/sdgundampatch.zip'
with zipfile.ZipFile(archive) as z:
    patch = z.read('sdgundampatch.ips')
if hashlib.sha256(patch).hexdigest() != '4e3da3a54d520d9d14d5c98b4feeb5d39eca81587ee79b2c0ca48cfe61d45e67':
    raise ValueError('Unexpected reference patch revision')
assert patch[:5] == b'PATCH'
pos = 5
records = []
target = bytearray(rom)
while patch[pos:pos + 3] != b'EOF':
    if pos + 5 > len(patch):
        raise ValueError('Truncated IPS record')
    offset = int.from_bytes(patch[pos:pos + 3], 'big')
    size = int.from_bytes(patch[pos + 3:pos + 5], 'big')
    pos += 5
    if size:
        data = patch[pos:pos + size]
        if len(data) != size:
            raise ValueError('Truncated IPS data')
        pos += size
    else:
        if pos + 3 > len(patch):
            raise ValueError('Truncated IPS RLE')
        data = patch[pos + 2:pos + 3] * int.from_bytes(patch[pos:pos + 2], 'big')
        pos += 3
    if offset + len(data) > len(rom):
        raise ValueError('Patch exceeds original cartridge')
    records.append({'offset': f'0x{offset:06x}', 'size': len(data),
                    'changed_bytes': sum(a != b for a, b in zip(target[offset:offset + len(data)], data))})
    target[offset:offset + len(data)] = data
if pos + 3 != len(patch):
    raise ValueError('Unexpected IPS trailer')
report = {'rom_size': len(rom), 'rom_sha256': hashlib.sha256(rom).hexdigest(),
          'rom_crc32': f'{zlib.crc32(rom):08x}',
          'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
          'ips_sha256': hashlib.sha256(patch).hexdigest(), 'ips_size': len(patch),
          'patched_sha256': hashlib.sha256(target).hexdigest(),
          'changed_bytes': sum(a != b for a, b in zip(rom, target)),
          'records': records}
out = root / 'reference/input-audit.json'
out.write_text(json.dumps(report, indent=2) + '\n')
if args.write_reference_rom:
    (root / 'reference/sd_gundam_english.vb').write_bytes(target)
print(json.dumps(report, indent=2))
