#!/usr/bin/env python3
"""Everything the cheat menu offers, sorted and checked against your ROM.

  catalog.py [project folder]            writes mods/bin/catalog.txt (the menu reads it)
  catalog.py [project folder] --report   also says why each code ended up where it did

Where the codes come from:
  mods/database/<game code>.txt   the whole R4 cheat list for your ROM (r4_to_text.py)
  mods/cheats/*.txt               live cheats made by hand (tried out)
  mods/code/*.txt                 code mods made by hand (tried out)

An Action Replay code is written for a DS, where it can change anything at any
moment. Here the game's program is compiled PC code, so every code is worked
out first, by running it against a copy of your ROM's own program:

  live     it only changes the game's data: the game carries it out while you play
  code     it changes instructions: those go into the build (patches.txt), after
           each one was found in your ROM where the code says it is
  blocked  it can't work here, or can't be checked: it stays off, with the reason
           (a routine of its own added to the program, DS hardware, an overlay it
           doesn't name, a jump out of the game's code...)

Nothing here changes the game: it only reads. apply_code_mods.py puts the code
mods that are switched on into the build.
"""
import bisect
import glob
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_code_mods as acm

KEY_NAMES = ["A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L", "X", "Y"]
BUDGET = 400000

# The database's folders, put into the menu's pages: (folder name matches, page, put before each code's name)
PAGES = [
    (r"random game enhancer", "Speed & comfort", ""),
    (r"movement speed", "Speed & comfort", ""),
    (r"camera", "Speed & comfort", ""),
    (r"exp multiplier|gold multiplier", "Experience & gold", ""),
    (r"hero codes for battle", "Party", "Hero: "),
    (r"infinite hp/mp", "Party", "Never goes down: "),
    (r"job modifier", "Party", ""),
    (r"max exp for all jobs", "Party", "Max EXP in every vocation: "),
    (r"skill point", "Party", ""),
    (r"battle codes", "Battle", ""),
    (r"enemy hp", "Battle", "Enemy HP 1: "),
    (r"enemy mp", "Battle", "Enemy MP 0: "),
    (r"encounter", "Battle", ""),
    (r"item codes", "Items", "99 of every: "),
    (r"treasure chest", "Items", ""),
    (r"alchemy", "Alchemy", ""),
    (r"daylight", "World", ""),
    (r"grotto", "World", ""),
    (r"unlock", "Unlocks", ""),
    (r"battle records|quest", "Records & quests", ""),
    (r"hide the party|big head|size modif", "Fun", ""),
    (r"miscellaneous", "Miscellaneous", ""),
    (r"backlight|wfc|wi-?fi", "System", ""),
]
PAGE_ORDER = ["Speed & comfort", "Experience & gold", "Party", "Battle", "Items", "Alchemy", "World",
              "Unlocks", "Records & quests", "Fun", "Miscellaneous", "My cheats"]

REASONS = {
    "hook": "It adds a routine of its own to the game's program. This compiled version can't check such a routine, so it stays off.",
    "jump": "It sends the game's program to a place outside its own code. That can't be checked, so it stays off.",
    "overlay": "It doesn't say which part of the game it changes, so it can't be checked against your ROM.",
    "ovldata": "It changes data inside a part of the program that this version compares with your ROM.",
    "selfmod": "Its new instructions write into the game's program while it runs. That can't be checked, so it stays off.",
    "mixed": "It changes the program and, while you play, data that goes with it. The two can't be kept in step in this version, so it stays off.",
    "hardware": "It works on the DS's own hardware (backlight, wireless chip...), which a PC doesn't have.",
    "nomatch": "Your ROM's program isn't what this code expects, so it would do nothing.",
    "empty": "It has no code lines.",
    "long": "It is too long to send to the game (more than 1023 lines).",
    "piracy": "Not needed: this version already takes the copy protection's trap out.",
    "wfc": "Not needed: choose the server in the game's own Wireless menu instead.",
}

LAUNCH = [
    ("launch:fast", "Always fast forward", "DQIX_FAST=1",
     "The whole game runs as fast as your PC can, from the moment it starts. (While playing, Tab does the same.) No sound while it's fast. Takes effect the next time the game starts."),
    ("launch:card", "Instant loading", "DQIX_CARD_INSTANT=1",
     "Skips the DS cartridge's reading delays. Only while you play alone: in a session with friends the game keeps the real delays by itself, so everyone stays in sync. Takes effect the next time the game starts."),
]


