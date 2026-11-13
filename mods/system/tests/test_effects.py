"""Per-cheat effect check: each live cheat is fired alone ("Once", all keys held) into a headless game and the RAM it
   leaves is compared with what an independent Python copy of the Action Replay engine predicts for that moment.
   test_effects.py <project root> <work dir> [untested|all] [first] [count] [input]

   A cheat PASSES when every byte its code writes (and that would change the value) is in the dump taken right after.
   NOCHANGE = the code writes nothing in this game state (its condition is not met at the boot menu / field): not a
   failure, but not proof either. Cheats that touch the same address as another cheat in the run are checked
   with the later writer only. Prints RESULT: PASS / FAIL and writes verified ids to <work>/effects.txt."""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
which = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "untested"
first = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 0
count = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 55
inp = sys.argv[6] if len(sys.argv) > 6 else ""
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
os.makedirs(work, exist_ok=True)
RING, AT = 8192, 32


def catalog():
    out = []
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if not line.startswith("entry\t"):
            continue
        d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
        if d.get("kind") == "live" and d.get("ops") and (which == "all" or d.get("status") == "untested"):
            d["ops"] = [tuple(int(x, 16) for x in o.split(":")) for o in d["ops"].split(",")]
            out.append(d)
    return out


# ---- an independent port of ar_engine.h (keys = all held): returns the writes it would make [(addr, size, value)]
def predict(ops, ram):
    writes = []

    def isram(a): return (a >> 24) == 0x02
    def rd(a, n):
        return int.from_bytes(ram[a & 0x3FFFFF:(a & 0x3FFFFF) + n], "little") if isram(a) else 0
    def wr(a, n, v):
        if isram(a):
            writes.append((a, n, v & ((1 << 8 * n) - 1)))
            ram[a & 0x3FFFFF:(a & 0x3FFFFF) + n] = (v & ((1 << 8 * n) - 1)).to_bytes(n, "little")
    def keyreg(a): return a == 0x04000130 or a == 0x04000136 or (a & 0x0FFFFFFF) == 0x027FFFA8

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
            if t <= 2: addr = (addr + offset) & 0xFFFFFFFF
            elif addr == 0: addr = offset
        if t == 0: wr(addr, 4, b)
        elif t == 1: wr(addr, 2, b)
        elif t == 2: wr(addr, 1, b)
        elif 3 <= t <= 6:
            if not keyreg(addr):
                v = rd(addr, 4); ok = (b > v, b < v, b == v, b != v)[t - 3]
                if not ok: skip = 1
        elif 7 <= t <= 0xA:
            if not keyreg(addr):
                v = rd(addr, 2) & ~(b >> 16) & 0xFFFF; y = b & 0xFFFF
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


entries = catalog()[first:first + count]
print("cheats in this run:", len(entries))


def words(e): return 1 + 4 * len(e["ops"])


START = 40
slots, f = [], START
for e in entries:
    slots.append((f, f + words(e) + 30))     # send at f, dump at f+words+30
    f += words(e) + 60
frames = f + 40
dumps = [s[1] for s in slots]
d = os.path.join(work, "effects"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_PLAYER_NAME="fx",
           DQIX_RAMDUMP=".," + ",".join(map(str, [START - 5] + dumps)))
if inp:
    env["DQIX_INPUT"] = inp
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"],
                     cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
box = None
for _ in range(400):
    try:
        b = mmap.mmap(-1, AT + RING * 2, tagname=f"Local\\dqix-mod-cheats-{p.pid}", access=mmap.ACCESS_WRITE)
        if struct.unpack_from("<I", b, 0)[0] == 0x43584451:
            box = b; break
        b.close()
    except OSError:
        pass
    time.sleep(0.05)
if box is None:
    print("FAIL: no mailbox"); p.kill(); sys.exit(1)
u = lambda off: struct.unpack_from("<I", box, off)[0]


def send(typ, cid, ops):
    ws = ([cid] if cid is not None else [])
    for a, b in ops:
        ws += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
    msg = [typ << 12 | len(ws)] + ws
    w = u(8)
    while w - u(12) + len(msg) > RING - 8:
        time.sleep(0.01)
    for x in msg:
        struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
    struct.pack_into("<I", box, 8, w)


