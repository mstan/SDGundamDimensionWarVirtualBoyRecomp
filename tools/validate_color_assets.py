"""Audit full cartridge artwork coverage and compare decoded maps to native VRAM."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import struct
from color_assets import catalog,artwork,decode_map,fingerprint
from audit_color_coverage import Materials

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-capture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();rom=(ROOT/'roms/sd_gundam.vb').read_bytes()
    mats=Materials(ROOT/'mods/color');units=catalog(rom)
    raw_hashes=defaultdict(set);report=[]
    for descriptor,name,fields in units:
        item={'name':name,'descriptor':f'{descriptor:x}','artwork':[]}
        for art in artwork(rom,fields):
            for i in range(0,len(art.tiles),16):
                data=art.tiles[i:i+16];raw_hashes[fingerprint(data)].add(data)
            inks=Counter();missing=0
            for x,y,h,u,v,raw,tile in art.texels():
                category=art.category
                # Use the catalog exactly as the native renderer does, outside
                # the already-authored opening scene's more specific masks.
                key=(category,0 if category==3 else x//8,0 if category==3 else y//8,h)
                mask=mats.catalog.get(key) or mats.shared.get((category,h))
                ink=mask[v*8+u] if mask else 0
                if not ink:
                    mask=mats.shared.get((category,h));ink=mask[v*8+u] if mask else 0
                missing+=not ink;inks[ink]+=1
            if missing:raise AssertionError(f'{name}/{art.name}: {missing} unclassified texels')
            if len(inks)<2:raise AssertionError(f'{name}/{art.name}: no material distinctions')
            item['artwork'].append({'name':art.name,'visible_texels':sum(inks.values()),'ink_counts':dict(inks),'missing':missing})
        report.append(item)
    unit_hashes=len(raw_hashes)
    shared_checks=[]
    for bank in json.loads((ROOT/'colors/shared.json').read_text())['banks']:
        visible=0
        for offset in range(int(bank['start'],16),int(bank['end'],16),16):
            data=rom[offset:offset+16];h=fingerprint(data);raw_hashes[h].add(data)
            for v,row in enumerate(struct.unpack('<8H',data)):
                for u in range(8):
                    if not ((row>>(u*2))&3):continue
                    for category in bank['categories']:
                        mask=mats.shared.get((category,h))
                        if not mask or not mask[v*8+u]:
                            raise AssertionError(f'{bank["name"]}: unclassified source {offset:x}/{u}/{v}')
                        visible+=1
        shared_checks.append({'name':bank['name'],'classified_texels_by_category':visible})
    collisions=[f'{h:08x}' for h,data in raw_hashes.items() if len(data)>1]
    if collisions:raise AssertionError(f'FNV collisions in unit art: {collisions}')
    live=args.native_capture.read_bytes();checks=[]
    for name,eye,map_id,base in [('RICK-DIAS',0,4,1024),('RICK-DIAS',1,5,1024),('ZAKU',0,6,1536)]:
        fields=next(f for d,n,f in units if n==name)
        cells,_=decode_map(rom,fields[15+eye]&0xfffff)
        expected=struct.pack('<4096H',*((v+base)&65535 for v in cells))
        actual=live[0x20000+map_id*0x2000:0x22000+map_id*0x2000]
        if expected!=actual:raise AssertionError(f'{name}/{eye}: decoded map differs from native VRAM')
        checks.append({'unit':name,'eye':eye,'native_map':map_id,'bytes_equal':len(actual),'sha256':hashlib.sha256(actual).hexdigest()})
    inputs = ('roms/sd_gundam.vb','tools/author_units.py','tools/color_assets.py',
              'colors/units.json','colors/shared.json','mods/color/palette.txt','mods/color/materials.txt',
              'mods/color/catalog.txt','mods/color/tiles.txt','dist/sd-gundam-color-0.2.0.vbmod')
    hashes = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in inputs}
    result={'passed':True,'input_sha256':hashes,'units':report,'artwork_count':sum(len(u['artwork']) for u in report),
            'unit_tile_hashes':unit_hashes,'total_tile_hashes':len(raw_hashes),'shared_banks':shared_checks,
            'hash_collisions':collisions,'native_map_checks':checks,'native_capture_sha256':hashlib.sha256(live).hexdigest()}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='units'}))


if __name__=='__main__':main()