# ---------------------------------------------------------------- your ROM
class Rom:
    def __init__(self, root):
        self.root = root
        extract = os.path.join(root, "build", "extract")
        self.region = "usa"
        try:
            self.region = open(os.path.join(root, "build", "obj", "region.txt")).read().strip() or "usa"
        except OSError:
            pass
        self.shifts = acm.eur_shifts(root) if self.region == "eur" else []
        mods = acm.load_modules(extract)
        self.main = mods[0]
        self.overlays = mods[1:]
        self.by_name = {m.name: m for m in mods}
        self.ovl_lo = min(m.base for m in self.overlays) if self.overlays else 0
        self.ovl_hi = max(m.base + len(m.data) for m in self.overlays) if self.overlays else 0
        with open(os.path.join(extract, "..", "..", "game", "data", "dqix.nds"), "rb") as f:
            head = f.read(0x200)
        self.game = head[12:16].decode("ascii", "replace")
        self.crc = ~zlib.crc32(head) & 0xFFFFFFFF          # what an R4 database calls the ROM's checksum
        # where the instructions are: the recompiler's own list of functions
        self.funcs = {}
        table = os.path.join(root, "build", "recomp", "dispatch_table.c")
        for ovl, addr, size in re.findall(r"\{\s*(-?\d+),\s*0x([0-9a-fA-F]+)u,\s*(\d+),", open(table).read()):
            a, size = int(addr, 16), int(size)
            name = "main" if int(ovl) < 0 else f"ov{int(ovl):03d}"
            if name == "main" and not self.in_image(self.main, a & ~1):
                continue                                    # ITCM
            self.funcs.setdefault(name, []).append((a & ~1, (a & ~1) + size, a & 1))
        for v in self.funcs.values():
            v.sort()

    @staticmethod
    def in_image(m, a):
        return m.base <= a < m.base + len(m.data)

    def func_at(self, m, a):
        """(start, end, thumb) of the function of module m that holds address a, or None."""
        fs = self.funcs.get(m.name, [])
        i = bisect.bisect_right(fs, (a, 1 << 40, 2)) - 1
        while i >= 0 and i >= bisect.bisect_right(fs, (a, 1 << 40, 2)) - 4:    # (secondary entries overlap)
            if fs[i][0] <= a < fs[i][1]:
                return fs[i]
            i -= 1
        return None

    def in_any_overlay(self, a):
        return any(self.in_image(m, a) for m in self.overlays)

    def to_rom(self, a):            # USA main-program address -> this ROM's
        for lo, hi, sh in self.shifts:
            if lo <= a < hi:
                return a + sh
        return a

    def from_rom(self, a):          # and back (patches.txt wants USA addresses)
        for lo, hi, sh in self.shifts:
            if lo + sh <= a < hi + sh:
                return a - sh
        return a


class Mem:
    """The DS's memory as the ROM leaves it: the main program, one overlay (or none), zeros elsewhere."""

    def __init__(self, rom, ctx):
        self.rom, self.ctx, self.w = rom, ctx, {}

    @staticmethod
    def norm(a):
        return 0x02000000 | (a & 0x3FFFFF)

    def is_static(self, a):
        """Is this the program itself (what a "only if the game has this instruction" line looks at)?
        The data sections, the heap and everything else change while the game runs."""
        if (a >> 24) != 2:
            return True
        a = self.norm(a)
        if Rom.in_image(self.rom.main, a):
            return self.rom.func_at(self.rom.main, a) is not None
        return self.rom.in_any_overlay(a)

    def byte(self, a):
        if a in self.w:
            return self.w[a]
        for m in (self.rom.main, self.ctx):
            if m is not None and Rom.in_image(m, a):
                return m.data[a - m.base]
        return 0

    def read(self, a, n):
        if (a >> 24) != 2:
            return 0
        a = self.norm(a)
        return sum(self.byte(a + i) << (8 * i) for i in range(n))

    def write(self, a, n, v):
        if (a >> 24) != 2:
            return
        a = self.norm(a)
        for i in range(n):
            self.w[a + i] = (v >> (8 * i)) & 0xFF


# ---------------------------------------------------------------- Action Replay, as in ar_engine.h
def is_keyreg(a):
    return a in (0x04000130, 0x04000136) or (a & 0x0FFFFFFF) == 0x027FFFA8


def keyreg(a, keys):
    if a == 0x04000130:
        return ~keys & 0x3FF
    if a == 0x04000136:
        return 0x7F & ~(keys >> 10 & 3)
    return 0x2C00 & ~((keys >> 10 & 3) << 10)


