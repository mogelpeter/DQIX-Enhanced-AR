"""An independent Python port of ar_engine.h (the Action Replay engine the game runs), for the tests.

    predict(ops, ram, keys=None) -> the writes [(address, size, value)] one pass of the code makes, applied to ram

keys=None: every button check passes (as if all were held). keys = a KEYINPUT-order bit mask (A=1, B=2, SELECT=4,
START=8, RIGHT, LEFT, UP, DOWN, R=0x100, L=0x200, X=0x400, Y=0x800): only those are held."""

KEYS = dict(A=1, B=2, SELECT=4, START=8, RIGHT=16, LEFT=32, UP=64, DOWN=128, R=256, L=512, X=1024, Y=2048)


def key_mask(text):
    """"A+L" -> 0x201"""
    m = 0
    for k in text.split("+"):
        m |= KEYS[k.strip().upper()]
    return m


def predict(ops, ram, keys=None):
    writes = []

    def isram(a): return (a >> 24) == 0x02
    def rd(a, n):
        return int.from_bytes(ram[a & 0x3FFFFF:(a & 0x3FFFFF) + n], "little") if isram(a) else 0
    def wr(a, n, v):
        if isram(a):
            writes.append((a, n, v & ((1 << 8 * n) - 1)))
            ram[a & 0x3FFFFF:(a & 0x3FFFFF) + n] = (v & ((1 << 8 * n) - 1)).to_bytes(n, "little")
    def keyreg(a): return a == 0x04000130 or a == 0x04000136 or (a & 0x0FFFFFFF) == 0x027FFFA8
    def keyval(a):                                  # the button registers: a bit is 0 while the button is held
        return (~keys & 0x3FF) if a == 0x04000130 else (~(keys >> 10) & 0x3) if a == 0x04000136 else (~keys & 0xFFF)

    offset = data = 0; budget = 400000; skip = 0; ls = -1; ll = 0; lskip = 0; pc = 0; n = len(ops)
    while pc < n:
        a, b = ops[pc]; t = a >> 28; top = a >> 24; addr = a & 0x0FFFFFFF
        budget -= 1
        if budget <= 0:
            break
        if skip:
            if 3 <= t <= 0xA: skip += 1
            elif top == 0xD0: skip -= 1
            elif top in (0xD1, 0xD2):
                skip = 0
                if top == 0xD2 and ls < 0: offset = data = 0
                if ls >= 0:
                    if ll > 0: ll -= 1; skip = lskip; pc = ls; pc += 1; continue
                    ls = -1
                    if top == 0xD2: offset = data = 0
            elif t == 0xE: pc += (b + 7) // 8
            pc += 1; continue
        if t <= 2 or 3 <= t <= 0xA or t == 0xB:
            if t <= 2 or t == 0xB: addr = (addr + offset) & 0xFFFFFFFF     # B: offset = word at [address + offset]
            elif addr == 0: addr = offset
        if t == 0: wr(addr, 4, b)
        elif t == 1: wr(addr, 2, b)
        elif t == 2: wr(addr, 1, b)
        elif 3 <= t <= 6:
            if not keyreg(addr) or keys is not None:
                v = keyval(addr) if keyreg(addr) else rd(addr, 4); ok = (b > v, b < v, b == v, b != v)[t - 3]
                if not ok: skip = 1
        elif 7 <= t <= 0xA:
            if not keyreg(addr) or keys is not None:
                v = (keyval(addr) if keyreg(addr) else rd(addr, 2)) & ~(b >> 16) & 0xFFFF; y = b & 0xFFFF
                ok = (y > v, y < v, y == v, y != v)[t - 7]
                if not ok: skip = 1
        elif t == 0xB: offset = rd(addr, 4)
        elif t == 0xC:
            if top == 0xC0: ls, ll, lskip = pc, b, 0
        elif t == 0xD:
            if top in (0xD1, 0xD2):
                if ls >= 0:
                    if ll > 0: ll -= 1; pc = ls + 1; continue
                    ls = -1
                if top == 0xD2: offset = data = 0
            elif top == 0xD3: offset = b
            elif top == 0xD4: data = (data + b) & 0xFFFFFFFF
            elif top == 0xD5: data = b
            elif top == 0xD6: wr(b + offset, 4, data); offset += 4
            elif top == 0xD7: wr(b + offset, 2, data); offset += 2
            elif top == 0xD8: wr(b + offset, 1, data); offset += 1
            elif top == 0xD9: data = rd(b + offset, 4)
            elif top == 0xDA: data = rd(b + offset, 2)
            elif top == 0xDB: data = rd(b + offset, 1)
            elif top == 0xDC: offset += b
        elif t == 0xE:
            dst = addr + offset; i = 0; l = pc + 1
            while l < n and i < b:
                for w in ops[l]:
                    for s in range(4):
                        if i < b: wr(dst + i, 1, (w >> 8 * s) & 0xFF); i += 1
                l += 1
            pc += (b + 7) // 8
        elif t == 0xF:
            for i in range(b): wr(addr + i, 1, rd(offset + i, 1))
        pc += 1
    return writes
