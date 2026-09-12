"""Compile color annotations against private draw-time source captures.

Destination coordinates and world indices are used only to identify artwork
while authoring. Runtime masks contain atlas coordinates, CHR hashes and inks.
The cartridge's original bitmap pixels are never included in the package.
"""
import argparse
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]

def inside(x,y,polygon):
    hit=False
    for (a,b),(c,d) in zip(polygon,polygon[1:]+polygon[:1]):
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:hit=not hit
    return hit

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',type=Path,default=ROOT/'colors/opening.json')
    parser.add_argument('--out',type=Path,default=ROOT/'mods/color/materials.txt')
    args=parser.parse_args();recipe=json.loads(args.recipe.read_text())
    entries={};conflicts=[];counts={}
    for capture in recipe['captures']:
        data=(ROOT/capture['path']).read_bytes()
        if data[:8]!=b'VBSRC001' or len(data)!=24+384*224*16:raise ValueError('Invalid source capture')
        count=0
        for i,s in enumerate(struct.iter_unpack('<IHHHBBBBBB',data[24:])):
            h,x,y,t,u,v,m,k,raw,w=s
            if not raw or not w or k>3:continue
            for region in capture['regions']:
                if any(s[index]!=region[name] for name,index in (('map',6),('kind',7),('world',9)) if name in region):continue
                px,py=(i%384,i//384) if region.get('space')=='screen' else (x,y)
                if 'box' in region:
                    a,b,c,d=region['box']
                    if not(a<=px<c and b<=py<d):continue
                if 'polygon' in region and not inside(px+.5,py+.5,region['polygon']):continue
                priority=region.get('priority',0);ink=region['ink']
                key=(m,k,x//8,y//8,h)
                row=entries.setdefault(key,{})
                for index in (range(64) if region.get('complete_tile') else (v*8+u,)):
                    old=row.get(index);value=ink
                    if old and old[0]>priority:continue
                    if old and old[0]==priority and old[1]!=ink:
                        if old[1]:conflicts.append({'key':key,'texel':index,'inks':[old[1],ink]})
                        # Identical source art with incompatible roles keeps red.
                        value=0
                    row[index]=(priority,value)
                count+=1
        if not count:raise ValueError(f'Annotation matched no source texels: {capture["path"]}')
        counts[capture['path']]=count
    masks=[]
    for (m,k,x,y,h),row in sorted(entries.items()):
        mask=''.join(f'{row.get(i,(0,0))[1]:x}' for i in range(64))
        if any(c!='0' for c in mask):masks.append(f'{m} {k} {x} {y} {h:08x} {mask}')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text('\n'.join(masks)+'\n',encoding='ascii',newline='\n')
    report={'materials':len(masks),'annotations':counts,'conflicts':conflicts}
    report_path=ROOT/'validation/color-authoring.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(masks)} materials, {len(conflicts)} ambiguous texels retained in original red')

if __name__=='__main__':main()