for (fs, _), e in zip(slots, entries):
    while u(28) < fs and p.poll() is None:
        time.sleep(0.005)
    send(1, None, e["ops"])
while p.poll() is None and u(28) < frames - 5:
    time.sleep(0.2)
p.wait(timeout=600); log.close()
print("exit code", p.returncode, "| sent", len(entries), "carried out", "-")

ram0 = open(os.path.join(d, "ram%06d.bin" % (START - 5)), "rb").read()
cur = bytearray(ram0)
later = {}                                   # addr -> index of the last cheat writing it, to skip clashes
res, ok = [], True
preds = []
for k, e in enumerate(entries):
    w = predict(e["ops"], bytearray(cur))
    preds.append(w)
    for a, n, v in w:
        for i in range(n): later[(a & 0x3FFFFF) + i] = k
    try:
        cur = bytearray(open(os.path.join(d, "ram%06d.bin" % dumps[k]), "rb").read())
    except OSError:
        print("no dump for", e["name"]); ok = False; preds[-1] = None
# re-run with the true previous state for each cheat
prev = bytearray(ram0)
for k, e in enumerate(entries):
    try:
        now = open(os.path.join(d, "ram%06d.bin" % dumps[k]), "rb").read()
    except OSError:
        continue
    w = predict(e["ops"], bytearray(prev))
    # final value per byte; only bytes that change and that no later cheat writes
    want = {}
    for a, n, v in w:
        for i, byte in enumerate(v.to_bytes(n, "little")):
            want[(a & 0x3FFFFF) + i] = byte
    want = {a: b for a, b in want.items() if prev[a] != b and later.get(a) == k}
    if any((a & ~0xF) == 0x02F5A5A0 or 0x02F60000 <= (a & 0x0FFFFFFF) < 0x02F70000 for a, b in e["ops"]):
        status = "NOCHANGE(SWITCH address (02F5A5xx / 02F6xxxx live code mod): handled by mod_cheats.c, see test_noflee / test_vanish / test_livepatch)"
    elif not w:
        status = "NOCHANGE(no write: condition not met here)"
    elif not want:
        status = "NOCHANGE(already that value / shared address)"
    else:
        bad = [a for a, b in want.items() if now[a] != b]
        # bytes the game itself keeps changing (audio buffers at the boot menu...) say nothing about the cheat
        seen = {}
        for j in range(k + 1, len(dumps)):
            try:
                dd = open(os.path.join(d, "ram%06d.bin" % dumps[j]), "rb").read()
            except OSError:
                break
            for a in bad:
                seen.setdefault(a, set()).add(dd[a])
        vol = [a for a in bad if len(seen.get(a, ())) >= 3]
        if bad and len(vol) == len(bad):
            res.append((e["id"], e["name"], "NOCHANGE(VOLATILE: the game rewrites those bytes by itself here)"))
            prev = bytearray(now)
            continue
        status = "PASS" if not bad else "FAIL %d/%d bytes not in RAM, first %08x want %02x got %02x" % (len(bad), len(want), 0x02000000 + bad[0], want[bad[0]], now[bad[0]])
        if bad:
            ok = False
    res.append((e["id"], e["name"], status))
    prev = bytearray(now)
for i, n, s in res:
    print("%-5s %-44s %s" % (s.split("(")[0].split(" ")[0], n[:44], s if s.startswith("FAIL") or "(" in s else ""))
good = [i for i, n, s in res if s == "PASS"]
open(os.path.join(work, "effects.txt"), "a", encoding="utf-8").write("".join(i + "\n" for i in good))
txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unhandled", "crash"))]
print("PASS %d | NOCHANGE %d | FAIL %d | suspicious log lines %d" % (len(good), sum(s.startswith("NOCHANGE") for _, _, s in res), sum(s.startswith("FAIL") for _, _, s in res), len(bad)))
ok &= not bad and p.returncode == 0
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