def ar_sim(ops, mem, keymode, flags):
    """One pass. keymode: "all" (every key condition holds), "none", or the (a, b) of the one that holds."""
    offset = data = 0
    skip = 0
    loop_start, loop_left = -1, 0
    budget = BUDGET
    n, pc = len(ops), 0
    M = 0xFFFFFFFF
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        budget -= 1
        if budget < 0:
            flags["endless"] = True
            return
        if skip:
            if 3 <= t <= 0xA:
                skip += 1
            elif top == 0xD0:
                skip -= 1
            elif top in (0xD1, 0xD2):
                skip = 0
                if top == 0xD2 and loop_start < 0:
                    offset = data = 0
                if loop_start >= 0:
                    if loop_left > 0:
                        loop_left -= 1
                        pc = loop_start + 1
                        continue
                    loop_start = -1
                    if top == 0xD2:
                        offset = data = 0
            elif t == 0xE:
                pc += (b + 7) // 8
            pc += 1
            continue
        if t <= 2:
            addr = (addr + offset) & M
        elif t <= 0xB and addr == 0:
            addr = offset
        if t == 0:
            mem.write(addr, 4, b)
        elif t == 1:
            mem.write(addr, 2, b)
        elif t == 2:
            mem.write(addr, 1, b)
        elif 3 <= t <= 0xA:
            key = is_keyreg(addr)
            if key and (keymode == "all" or keymode == (a, b)):
                pc += 1
                continue
            if not key and not mem.is_static(addr):
                flags["dynamic"] = True
            if t <= 6:
                v = keyreg(addr, 0) if key else mem.read(addr, 4)
                ok = b > v if t == 3 else b < v if t == 4 else b == v if t == 5 else b != v
            else:
                v = (keyreg(addr, 0) if key else mem.read(addr, 2)) & ~(b >> 16) & 0xFFFF
                y = b & 0xFFFF
                ok = y > v if t == 7 else y < v if t == 8 else y == v if t == 9 else y != v
            if not ok:
                skip = 1
        elif t == 0xB:
            flags["dynamic"] = True
            offset = mem.read(addr, 4)
        elif t == 0xC:
            if top == 0xC0:
                loop_start, loop_left = pc, b
        elif t == 0xD:
            if top in (0xD1, 0xD2):
                if loop_start >= 0 and loop_left > 0:
                    loop_left -= 1
                    pc = loop_start + 1
                    continue
                loop_start = -1 if loop_start >= 0 else loop_start
                if top == 0xD2:
                    offset = data = 0
            elif top == 0xD3:
                offset = b
            elif top == 0xD4:
                data = (data + b) & M
            elif top == 0xD5:
                data = b
            elif top == 0xD6:
                mem.write((b + offset) & M, 4, data)
                offset = (offset + 4) & M
            elif top == 0xD7:
                mem.write((b + offset) & M, 2, data)
                offset = (offset + 2) & M
            elif top == 0xD8:
                mem.write((b + offset) & M, 1, data)
                offset = (offset + 1) & M
            elif top in (0xD9, 0xDA, 0xDB):
                src = (b + offset) & M
                if not mem.is_static(src):
                    flags["dynamic"] = True
                data = mem.read(src, 4 if top == 0xD9 else 2 if top == 0xDA else 1)
            elif top == 0xDC:
                offset = (offset + b) & M
        elif t == 0xE:
            dst = (addr + offset) & M
            i, line = 0, pc + 1
            while line < n and i < b:
                for w in ops[line]:
                    for s in range(4):
                        if i < b:
                            mem.write((dst + i) & M, 1, (w >> (8 * s)) & 0xFF)
                            i += 1
                line += 1
            pc += (b + 7) // 8
        elif t == 0xF:
            if b > budget:
                flags["endless"] = True
                return
            budget -= b
            for i in range(b):
                mem.write((addr + i) & M, 1, mem.read((offset + i) & M, 1))
        pc += 1


def scan(ops):
    """What a code asks of the DS, without running it: its key conditions, and hardware it touches."""
    keys, hardware = [], False
    pc, n = 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        if t == 0xE:
            hardware |= (addr >> 24) >= 3
            pc += 1 + (b + 7) // 8
            continue
        if 3 <= t <= 0xA and is_keyreg(addr):
            if (a, b) not in keys:
                keys.append((a, b))
        elif t <= 0xB or t == 0xF:
            hardware |= (addr >> 24) >= 3
        elif top in (0xD3, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xDB):
            hardware |= 3 <= (b >> 24) < 0x10
        pc += 1
    return keys, hardware


