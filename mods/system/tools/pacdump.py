#!/usr/bin/env python3
"""Research tool: reads the ROM's .pac archives and renders their NCGR tile sheets into PNG files (needs Pillow).

  pacdump.py <rom.nds> data/ani/obj_bt3.gp2 data/ani/obj_ii.pac ...       -> mods/system/tools/pac-out/*.png (git-ignored)

A .pac is a run of named entries: 0x40 bytes of name, then u32 data offset (0x50), u32 size and u32 distance to the next entry; the data is a plain
NDS file (NCGR tiles, NCLR palette, NCER cells, NANR animation). A .gp2 is a GPC2 archive holding one .pac per language.

What it found (docs/NOTES.md 2026-11-14 (46)): the 2D art in the ROM is UI parts (labels, number glyphs, HP panels, map icons); there are no face, item
or monster pictures as tiles. Monsters are 3D models (data/pack_lv5/enemy.gp2) and a party member's face is composed from the character's look."""
import os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pac-out")


def pac_entries(b):
    out, p = [], 0
    while p + 0x50 <= len(b):
        name = b[p:p + 0x40].split(b"\0")[0]
        if not name or not re.fullmatch(rb"[\x20-\x7e]+", name):
            break
        off, size, nxt = struct.unpack_from("<3I", b, p + 0x40)
        if p + off + size > len(b):
            break
        out.append((name.decode(), b[p + off:p + off + size]))
        if nxt == 0:
            break
        p += nxt
    return out


def palette(nclr):
    """-> [(r, g, b)] of an NCLR (the TTLP block: size, depth, 0, data size, data offset)"""
    i = nclr.find(b"TTLP")
    size, _depth, _, _dsz, off = struct.unpack_from("<5I", nclr, i + 4)
    data = nclr[i + 8 + off:i + size]
    cols = []
    for k in range(len(data) // 2):
        v = struct.unpack_from("<H", data, k * 2)[0]
        cols.append(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31))
    return cols


def render(ncgr, cols, width_tiles=16, bank=0):
    """an NCGR (RGCN / RAHC: tile counts, depth 3 = 4 bit, 4 = 8 bit, tile data) as an RGBA image, `width_tiles` tiles wide"""
    from PIL import Image
    i = ncgr.find(b"RAHC")
    depth, = struct.unpack_from("<I", ncgr, i + 0x0C)
    dsz, = struct.unpack_from("<I", ncgr, i + 0x18)
    data = ncgr[i + 0x20:i + 0x20 + dsz]
    bpp = 4 if depth == 3 else 8
    n = len(data) // (bpp * 8)
    h = (n + width_tiles - 1) // width_tiles
    im = Image.new("RGBA", (width_tiles * 8, h * 8), (0, 0, 0, 0))
    base = bank * 16 if bpp == 4 else 0
    for t in range(n):
        ox, oy = (t % width_tiles) * 8, (t // width_tiles) * 8
        for y in range(8):
            for x in range(8):
                if bpp == 4:
                    byte = data[t * 32 + y * 4 + x // 2]
                    v = byte >> 4 if x & 1 else byte & 15
                else:
                    v = data[t * 64 + y * 8 + x]
                if v:
                    im.putpixel((ox + x, oy + y), (cols[base + v] if base + v < len(cols) else (255, 0, 255)) + (255,))
    return im


def main():
    import rom_text
    nds = rom_text.Nds(sys.argv[1])
    os.makedirs(OUT, exist_ok=True)
    for path in sys.argv[2:]:
        b = nds.read(path)
        members = []
        if b[:4] == b"GPC2":
            arc = rom_text.gpc2(b)
            members = [(k, v) for k, v in arc.items() if "_en." in k][:1] or list(arc.items())[:1]
        else:
            members = [(os.path.basename(path), b)]
        for mname, mb in members:
            ents = pac_entries(mb)
            print(path, mname, [(n, len(d)) for n, d in ents][:10])
            pal = next((d for n, d in ents if n.lower().endswith(".nclr")), None)
            for n, d in ents:
                if n.lower().endswith(".ncgr") and pal:
                    im = render(d, palette(pal))
                    fn = os.path.join(OUT, os.path.basename(path).replace(".", "_") + "_" + n + ".png")
                    im.resize((im.width * 2, im.height * 2)).save(fn)
                    print("  ", fn, im.size)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    main()
