"""Render private roster contact sheets using the compiled runtime masks.

These diagnostic images contain cartridge artwork; keep them in validation/.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from color_assets import artwork, catalog
from audit_color_coverage import Materials

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rom = (ROOT / 'roms/sd_gundam.vb').read_bytes()
    mats = Materials(ROOT / 'mods/color')
    palette = {int(i): tuple(bytes.fromhex(rgb)) for i, rgb in
               (line.split() for line in (ROOT / 'mods/color/palette.txt').read_text().splitlines())}
    sheets = [Image.new('RGB', (960, 8 * 176), '#191d28') for _ in (0, 1)]
    for index, (_, name, fields) in enumerate(catalog(rom)):
        for eye in (0, 1):
            dx, dy = index % 6 * 160, index // 6 * 176
            sheet = sheets[eye]
            ImageDraw.Draw(sheet).text((dx + 4, dy + 4), name, fill='white')
            for art in artwork(rom, fields):
                if art.name not in (f'tactical-2-{eye}', f'battle-{eye}'):
                    continue
                im = Image.new('RGB', (art.width * 8, art.height * 8))
                for x, y, h, u, v, raw, _ in art.texels():
                    # Map 254 bypasses opening scene overrides: this catalog
                    # checks the compiled masks shared by subsequent scenes.
                    sx, sy = (u, v) if art.category == 3 else (x, y)
                    ink = mats.ink((h, sx, sy, 0, u, v, 254, art.category, raw, 1))
                    rgb = palette[ink] if ink else (255, 0, 0)
                    peak = max(rgb)
                    im.putpixel((x, y), tuple(c * raw * 85 // peak for c in rgb))
                if art.name.startswith('battle'):
                    im = im.crop((0, 0, 128, 64))
                    sheet.paste(im, (dx + 4, dy + 108))
                else:
                    im.thumbnail((150, 84), Image.Resampling.NEAREST)
                    sheet.paste(im, (dx + 4, dy + 20))
    for eye, sheet in enumerate(sheets):
        sheet.save(args.out / f'roster-{eye}.png')


if __name__ == '__main__':
    main()
