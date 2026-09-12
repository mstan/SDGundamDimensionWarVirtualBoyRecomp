"""Read SD Gundam artwork tables for offline color authoring only.

No bitmap data is shipped. The runtime consumes source fingerprints and inks.
The map decoder follows cartridge function FFF05B64; layout dimensions follow
FFF0D174/FFF0D296/FFF0D3BE and the six-byte records at ROM offset DD670.
"""
from dataclasses import dataclass
import hashlib
import struct

ROM_SHA256 = '98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92'


def fingerprint(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def decode_map(rom, offset):
    """Decode literal/repeat/increasing/decreasing tile-map runs."""
    start = offset
    cells = []
    while True:
        command = struct.unpack_from('<H', rom, offset)[0]
        offset += 2
        if command == 0:
            break
        operation, count = command >> 12, (command & 4095) + 1
        value = struct.unpack_from('<H', rom, offset)[0]
        offset += 2
        if operation == 1:
            offset -= 2
            cells.extend(struct.unpack_from(f'<{count}H', rom, offset))
            offset += count * 2
        elif operation == 2:
            cells.extend([value] * count)
        elif operation in (3, 4):
            delta = 1 if operation == 3 else -1
            cells.extend((value + i * delta) & 65535 for i in range(count))
        else:
            raise ValueError(f'Unsupported map command {command:04x} at {offset-4:x}')
        if len(cells) > 4096:
            raise ValueError(f'Oversized map at {start:x}')
    if len(cells) != 4096:
        raise ValueError(f'Incomplete map at {start:x}: {len(cells)} cells')
    return cells, offset


@dataclass
class Artwork:
    name: str
    width: int
    height: int
    cells: list
    tiles: bytes
    source: int
    bank: int
    category: int

    def texels(self):
        for index, cell in enumerate(self.cells):
            tile = cell & 2047
            data = self.tiles[tile * 16:tile * 16 + 16]
            if len(data) != 16:
                raise ValueError(f'{self.name}: tile {tile} exceeds bank')
            tile_hash = fingerprint(data)
            for v, row in enumerate(struct.unpack('<8H', data)):
                for u in range(8):
                    raw = (row >> (u * 2)) & 3
                    if not raw:
                        continue
                    x = index % self.width * 8 + (7-u if cell & 0x2000 else u)
                    y = index // self.width * 8 + (7-v if cell & 0x1000 else v)
                    yield x, y, tile_hash, u, v, raw, tile


def catalog(rom):
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Authoring requires the unchanged Japanese cartridge')
    units = []
    for offset in range(0xe8000, 0xf2000, 4):
        fields = struct.unpack_from('<22I', rom, offset)
        if not (0xfff6f000 <= fields[2] < 0xfff86000 and 10 < fields[3] < 150
                and fields[1] < 6 and offset-24 <= (fields[0] & 0xfffff) < offset):
            continue
        name = rom[fields[0] & 0xfffff:offset].split(b'\0')[0].decode('ascii').strip()
        units.append((offset, name, fields))
    if len(units) != 47:
        raise ValueError(f'Expected 47 unit descriptors, found {len(units)}')
    return units


def artwork(rom, fields):
    result = []
    for scale, entries in enumerate(((6, (12,)), (4, (10, 11)), (2, (8, 9)))):
        bank_field, maps = entries
        width, height = rom[0xdd670 + fields[1]*6 + scale*2:0xdd672 + fields[1]*6 + scale*2]
        bank = fields[bank_field] & 0xfffff
        tiles = rom[bank:bank+fields[bank_field+1]*16]
        for eye, field in enumerate(maps):
            source = fields[field] & 0xfffff
            cells = list(struct.unpack_from(f'<{width*height}H', rom, source))
            result.append(Artwork(f'tactical-{scale}-{eye}', width, height, cells, tiles, source, bank, 3))
    bank = fields[13] & 0xfffff
    tiles = rom[bank:bank+fields[14]*16]
    for eye in (0, 1):
        source = fields[15+eye] & 0xfffff
        if fields[1] < 4:
            cells, _ = decode_map(rom, source)
            width = height = 64
        else:
            width, height = 16, 8
            cells = list(struct.unpack_from('<128H', rom, source))
        result.append(Artwork(f'battle-{eye}', width, height, cells, tiles, source, bank, 0))
    return result