def static_writes(ops):
    """Every place a code can write: [(address, bytes)], and whether it also writes through a pointer."""
    out, pointer, moved = [], False, False
    pc, n = 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        if t <= 2 or t == 0xE or t == 0xF:
            size = (4, 2, 1)[t] if t <= 2 else b
            if moved and t != 0xF:
                pointer = True
            else:
                out.append((addr, size))
            if t == 0xE:
                pc += (b + 7) // 8
        elif top in (0xD6, 0xD7, 0xD8):
            if moved:
                pointer = True
            else:
                out.append((b, {0xD6: 4, 0xD7: 2, 0xD8: 1}[top]))
            moved = True                                    # the next one is further on
        elif t == 0xB or top in (0xD3, 0xDC):
            moved = True
        elif top == 0xD2:
            moved = False
        pc += 1
    return out, pointer


def moved_for_rom(rom, ops):
    """The same code with main-program addresses moved from the USA version's to this ROM's."""
    out, pc, n = [], 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, addr = a >> 28, a & 0x0FFFFFFF
        if t <= 0xA or t == 0xE:
            if Rom.in_image(rom.main, addr) and rom.func_at(rom.main, rom.to_rom(addr)):
                a = (a & 0xF0000000) | rom.to_rom(addr)
        out.append((a, b))
        if t == 0xE:
            k = (b + 7) // 8
            out += ops[pc + 1:pc + 1 + k]
            pc += k
        pc += 1
    return out


def key_text(cond):
    """"L+R" for 94000130 FCFF0000; "" when it isn't a plain "these are held"."""
    a, b = cond
    t, addr = a >> 28, a & 0x0FFFFFFF
    if t != 9:
        return ""
    look, want = ~(b >> 16) & 0xFFFF, b & 0xFFFF
    if want & look:
        return ""                                           # asks for a key NOT held
    if addr == 0x04000130:
        bits = [i for i in range(10) if look >> i & 1]
    elif addr == 0x04000136:
        bits = [10 + i for i in range(2) if look >> i & 1]
    else:
        bits = [i for i in (10, 11) if look >> i & 1]
    order = [9, 8, 2, 3, 0, 1, 10, 11, 6, 7, 5, 4]          # L R SELECT START A B X Y, then directions
    return "+".join(KEY_NAMES[i] for i in order if i in bits)


def is_branch(w):
    return (w & 0x0E000000) == 0x0A000000


def stores_into_program(w):
    """An ARM instruction that writes to memory at an address counted from itself (str ..., [pc, #n])."""
    if (w >> 28) == 0xF or ((w >> 16) & 0xF) != 15 or (w >> 20) & 1:
        return False
    if (w & 0x0C000000) == 0x04000000:
        return True                                         # str / strb
    return (w & 0x0E000090) == 0x00000090 and (w >> 5) & 3 != 0     # strh and the like


def branch_target(addr, w):
    off = w & 0x00FFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (addr + 8 + (off << 2) + (2 if (w >> 28) == 0xF and (w >> 24) & 1 else 0)) & 0xFFFFFFFF


