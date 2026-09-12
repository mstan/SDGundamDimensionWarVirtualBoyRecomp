"""Measure authored source coverage, distinguishing intentional red from misses."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import struct
from PIL import Image
from color_assets import fingerprint

ROOT=Path(__file__).resolve().parents[1]


class Materials:
    def __init__(self,directory):
        self.exact={};self.catalog={};self.shared={}
        for name,target,nibble in [('materials.txt',self.exact,True),('catalog.txt',self.catalog,False),('tiles.txt',self.shared,False)]:
            for line in (directory/name).read_text().splitlines():
                fields=line.split();key=tuple(int(v) for v in fields[:-2])+(int(fields[-2],16),)
                target[key]=[int(c,16) for c in fields[-1]] if nibble else list(bytes.fromhex(fields[-1]))

    def ink(self,s):
        h,x,y,t,u,v,m,k,raw,w=s
        if not raw or not w or k>3:return 0
        category=3 if k==3 else 0
        for table,key in ((self.exact,(m,k,x//8,y//8,h)),(self.catalog,(category,x//8,y//8,h)),(self.shared,(category,h))):
            mask=table.get(key)
            if mask and mask[v*8+u]:return mask[v*8+u]
        return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    mats=Materials(ROOT/'mods/color');report=[];unknown_hashes=Counter()
    for path in sorted(args.captures.glob('*.src')):
        data=path.read_bytes()
        if data[:8]!=b'VBSRC001' or len(data)!=24+384*224*16:raise ValueError(path)
        misses=Counter();inks=Counter();im=Image.new('RGB',(384,224))
        for i,s in enumerate(struct.iter_unpack('<IHHHBBBBBB',data[24:])):
            if not s[8]:continue
            ink=mats.ink(s);inks[ink]+=1
            if not ink:
                misses[(s[7],s[6],s[9])]+=1;unknown_hashes[s[0]]+=1
                im.putpixel((i%384,i//384),(s[8]*85,)*3)
        im.save(args.out/(path.stem+'-unclassified.png'))
        item={'capture':path.name,'visible':sum(inks.values()),'unclassified':inks[0],
              'inks':dict(inks),'groups':[{'kind':k,'map':m,'world':w,'pixels':n} for (k,m,w),n in misses.most_common()]}
        report.append(item)
        print(path.name,round(100*(1-inks[0]/max(1,sum(inks.values()))),2),'%',misses.most_common(3))
    rom=(ROOT/'roms/sd_gundam.vb').read_bytes();matches=defaultdict(list)
    for offset in range(0,len(rom)-15,2):
        h=fingerprint(rom[offset:offset+16])
        if h in unknown_hashes:matches[h].append(offset)
    summary={'captures':report,'unclassified_tiles':[{'hash':f'{h:08x}','pixels':n,'rom_offsets':[f'{v:05x}' for v in matches[h]]}
                                                    for h,n in unknown_hashes.most_common()]}
    (args.out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
