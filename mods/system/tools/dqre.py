#!/usr/bin/env python3
"""Reverse-engineering helper: answers the questions that come up again and again, in one command each.

  dqre.py [--root GAME] func  ADDR            which game function contains ADDR (name, module, size) + 5 neighbours
  dqre.py [--root GAME] names REGEX           functions whose name matches (the ROM's own symbol names)
  dqre.py [--root GAME] ar    "02345678 0000FFFF" ...   decode Action Replay lines: kind, target, containing function
  dqre.py ram  DUMP ADDR [WORDS]              words of a DQIX_RAMDUMP file (ram<frame>.bin) at a DS address
  dqre.py diff A B [--lo HEX --hi HEX]        ranges that differ between two RAM dumps (+ function if in code)

Dumps come from DQIX_RAMDUMP=dir,frame (see docs/RE.md). Addresses are DS addresses (main RAM 0x02000000..0x023FFFFF).
"""
import argparse, bisect, os, re, sys

BASE = 0x02000000


def find_root(a):
    for c in (a, os.environ.get("DQIX_ROOT"), None):
        if c is None:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dev-root.txt")
            if os.path.isfile(p):
                c = open(p).read().strip()
        if c and os.path.isfile(os.path.join(c, "build", "recomp", "dispatch_table.c")):
            return c
    sys.exit("game folder not found: --root <DQIX Enhanced folder> or DQIX_ROOT")


def load_funcs(root):
    rx = re.compile(r'\{\s*(-?\d+),\s*0x([0-9A-Fa-f]+)u,\s*(\d+),\s*(\w+),\s*"([^"]*)"')
    out = []
    for m in rx.finditer(open(os.path.join(root, "build", "recomp", "dispatch_table.c"), encoding="utf-8", errors="replace").read()):
        ov, a, sz, fn, name = int(m[1]), int(m[2], 16), int(m[3]), m[4], m[5]
        out.append((a & ~1, ov, sz, name, fn, a & 1))
    out.sort()
    return out


def containing(funcs, addr, keys=None):
    keys = keys or [f[0] for f in funcs]
    i = bisect.bisect_right(keys, addr) - 1
    return (i, funcs[i]) if i >= 0 else (None, None)


def fmt(f):
    return "%08x %-5s %-28s %s %s" % (f[0], "thumb" if f[5] else "arm", f[3] or "(unnamed)", "ovl%d" % f[1] if f[1] >= 0 else "main", f[4])


def cmd_func(a):
    funcs = load_funcs(find_root(a.root)); addr = int(a.addr, 16)
    i, f = containing(funcs, addr)
    if f is None:
        sys.exit("below the first known function")
    for j in range(max(0, i - 2), min(len(funcs), i + 4)):
        print(("=> " if j == i else "   ") + fmt(funcs[j]))
    print("offset into function: 0x%x" % (addr - f[0]))


def cmd_names(a):
    rx = re.compile(a.regex, re.I)
    for f in load_funcs(find_root(a.root)):
        if f[3] and rx.search(f[3]):
            print(fmt(f))


def decode_ar(lines):
    """Action Replay 'type address value' lines -> description. Only the opcodes the DS AR engine defines."""
    for line in lines:
        w = line.replace(",", " ").split()
        if len(w) != 2 or not all(re.fullmatch(r"[0-9A-Fa-f]{8}", x) for x in w):
            yield line, None, None, "not a code line"; continue
        c, v = int(w[0], 16), int(w[1], 16)
        t = c >> 28; ad = BASE | (c & 0x0FFFFFFF) if t in (0, 1, 2) else c & 0x0FFFFFFF
        if t in (0, 1, 2):
            yield line, ad, 4 >> (2 - t) if t else 4, "write %s %#x" % (("word", "half", "byte")[t if t < 3 else 0] if t else "word", v)
        elif t == 3 or t == 4 or t == 5 or t == 6 or t == 7 or t == 8 or t == 9 or t == 0xA or t == 0xB or t == 0xC or t == 0xD or t == 0xE:
            yield line, None, None, {3: "if > word", 4: "if < word", 5: "if = word", 6: "if != word", 7: "if > half", 8: "if < half", 9: "if = half",
                                      0xA: "if != half", 0xB: "load offset", 0xC: "loop/end", 0xD: "special (END/ELSE/OFFSET...)", 0xE: "write bytes: following lines are data"}[t]
        else:
            yield line, None, None, "key / D2 etc"


def cmd_ar(a):
    funcs = load_funcs(find_root(a.root))
    for line, ad, _, what in decode_ar(a.lines):
        s = "%-20s %s" % (line, what)
        if ad is not None:
            _, f = containing(funcs, ad)
            # inside the program's own code, or plain data? the table only knows code
            s += "   -> %08x" % ad
            if f is not None and ad < f[0] + max(f[2], 4):
                s += "  INSIDE CODE %s+0x%x" % (f[3] or f[4], ad - f[0])
        print(s)


def read_dump(path):
    return open(path, "rb").read()


def cmd_ram(a):
    d = read_dump(a.dump); off = int(a.addr, 16) - BASE
    for i in range(a.words):
        o = off + 4 * i
        if o < 0 or o + 4 > len(d):
            break
        print("%08x  %08x" % (BASE + o, int.from_bytes(d[o:o + 4], "little")))


def cmd_diff(a):
    x, y = read_dump(a.a), read_dump(a.b); n = min(len(x), len(y))
    lo = int(a.lo, 16) - BASE if a.lo else 0; hi = min(n, int(a.hi, 16) - BASE if a.hi else n)
    funcs = load_funcs(find_root(a.root)) if a.names else None
    i = lo; runs = []
    while i < hi:
        if x[i] != y[i]:
            j = i
            while j < hi and (x[j] != y[j] or (j + 1 < hi and x[j + 1] != y[j + 1])):
                j += 1
            runs.append((i, j)); i = j
        else:
            i += 1
    for s, e in runs[:a.limit]:
        t = ""
        if funcs:
            _, f = containing(funcs, BASE + s)
            if f is not None and BASE + s < f[0] + f[2]:
                t = "  in code " + (f[3] or f[4])
        print("%08x..%08x (%d bytes)%s" % (BASE + s, BASE + e, e - s, t))
    print("%d differing ranges" % len(runs))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root")
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("func"); q.add_argument("addr"); q.set_defaults(f=cmd_func)
    q = s.add_parser("names"); q.add_argument("regex"); q.set_defaults(f=cmd_names)
    q = s.add_parser("ar"); q.add_argument("lines", nargs="+"); q.set_defaults(f=cmd_ar)
    q = s.add_parser("ram"); q.add_argument("dump"); q.add_argument("addr"); q.add_argument("words", type=int, nargs="?", default=8); q.set_defaults(f=cmd_ram)
    q = s.add_parser("diff"); q.add_argument("a"); q.add_argument("b"); q.add_argument("--lo"); q.add_argument("--hi")
    q.add_argument("--limit", type=int, default=60); q.add_argument("--names", action="store_true", help="name the function when a range is code"); q.set_defaults(f=cmd_diff)
    a = p.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