def classify(rom, ops):
    """-> dict(kind=live|code|blocked, why=..., variants=[(label, [(module, address, word)])], keys=[...])."""
    keys, hardware = scan(ops)
    out = {"keys": keys, "variants": []}
    if not ops:
        return dict(out, kind="blocked", why="empty")
    modes = ["none"] + keys + (["all"] if len(keys) != 1 else [])
    found = {}                      # keymode -> {(module, address): word}
    touched = set()                 # instruction words it writes (also when it puts back what was there)
    mixed = False                   # a run that changes instructions also writes elsewhere
    any_write = dynamic = False
    loose = ovldata = False
    for ctx in [None] + rom.overlays:
        for mode in modes:
            mem, flags = Mem(rom, ctx), {}
            ar_sim(ops, mem, mode, flags)
            dynamic |= bool(flags.get("dynamic"))
            if not mem.w:
                continue
            any_write = True
            code, other = {}, 0
            for a in mem.w:
                m = None
                if Rom.in_image(rom.main, a):
                    m = rom.main if rom.func_at(rom.main, a) else None
                elif ctx is not None and Rom.in_image(ctx, a):
                    if rom.func_at(ctx, a):
                        m = ctx
                    else:
                        ovldata = True
                        continue
                elif rom.in_any_overlay(a):
                    if ctx is None:
                        loose = True                        # written whatever is loaded there
                    continue
                if m is None:
                    other += 1
                    continue
                code[(m.name, a & ~3)] = None
                touched.add(a & ~3)
            for name, wa in list(code):
                m = rom.by_name[name]
                word = sum(mem.byte(wa + i) << (8 * i) for i in range(4))
                if word == m.word(wa):
                    del code[(name, wa)]                    # puts back what is there anyway
                else:
                    code[(name, wa)] = word
            if code:
                if other:
                    mixed = True
                found.setdefault(mode, {}).update(code)
    if found:
        if mixed:
            return dict(out, kind="blocked", why="hook")
        writes, pointer = static_writes(ops)
        if pointer or any((Mem.norm(a + i) & ~3) not in touched for a, size in writes for i in range(0, max(size, 1), 4)):
            return dict(out, kind="blocked", why="mixed")
        for patch in found.values():
            for (name, wa), word in patch.items():
                m = rom.by_name[name]
                fn = rom.func_at(m, wa)
                if fn and not fn[2] and stores_into_program(word):
                    return dict(out, kind="blocked", why="selfmod")
                if fn and not fn[2] and is_branch(word):
                    tgt = branch_target(wa, word)
                    inside = (Rom.in_image(m, tgt) and rom.func_at(m, tgt)) or \
                             (Rom.in_image(rom.main, tgt) and rom.func_at(rom.main, tgt))
                    old = m.word(wa)
                    same = is_branch(old) and branch_target(wa, old) == tgt
                    if not inside and not same:
                        return dict(out, kind="blocked", why="jump")
        variants = []
        if found.get("none"):
            variants.append(("", found["none"]))            # it's on whatever is held: that is the mod
        else:
            seen = []
            for mode in keys + ["all"]:
                p = found.get(mode)
                if p and p not in seen:
                    seen.append(p)
                    variants.append((key_text(mode) if mode != "all" else "", p))
        out["variants"] = [(label, sorted((n, a, w) for (n, a), w in p.items())) for label, p in variants]
        out["held"] = not found.get("none")
        return dict(out, kind="code")
    if loose:
        return dict(out, kind="blocked", why="overlay")
    if ovldata:
        return dict(out, kind="blocked", why="ovldata")
    if hardware:
        return dict(out, kind="blocked", why="hardware")
    if not any_write and not dynamic:
        return dict(out, kind="blocked", why="nomatch")
    if len(ops) > 1023:
        return dict(out, kind="blocked", why="long")
    return dict(out, kind="live")


# ---------------------------------------------------------------- the files
def clean(s):
    return " ".join(str(s).replace("\t", " ").split())


def strip_keys(name):
    """"[SEL]All shield" -> "All shield": the menu shows the keys by itself."""
    rest = re.sub(r"^\s*\[(?:[A-Za-z/]+)(?:\s*\+\s*[A-Za-z/]+)*(?:\s+On/Off)?\]\s*", "", name).strip()
    return rest if rest and (rest[0].isupper() or rest[0].isdigit()) else name


def read_database(path):
    """-> (game code, crc, title, [folder]) with folder = dict(name, note, one, codes=[dict(name, note, ops)])."""
    game = crc = title = None
    folders, top, cur, last = [], None, None, None
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@game"):
            p = s.split(None, 3)
            game, crc, title = p[1], int(p[2], 16), p[3] if len(p) > 3 else p[1]
        elif s.startswith("@folder"):
            cur = {"name": s[7:].strip(), "note": "", "one": False, "codes": []}
            folders.append(cur)
            last = cur
        elif s == "@one":
            if cur is not None:
                cur["one"] = True
        elif s == "@end":
            cur = None
        elif s.startswith("@note"):
            if last is not None:
                last["note"] = s[5:].strip()
        elif s.startswith("@code"):
            last = {"name": s[5:].strip(), "note": "", "ops": []}
            if cur is None:
                if top is None:
                    top = {"name": "", "note": "", "one": False, "codes": []}
                    folders.append(top)
                top["codes"].append(last)
            else:
                cur["codes"].append(last)
        else:
            p = s.split()
            if len(p) == 2 and last is not None and "ops" in last:
                try:
                    last["ops"].append((int(p[0], 16), int(p[1], 16)))
                except ValueError:
                    pass
    return game, crc, title, folders


