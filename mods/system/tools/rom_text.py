#!/usr/bin/env python3
"""Reads the game's own texts out of your ROM: the five languages (en de fr es it) of the item names and
the other name tables, so the Cheats window and the save editor can use the game's exact words.

  rom_text.py <rom.nds> [--out DIR]     writes DIR\\rom-<table>-<lang>.tsv  (default: mods\\system\\lang)
  rom_text.py <rom.nds> --find WORD     which tables/languages contain WORD (for translating by the game's terms)

Formats (NitroFS, GPC2 archive, DS compression, name tables) are the ones documented by the DQIX project's wiki
(github.com/DQIX/wiki); this is an own implementation. The ROM is only read."""
import os, re, struct, sys, unicodedata

LANGS = ("en", "de", "fr", "es", "it")


# ------------------------------------------------------------------ NitroFS
class Nds:
    def __init__(self, path):
        self.rom = open(path, "rb").read()
        r = self.rom
        fnt, _, fat, fat_sz = struct.unpack_from("<4I", r, 0x40)
        self.fnt, self.fat = fnt, [struct.unpack_from("<2I", r, fat + i * 8) for i in range(fat_sz // 8)]
        self.files = {}
        self._dir(0xF000, "")

    def _dir(self, did, path):
        r = self.rom
        sub, fid, _ = struct.unpack_from("<IHH", r, self.fnt + (did & 0xFFF) * 8)
        p = self.fnt + sub
        while True:
            b = r[p]; p += 1
            if b == 0:
                return
            n = b & 0x7F
            name = r[p:p + n].decode("latin1"); p += n
            if b & 0x80:
                cid = struct.unpack_from("<H", r, p)[0]; p += 2
                self._dir(cid, path + name + "/")
            else:
                self.files[path + name] = fid; fid += 1

    def read(self, name):
        a, b = self.fat[self.files[name]]
        return self.rom[a:b]


# ------------------------------------------------------------------ DS compression (payload without BIOS header)
def lz10(d, p, size):
    out = bytearray()
    while len(out) < size:
        flags = d[p]; p += 1
        for i in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> i):
                b0, b1 = d[p], d[p + 1]; p += 2
                n, disp = (b0 >> 4) + 3, ((b0 & 15) << 8 | b1) + 1
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(d[p]); p += 1
    return bytes(out[:size])


def rle(d, p, size):
    out = bytearray()
    while len(out) < size:
        f = d[p]; p += 1
        if f & 0x80:
            out += bytes([d[p]]) * ((f & 0x7F) + 3); p += 1
        else:
            n = (f & 0x7F) + 1; out += d[p:p + n]; p += n
    return bytes(out[:size])


def huff(d, p, size, bits):
    tree = p + 1
    stream = p + (d[p] + 1) * 2
    out = bytearray(); word = 0; nbits = 0
    node = tree  # root
    nib_lo = None
    sp = stream
    while len(out) < size:
        if nbits == 0:
            word = struct.unpack_from("<I", d, sp)[0]; sp += 4; nbits = 32
        bit = (word >> (nbits - 1)) & 1; nbits -= 1
        nd = d[node]
        child = (node & ~1) + (nd & 0x3F) * 2 + 2 + bit
        is_data = (nd >> (7 - bit)) & 1
        if is_data:
            v = d[child]
            if bits == 8:
                out.append(v)
            elif nib_lo is None:
                nib_lo = v
            else:
                out.append(nib_lo | v << 4); nib_lo = None
            node = tree
        else:
            node = child
    return bytes(out[:size])


def region(d, p):
    """a region: u32 (codec | size << 3), then the payload"""
    pre = struct.unpack_from("<I", d, p)[0]
    codec, size = pre & 7, pre >> 3
    p += 4
    if codec == 0:
        return d[p:p + size]
    if codec == 1:
        return lz10(d, p, size)
    if codec == 2:
        return huff(d, p, size, 4)
    if codec == 3:
        return huff(d, p, size, 8)
    if codec == 4:
        return rle(d, p, size)
    raise ValueError("codec %d" % codec)


def bios(d, p, size):
    """the entry table when compressed: tried as each codec, the first sane one wins (the header doesn't say)"""
    for fn in (lambda: lz10(d, p, size), lambda: huff(d, p, size, 4), lambda: huff(d, p, size, 8), lambda: rle(d, p, size)):
        try:
            t = fn()
            hashes = [struct.unpack_from("<I", t, i * 12)[0] for i in range(size // 12)]
            if all(a < b for a, b in zip(hashes, hashes[1:])):
                return t
        except Exception:
            pass
    raise ValueError("entry table")


# ------------------------------------------------------------------ GPC2
def gpc2(d):
    """-> {member name: bytes}"""
    assert d[:4] == b"GPC2", "not a GPC2 archive"
    count = d[4] | (d[5] & 0x0F) << 8
    name_off, data_off, _ = struct.unpack_from("<3H", d, 8)
    name_off *= 4; data_off *= 4
    etab = None
    if name_off - 0x18 == 12 * count:
        etab = d[0x18:0x18 + 12 * count]
    else:
        # compressed entry table: try with and without a 4-byte BIOS-style header
        for skip in (0, 4):
            try:
                etab = bios(d, 0x18 + skip, 12 * count); break
            except Exception:
                pass
    out = {}
    nbytes = region(d, name_off)
    for i in range(count):
        crc, w1, w2 = struct.unpack_from("<3I", etab, i * 12)
        off = (w1 & 0xFFFFFF) * 4
        noff = ((w2 >> 24) << 8) | (w1 >> 24)
        end = nbytes.index(b"\0", noff)
        nm = nbytes[noff:end].decode("latin1")
        out[nm] = region(d, data_off + off)
    return out


# ------------------------------------------------------------------ name tables
def item_names(nat):
    """itemname_<lang>.nat -> {item id: (singular, plural)}"""
    count = struct.unpack_from("<I", nat, 0)[0] & 0xFFF
    base = 4 + 16 * count
    res = {}
    for i in range(count):
        o1, o2, _, iid = struct.unpack_from("<4I", nat, 4 + i * 16)
        def s(o):
            e = nat.find(b"\0", base + o)
            if e < 0:
                e = len(nat)
            return nat[base + o:e].decode("latin1")
        res[iid & 0xFFFF] = (s(o1), s(o2))
    return res


_MARK = {"'": "́", "`": "̀", "^": "̂", ":": "̈", "~": "̃", ",": "̧"}
_FIXED = {"1": "’", "6": "“", "9": "”", "66": "“", "99": "”", "oe": "œ", "OE": "Œ", "ss": "ß", ",": ","}


def _tag(m):
    t = m.group(1)
    if t in _FIXED:
        return _FIXED[t]
    if len(t) == 2 and t[0] in _MARK and t[1].isalpha():
        return unicodedata.normalize("NFC", t[1] + _MARK[t[0]])
    return ""


def clean(t):
    """the game's markup to plain Unicode text: <'e> -> e-acute, <1> -> apostrophe; German grammar tags [ges] etc. dropped"""
    t = re.sub(r"<([^>]*)>", _tag, t)
    return re.sub(r"\[[a-z-]+\]", "", t)


def nat_table(b):
    """a string table: head word (count in the low 12 bits), then (number, offset) records, then the strings -> {number: text}"""
    count = struct.unpack_from("<I", b, 0)[0] & 0xFFF
    base = 4 + 8 * count
    out = {}
    for i in range(count):
        num, off = struct.unpack_from("<II", b, 4 + 8 * i)
        if base + off >= len(b):
            continue
        e = b.find(b"\0", base + off)
        out[num] = clean(b[base + off:e if e >= 0 else None].decode("latin1"))
    return out


def map_names(b):
    """a tagged data table (header: records, string table offset, size, count; record: u16 tag, u8 count, 2-bit types, padded
    to a word, then 4-byte values) -> {map id: name} from the tag 0x67 records of (id, string offset)"""
    stab = struct.unpack_from("<I", b, 4)[0]
    p, out = 16, {}
    while p < stab:
        if b[p:p + 4] == b"\xff\xff\xff\xff":
            p += 4
            continue
        tag, cnt = struct.unpack_from("<HB", b, p)
        tb = (cnt * 2 + 7) // 8
        hdr = ((3 + tb + 3) // 4) * 4
        vals = struct.unpack_from("<%dI" % cnt, b, p + hdr)
        if tag == 0x67 and cnt == 2:
            e = b.find(b"\0", stab + vals[1])
            out[vals[0]] = clean(b[stab + vals[1]:e if e >= 0 else None].decode("latin1"))
        p += hdr + 4 * cnt
    return out


def glossary(nds):
    """English text -> {lang: text}, from every message table the ROM holds in all five languages (same message number)"""
    gl = {}
    for name in nds.files:
        if not name.endswith(".gp2"):
            continue
        d = nds.read(name)
        if d[:4] != b"GPC2":
            continue
        try:
            arc = gpc2(d)
        except Exception:
            continue
        stems = {}
        for m, b in arc.items():
            mm = re.match(r"(.*)_(en|de|fr|es|it)\.nat$", m)
            if mm:
                stems.setdefault(mm.group(1), {})[mm.group(2)] = b
        for st, v in stems.items():
            if len(v) < 5 or st.startswith("itemexpl"):
                continue
            try:
                t = {l: nat_table(b) for l, b in v.items()}
            except Exception:
                continue
            for num, en in t["en"].items():
                if 1 < len(en) <= 100 and "\n" not in en and all(num in t[l] for l in LANGS):
                    row = gl.setdefault(en, {})
                    for l in LANGS[1:]:
                        row.setdefault(l, t[l][num])
    # place names: data/map/mapname.gp2, a tagged table (tag 0x67 = id + string offset); where one English name is used by
    # several entries (a field region "Région de X" and the town "X") the shortest wording is the town's
    try:
        arc = gpc2(nds.read("data/map/mapname.gp2"))
        maps = {l: map_names(arc["mapname_%s.bin" % l]) for l in LANGS}
        for mid, en in maps["en"].items():
            if len(en) < 2 or not en.isascii():
                continue
            row = gl.setdefault(en, {})
            for l in LANGS[1:]:
                t = maps[l].get(mid, "")
                if t and (l not in row or len(t) < len(row[l])):
                    row[l] = t
    except Exception:
        pass
    # monster names: mon_list_<lang>.nat, 32-byte records, the name's offset at +8, strings after the records
    try:
        arc = gpc2(nds.read("data/prm/mon_list.gp2"))
        names = {}
        for l in LANGS:
            b = arc["mon_list_%s.nat" % l]
            count = struct.unpack_from("<I", b, 0)[0] & 0xFFF
            base = 4 + 32 * count
            lst = []
            for i in range(count):
                off = struct.unpack_from("<I", b, 4 + 32 * i + 8)[0]
                e = b.find(b"\0", base + off)
                lst.append(clean(b[base + off:e if e >= 0 else None].decode("latin1")))
            names[l] = lst
        for i, en in enumerate(names["en"]):
            if en:
                row = gl.setdefault(en, {})
                for l in LANGS[1:]:
                    row.setdefault(l, names[l][i])
    except Exception:
        pass
    return gl


def tagged_records(b):
    """[(tag, [values])] of a tagged data table (see map_names)"""
    stab = struct.unpack_from("<I", b, 4)[0]
    p, out = 16, []
    while p < stab:
        if b[p:p + 4] == b"\xff\xff\xff\xff":
            p += 4
            continue
        tag, cnt = struct.unpack_from("<HB", b, p)
        hdr = ((3 + (cnt * 2 + 7) // 8 + 3) // 4) * 4
        out.append((tag, list(struct.unpack_from("<%dI" % cnt, b, p + hdr))))
        p += hdr + 4 * cnt
    return out


def monsters(nds):
    """[(monster number, English name)] of the ordinary monsters, the ones that roam the field (fld_mondata.bin:
    the tag 0x65 records; value 2, the margin by which the party's level must pass the monster's before it runs, is 0 on the bosses only)"""
    arc = gpc2(nds.read("data/prm/mon_list.gp2"))
    b = arc["mon_list_en.nat"]
    count = struct.unpack_from("<I", b, 0)[0] & 0xFFF
    base = 4 + 32 * count
    names = {}
    for i in range(count):
        off = struct.unpack_from("<I", b, 4 + 32 * i + 8)[0]
        num = struct.unpack_from("<H", b, 4 + 32 * i + 12)[0]
        e = b.find(b"\0", base + off)
        names.setdefault(num, clean(b[base + off:e if e >= 0 else None].decode("latin1")))
    ordinary = [v[0] for t, v in tagged_records(nds.read("data/prm/fld_mondata.bin")) if t == 0x65 and len(v) >= 3 and v[2] != 0]
    return sorted((n, names[n]) for n in set(ordinary) if n in names and names[n])


def write_tables(rom_path, out):
    """writes <out>/rom-itemname-<lang>.tsv for every language in the ROM"""
    nds = Nds(rom_path)
    arc = gpc2(nds.read("data/prm/itemname.gp2"))
    os.makedirs(out, exist_ok=True)
    done = []
    for lang in LANGS:
        k = "itemname_%s.nat" % lang
        if k not in arc:
            continue
        t = item_names(arc[k])
        with open(os.path.join(out, "rom-itemname-%s.tsv" % lang), "w", encoding="utf-8", newline="\n") as f:
            for iid in sorted(t):
                f.write("%d\t%s\t%s\n" % (iid, clean(t[iid][0]), clean(t[iid][1])))
        done.append(lang)
    gl = glossary(nds)
    with open(os.path.join(out, "rom-glossary.tsv"), "w", encoding="utf-8", newline="\n") as f:
        for en, row in sorted(gl.items()):
            if all(l in row for l in LANGS[1:]) and "\t" not in en:
                f.write("\t".join([en] + [row[l].replace("\t", " ") for l in LANGS[1:]]) + "\n")
    return done


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    nds = Nds(a[0])
    out = a[a.index("--out") + 1] if "--out" in a else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lang")
    arc = gpc2(nds.read("data/prm/itemname.gp2"))
    tables = {}
    for lang in LANGS:
        k = "itemname_%s.nat" % lang
        if k in arc:
            tables[lang] = item_names(arc[k])
    if "--find" in a:
        w = a[a.index("--find") + 1].lower()
        for lang, t in tables.items():
            for iid, (s, p) in t.items():
                if w in s.lower():
                    print(lang, "%04X" % iid, s)
        return
    os.makedirs(out, exist_ok=True)
    for lang, t in tables.items():
        with open(os.path.join(out, "rom-itemname-%s.tsv" % lang), "w", encoding="utf-8", newline="\n") as f:
            for iid in sorted(t):
                f.write("%d\t%s\t%s\n" % (iid, clean(t[iid][0]), clean(t[iid][1])))
    print("wrote", ", ".join("%s: %d" % (l, len(t)) for l, t in tables.items()), "->", os.path.abspath(out))


if __name__ == "__main__":
    main()
