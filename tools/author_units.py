"""Compile reference-guided masks for every cartridge unit's artwork.

The output contains color IDs and tile fingerprints, never original graphics.
Optional galleries contain private cartridge images and belong in validation/.
"""
import argparse
from collections import defaultdict, Counter
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw
from color_assets import catalog, artwork, fingerprint

ROOT = Path(__file__).resolve().parents[1]


def ink_at(unit, art, x, y, bounds):
    inks = unit['inks']
    if unit['form'] == 'ship':
        a, b, c, d = bounds
        px, py = (x-a)/max(1,c-a), (y-b)/max(1,d-b)
        ink = inks['body']
        if .38 < px < .63 and .12 < py < .67:
            ink = inks['torso']
        if py > .76 and (px < .32 or px > .68):
            ink = inks['trim']
        if .42 < px < .58 and .10 < py < .19:
            ink = inks['sensor']
        return ink
    battle = art.name.startswith('battle')
    if battle:
        stride = 64 if unit['form'] == 'armor' else 56
        row, column = y // stride, x // 120
        px, py = x % 120, y % stride
        if column % 2:
            px = 127-px
        a,b,c,d = unit['battle_body']
        # Weapon extension and beam arcs are authored in pose-sheet space.
        if px > c+8 and b+10 < py < d:
            if (row >= 6 and column < 2) or (column >= 2 and row in (3,4,5) and unit['name']=='G-EPYON'):
                return inks['beam']
            if row < 3:
                return inks['weapon']
        px, py = (px-a)/(c-a), (py-b)/(d-b)
        facing = row % 3
    else:
        a,b,c,d = bounds
        px, py = (x-a)/max(1,c-a), (y-b)/max(1,d-b)
        facing = 0
    ink = inks['body']
    if unit['form'] == 'armor':
        if .45 < py < .65:
            ink = inks['torso']
        if py > .78:
            ink = inks['trim']
        if .42 < px < .61 and .18 < py < .24:
            ink = inks['sensor']
        return ink
    if .24 < px < .78 and .36 < py < .62:
        ink = inks['torso']
    if .34 < px < .69 and .63 < py < .74:
        ink = inks['trim']
    if py > .87:
        ink = inks['trim']
    if facing != 2:
        if .28 < px < .76 and .25 < py < .30:
            ink = inks['sensor']
        if .34 < px < .71 and .44 < py < .48:
            ink = inks['accent']
        if .48 < px < .59 and .04 < py < .12:
            ink = inks['accent']
    if not battle and unit['name'] in ('GUNDAM','G  M') and px < .23 and .33 < py < .75:
        ink = inks['trim']
    return ink


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, default=ROOT/'roms/sd_gundam.vb')
    p.add_argument('--recipe', type=Path, default=ROOT/'colors/units.json')
    p.add_argument('--out', type=Path, default=ROOT/'mods/color')
    p.add_argument('--gallery', type=Path, default=ROOT/'validation/unit-colors')
    args = p.parse_args()
    rom = args.rom.read_bytes()
    recipe = json.loads(args.recipe.read_text(encoding='utf-8'))
    authored = {int(u['descriptor'],16):u for u in recipe['units']}
    exact, shared = defaultdict(dict), defaultdict(dict)
    conflicts = Counter()
    report = []
    args.gallery.mkdir(parents=True,exist_ok=True)
    palette = {int(i):tuple(bytes.fromhex(rgb)) for i,rgb in
               (line.split() for line in (ROOT/'mods/color/palette.txt').read_text().splitlines())}

    def assign(table,key,texel,ink):
        old = table[key].get(texel)
        if old is not None and old != ink:
            conflicts['exact' if table is exact else 'shared'] += 1
            ink = 5
        table[key][texel] = ink

    all_units = catalog(rom)
    if set(authored) != {d for d,n,f in all_units}:
        raise ValueError('Recipe must explicitly cover every cartridge descriptor')
    for index,(descriptor,name,fields) in enumerate(all_units):
        unit = authored[descriptor]
        if unit['name'] != name:
            raise ValueError(f'Name mismatch for {descriptor:x}')
        item = {'name':name,'descriptor':f'{descriptor:x}','artwork':[]}
        for art in artwork(rom,fields):
            texels = list(art.texels())
            bounds = (min(t[0] for t in texels),min(t[1] for t in texels),
                      max(t[0] for t in texels)+1,max(t[1] for t in texels)+1)
            im = Image.new('RGB',(art.width*8,art.height*8))
            inks = Counter()
            for x,y,h,u,v,raw,tile in texels:
                ink = ink_at(unit,art,x,y,bounds)
                key = (art.category,0 if art.category==3 else x//8,0 if art.category==3 else y//8,h)
                assign(exact,key,v*8+u,ink)
                assign(shared,(art.category,h),v*8+u,ink)
                rgb = palette[ink];peak = max(rgb)
                im.putpixel((x,y),tuple(c*raw*85//peak for c in rgb))
                inks[ink] += 1
            im.save(args.gallery/f'{index:02}-{art.name}.png')
            item['artwork'].append({'name':art.name,'map_offset':f'{art.source:x}','chr_offset':f'{art.bank:x}',
                                    'visible_texels':len(texels),'inks':dict(inks)})
        report.append(item)
        print(f'{index+1}/47 {name}',flush=True)
    shared_recipe=json.loads((ROOT/'colors/shared.json').read_text())
    bank_report=[]
    for bank in shared_recipe['banks']:
        start,end=int(bank['start'],16),int(bank['end'],16)
        if start%16 or end%16 or end<=start:raise ValueError(bank['name'])
        for offset in range(start,end,16):
            data=rom[offset:offset+16];h=fingerprint(data)
            rows=struct.unpack('<8H',data);tile=(offset-start)//16
            for v,row in enumerate(rows):
                for u in range(8):
                    raw=(row>>(u*2))&3
                    if not raw:continue
                    ink=bank.get('ink',bank.get('levels',{}).get(str(raw)))
                    for override in bank.get('overrides',[]):
                        if override['first_tile']<=tile<=override['last_tile']:ink=override['ink']
                    if ink not in palette:raise ValueError((bank['name'],ink))
                    for category in bank['categories']:
                        assign(shared,(category,h),v*8+u,ink)
        bank_report.append({'name':bank['name'],'tiles':(end-start)//16})
    args.out.mkdir(parents=True,exist_ok=True)
    for name,table in (('catalog.txt',exact),('tiles.txt',shared)):
        lines=[]
        for key,mask in sorted(table.items()):
            if not mask:
                continue
            prefix=' '.join(str(v) for v in key[:-1])+f' {key[-1]:08x}'
            lines.append(prefix+' '+''.join(f'{mask.get(i,0):02x}' for i in range(64)))
        (args.out/name).write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    result={'units':report,'shared_banks':bank_report,'exact_masks':len(exact),'shared_masks':len(shared),
            'ambiguous_assignments':dict(conflicts),'shared_conflict_ink':5}
    (args.gallery/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='units'}))


if __name__=='__main__':main()