def read_cheat_file(path):
    name, about, mode, cat, ops = os.path.basename(path)[:-4], "", "always", "", []
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if s.startswith("#"):
            m = re.match(r"#\s*(\w+)\s*:\s*(.*)", s)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                if k == "name":
                    name = v
                elif k == "about":
                    about = v
                elif k == "mode":
                    mode = "once" if v.lower() == "once" else "always"
                elif k == "category":
                    cat = v
            continue
        p = s.split()
        if len(p) == 2:
            try:
                ops.append((int(p[0], 16), int(p[1], 16)))
            except ValueError:
                pass
    return name, about, mode, cat, ops


def file_header(path, key):
    for line in open(path, encoding="utf-8-sig"):
        m = re.match(r"#\s*(\w+)\s*:\s*(.*)", line.strip())
        if m and m.group(1).lower() == key:
            return m.group(2).strip()
    return ""


def fit_code_file(rom, checks, patches):
    """A hand-made code mod's instructions in this ROM: [(module, address, word)], or None."""
    out = []
    for m in [rom.main] + rom.overlays:
        ways = [rom.to_rom, lambda a: a] if m is rom.main else [lambda a: a]
        for ra in ways:
            if all(m.word(ra(a)) == w for a, w in checks) and all(m.word(ra(a)) is not None for a, _ in patches):
                out += [(m.name, ra(a), w) for a, w in patches]
                break
    return sorted(set(out)) or None


def page_of(folder):
    for pat, page, prefix in PAGES:
        if re.search(pat, folder, re.I):
            return page, prefix
    return (strip_keys(folder) or "Miscellaneous"), ""


def db_id(folder, name, ops):
    text = folder + "\0" + name + "\0" + ",".join(f"{a:08X}{b:08X}" for a, b in ops)
    return f"db:{zlib.crc32(text.encode('utf-8')) & 0xFFFFFFFF:08x}"


def build(root):
    """-> (info, entries, groups). An entry is a dict; see write() for what the menu gets."""
    rom = Rom(root)
    entries, groups = [], []

    # ---- the hand-made files first: a database code that does the same becomes that file's
    by_sig = {}
    files = []
    for f in sorted(glob.glob(os.path.join(root, "mods", "cheats", "*.txt"))):
        base = os.path.basename(f)
        if base.lower() == "on.txt" or base.startswith("_"):
            continue
        name, about, mode, cat, ops = read_cheat_file(f)
        if not ops:
            continue
        keys, _ = scan(ops)
        e = dict(id="file:cheats/" + base, name=name, note=about, cat=cat, group="", kind="live", status="tested",
                 mode=mode, ops=ops, keys=keys, reason="", file="", on=False, patch=[], env="")
        if len(ops) > 1023:
            e.update(kind="blocked", status="blocked", reason=REASONS["long"])
        files.append(e)
        by_sig.setdefault(("live", tuple(ops)), e)
    for f in sorted(glob.glob(os.path.join(root, "mods", "code", "*.txt"))):
        base = os.path.basename(f)
        if base.startswith("_"):
            continue
        name, on, checks, patches, errors = acm.parse_mod(f)
        e = dict(id="file:code/" + base, name=name, note=file_header(f, "about"), cat=file_header(f, "category"),
                 group="", kind="code", status="tested", mode="", ops=[], keys=[], reason="",
                 file="code/" + base, on=on, patch=[], env="")
        fit = None if errors else fit_code_file(rom, checks, patches)
        if errors:
            e.update(kind="blocked", status="blocked", reason="The file has a mistake: " + "; ".join(errors))
        elif not fit:
            e.update(kind="blocked", status="blocked", reason=REASONS["nomatch"])
        else:
            e["patch"] = fit
            by_sig.setdefault(("code", tuple(fit)), e)
        files.append(e)
    used, seen_sigs = set(), set()

    # ---- the database for this ROM
    info = dict(game=rom.game, region=rom.region, title="", database="", exact="0")
    db = os.path.join(root, "mods", "database", rom.game + ".txt")
    folders = []
    if os.path.isfile(db):
        game, crc, title, folders = read_database(db)
        info.update(title=title, database=os.path.basename(db), exact="1" if crc == rom.crc else "0")
    for folder in folders:
        page, prefix = page_of(folder["name"]) if folder["name"] else ("System", "")
        if page == "System":
            continue                                        # backlight / Wi-Fi / anti-piracy codes: not needed on a PC
        made = []
        for c in folder["codes"]:
            if not c["ops"]:
                continue                                    # a line of text in the list ("Use V1 or V2 only")
            r = classify(rom, c["ops"])
            moved = False
            if r["kind"] == "blocked" and r["why"] == "nomatch" and rom.shifts:
                # the database sometimes lists a USA code under the European game: the same code,
                # moved to where this ROM has it, counts when its instructions are there
                r2 = classify(rom, moved_for_rom(rom, c["ops"]))
                if r2["kind"] == "code":
                    r, moved = r2, True
            if re.search(r"backlight", c["name"], re.I):
                r = dict(r, kind="blocked", why="hardware")
            shown = strip_keys(c["name"])
            note = c["note"] if clean(c["note"]) != clean(c["name"]) else ""
            if len(shown) > 60:                             # a name with the instructions in it: those go below
                cut = re.split(r", | - |\. |: ", shown, maxsplit=1)[0]
                if 10 <= len(cut) < len(shown):
                    note, shown = note if len(note) >= len(c["name"]) else clean(c["name"] + ". " + note).rstrip(". ") , cut
            base = dict(id=db_id(folder["name"], c["name"], c["ops"]), name=prefix + shown,
                        note=note, cat=page, group="",
                        status="untested", mode="both" if len(r["keys"]) <= 1 else "always", ops=[],
                        keys=r["keys"], reason="", file="", on=False, patch=[], env="", option=shown)
            if re.search(r"anti-?piracy", c["name"], re.I):
                r = dict(r, kind="blocked", why="piracy")
            elif re.search(r"wfc|https|wi-?fi connection", c["name"], re.I) and r["kind"] != "live":
                r = dict(r, kind="blocked", why="wfc")
            if r["kind"] == "blocked":
                made.append(dict(base, kind="blocked", status="blocked", reason=REASONS[r["why"]], mode=""))
            elif r["kind"] == "live":
                made.append(dict(base, kind="live", ops=c["ops"]))
            else:
                many = len(r["variants"]) > 1
                for i, (label, patch) in enumerate(r["variants"]):
                    e = dict(base, kind="code", mode="", patch=patch, keys=[])
                    if many:
                        e.update(id=f"{base['id']}:{i}", name=f"{base['name']} ({label or i + 1})",
                                 option=f"{shown} ({label or i + 1})")
                    if moved:
                        e["note"] = clean(e["note"] + " (Listed with the USA version's addresses; moved to where your ROM has these instructions.)")
                    if r.get("held"):
                        held = " / ".join(k for k in (key_text(k) for k in r["keys"]) if k)
                        first = e["note"] + ("" if not e["note"] or e["note"].rstrip()[-1] in ".!?)" else ".")
                        e["note"] = clean(first + f" On a DS you hold or press {held or 'a button'} for this; here it is simply on.")
                    made.append(e)
        # the list has some codes twice (in two folders): once is enough
        for e in list(made):
            sig = ("live", tuple(e["ops"])) if e["kind"] == "live" else ("code", tuple(e["patch"])) if e["kind"] == "code" else None
            if sig in seen_sigs and not folder["one"]:
                made.remove(e)
            elif sig:
                seen_sigs.add(sig)
        # a file that does exactly the same takes the code's place (its name, its switch, "tried out")
        for e in made:
            twin = by_sig.get(("live", tuple(e["ops"]))) if e["kind"] == "live" else \
                by_sig.get(("code", tuple(e["patch"]))) if e["kind"] == "code" else None
            if twin is not None and twin["id"] not in used:
                used.add(twin["id"])
                e.update(id=twin["id"], name=twin["name"], note=twin["note"] or e["note"], status="tested",
                         mode=twin["mode"], file=twin["file"], on=twin["on"])
        choice = [e for e in made if e["kind"] in ("live", "code")]
        if folder["one"] and len(choice) > 1 and len({e["kind"] for e in choice}) == 1:
            gid = "group:" + f"{zlib.crc32(folder['name'].encode('utf-8')) & 0xFFFFFFFF:08x}"
            groups.append(dict(id=gid, cat=page, title=strip_keys(folder["name"]), note=folder["note"], kind=choice[0]["kind"]))
            for e in choice:
                e["group"] = gid
        entries += made

    # ---- the files no database code matched
    for e in files:
        if e["id"] not in used:
            e["cat"] = e["cat"] or "My cheats"
            e["option"] = e["name"]
            entries.append(e)

    # ---- code mods that change the same instruction differently can't be on together: one choice
    code = [e for e in entries if e["kind"] == "code"]
    parent = {e["id"]: e["id"] for e in code}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    where = {}
    for e in code:
        for name, a, w in e["patch"]:
            for other, ow in where.get((name, a), []):
                if ow != w:
                    parent[find(e["id"])] = find(other)
            where.setdefault((name, a), []).append((e["id"], w))
    sets = {}
    for e in code:
        sets.setdefault(find(e["id"]), []).append(e)
    for members in sets.values():
        if len(members) < 2:
            continue
        gids = {e["group"] for e in members if e["group"]}
        if len(gids) == 1 and all(e["group"] for e in members):
            continue                                        # already one folder's choice
        if gids:
            gid = sorted(gids)[0]
            g = next(g for g in groups if g["id"] == gid)
        else:
            gid = "group:" + f"{zlib.crc32(members[0]['id'].encode('utf-8')) & 0xFFFFFFFF:08x}"
            names = [e["name"] for e in members]
            common = os.path.commonprefix(names).rstrip(" x(-:")
            g = dict(id=gid, cat=members[0]["cat"], title=common if len(common) >= 6 else " / ".join(names[:3]), note="", kind="code")
            groups.append(g)
        for e in members:
            if not e["group"]:
                e["option"] = e["name"]
            e["group"], e["cat"] = gid, g["cat"]
    for old in [g for g in groups if not any(e["group"] == g["id"] for e in entries)]:
        groups.remove(old)

    # ---- how the game is started
    for lid, name, env, note in LAUNCH:
        entries.append(dict(id=lid, name=name, note=note, cat="Speed & comfort", group="", kind="launch", status="tested",
                            mode="", ops=[], keys=[], reason="", file="", on=False, patch=[], env=env, option=name))
    return info, entries, groups


def read_state(root):
    """What is switched on in the cheat menu: mods/menu-state.txt, lines of "<live|code|launch> <id>"."""
    state = {"live": set(), "code": set(), "launch": set()}
    try:
        for line in open(os.path.join(root, "mods", "menu-state.txt"), encoding="utf-8-sig"):
            p = line.split(None, 1)
            if len(p) == 2 and p[0] in state:
                state[p[0]].add(p[1].strip())
    except OSError:
        pass
    return state


def write(root, info, entries, groups):
    def kv(what, **f):
        return what + "\t" + "\t".join(f"{k}={clean(v)}" for k, v in f.items() if v not in ("", None))

    pages = []
    for e in entries:
        if e["cat"] not in pages:
            pages.append(e["cat"])
    pages.sort(key=lambda p: (PAGE_ORDER.index(p) if p in PAGE_ORDER else len(PAGE_ORDER) - 1.5, p))
    lines = [kv("info", **info)]
    lines += [kv("page", title=p) for p in pages]
    lines += [kv("group", id=g["id"], cat=g["cat"], title=g["title"], note=g["note"], kind=g["kind"]) for g in groups]
    for e in entries:
        lines.append(kv(
            "entry", id=e["id"], cat=e["cat"], group=e["group"], kind=e["kind"], status=e["status"], name=e["name"],
            option=e.get("option", ""), note=e["note"], reason=e["reason"], mode=e["mode"],
            keys=" / ".join(k for k in (key_text(k) for k in e["keys"]) if k), combos=str(len(e["keys"])) if e["keys"] else "",
            file=e["file"], on="1" if e["on"] else "", env=e["env"],
            ops=",".join(f"{a:08X}:{b:08X}" for a, b in e["ops"]),
            patch=",".join(f"{n}:{a:08x}:{w:08x}" for n, a, w in e["patch"])))
    out = os.path.join(root, "mods", "bin", "catalog.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    text = "\n".join(lines) + "\n"
    try:
        if open(out, encoding="utf-8", newline="").read() == text:
            return out
    except OSError:
        pass
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.isfile(os.path.join(root, "build", "recomp", "dispatch_table.c")):
        print("   The game hasn't been built yet (no build\\recomp): build it once, then run this again.")
        return 1
    info, entries, groups = build(root)
    write(root, info, entries, groups)
    n = {k: sum(1 for e in entries if e["kind"] == k) for k in ("live", "code", "blocked", "launch")}
    print(f"   Cheat list: {n['live']} live, {n['code']} built into the game, {n['blocked']} that can't work here"
          + ("" if info["database"] else f"  (no mods\\database\\{info['game']}.txt: only your own files)"))
    if "--report" in sys.argv:
        for e in entries:
            what = e["reason"] if e["kind"] == "blocked" else \
                " ".join(f"{n}:{a:08x}={w:08x}" for n, a, w in e["patch"]) if e["kind"] == "code" else f"{len(e['ops'])} lines"
            print(f"{e['kind']:8}{e['status']:9}{e['cat'][:16]:17}{('*' if e['group'] else ' ')}{e['name'][:58]:59}{what[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
