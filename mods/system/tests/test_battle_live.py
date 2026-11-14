"""The live battle cheats (catalog entries "live:battle:<who>:<what>", the Battle cheats window) in a real battle, headless, Windows. EU and USA game alike.

   test_battle_live.py <project root> <work dir>

A battle is forced (DQIX_MOD_FORCE=3: every roamer a metal slime; TEST_SAVE = a party in a dungeon). The cheats' own ops are taken from the catalog and sent
through the mailbox the way the window does it; the RAM of the battle must show their effect:
   enemy 1 HP to 1, enemy 2 asleep (status byte), party member 2 high tension + Coup de Grace ready, member 1 HP and MP 9999, member 3 invincible flag,
   then member 2's HP is set to 3 and "HP and MP never go down" (member 2) is switched on: the code (R4 "HP never decrease") copies the current HP into
   the "actual" HP every frame, so the two must be equal afterwards.
Also checks the catalog: every entry that names a member (p2..p4) or an enemy (e1..e6) has its section, and the old R4 codes for the same bytes are gone.
Prints RESULT: PASS / FAIL."""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32
B = 0x02000000
PARTY0, STRIDE, ENEMY0, ESTRIDE = 0x020F54B4, 0x964, 0x022A4638, 0xA4

entries = {}
for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
    if line.startswith("entry\t"):
        d = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
        entries[d["id"]] = d
problems = []


def ops_of(eid):
    d = entries.get(eid)
    if not d or not d.get("ops"):
        problems.append("no catalog entry %s" % eid); return []
    return [tuple(int(v, 16) for v in o.split(":")) for o in d["ops"].split(",")]


for who in ("p1", "p2", "p3", "p4", "e1", "e6"):
    mine = [d for d in entries.values() if d.get("who") == who and d["cat"] == "Live battle"]
    if not mine:
        problems.append("no live battle entries for %s" % who)
    for d in mine:
        if not d.get("section"):
            problems.append("%s has no section" % d["id"])
old = [d["name"] for d in entries.values() if d["id"].startswith("db:") and d["kind"] == "live" and any(
    (int(o.split(":")[0], 16) & 0x0FFFFFFF) in (ENEMY0, 0x020F550C, 0x020F5510, 0x020F4BAC) for o in d.get("ops", "").split(",") if o)]
if old:
    problems.append("the database's own codes for the same bytes are still listed: %s" % old)

AT = 5000
dumps = [AT - 100, AT + 120, AT + 320]
d = os.path.join(work, "battle-live"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
shutil.copy(os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_MOD_FORCE="3",
           DQIX_INPUT=inp, DQIX_RAMDUMP=".," + ",".join(map(str, dumps)))
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(AT + 400), "1", "test.sav"],
                     cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
box = None
for _ in range(400):
    try:
        b = mmap.mmap(-1, MB + RING * 2, tagname=f"Local\\dqix-mod-cheats-{p.pid}", access=mmap.ACCESS_WRITE)
        if struct.unpack_from("<I", b, 0)[0] == 0x43584451:
            box = b; break
        b.close()
    except OSError:
        pass
    time.sleep(0.05)
if box is None:
    print("RESULT: FAIL (no mailbox: is the game built with the mods?)"); p.kill(); sys.exit(1)
u = lambda off: struct.unpack_from("<I", box, off)[0]


def send(typ, ident, ops):
    words = ([ident] if ident is not None else [])
    for a, v in ops:
        words += [a & 0xFFFF, a >> 16, v & 0xFFFF, v >> 16]
    msg = [typ << 12 | len(words)] + words
    w = u(8)
    for x in msg:
        struct.pack_into("<H", box, MB + (w % RING) * 2, x); w += 1
    struct.pack_into("<I", box, 8, w)


def at(frame, what):
    while u(28) < frame and p.poll() is None:
        time.sleep(0.005)
    what()


once = ops_of("live:battle:e1:hp1") + ops_of("live:battle:e2:sleep") + ops_of("live:battle:p2:tension") + ops_of("live:battle:p2:coup") \
    + ops_of("live:battle:p1:max") + ops_of("live:battle:p3:invincible")
at(AT - 60, lambda: send(1, None, once))
at(AT + 130, lambda: send(1, None, [(0x10000000 | PARTY0 - STRIDE + 0x5C, 3)]))                   # member 2's HP now: 3
at(AT + 190, lambda: send(2, 9, ops_of("live:battle:p2:keep")))                                   # "HP and MP never go down" (member 2)
p.wait(timeout=900); log.close()


def ram(frame, addr, n):
    data = open(os.path.join(d, "ram%06d.bin" % frame), "rb").read()
    return int.from_bytes(data[addr - B:addr - B + n], "little")


def expect(cond, text):
    if not cond:
        problems.append(text)


p2 = PARTY0 - STRIDE
f = AT + 120
expect(ram(dumps[0], PARTY0 + 0x58, 2) != 0, "no battle was reached (TEST_SAVE = the dungeon save)")
expect(ram(f, ENEMY0, 2) == 1, "enemy 1 HP must be 1, is %d" % ram(f, ENEMY0, 2))
expect(ram(f, ENEMY0 + ESTRIDE + 0x14, 1) & 0x10, "enemy 2 must be asleep (status byte %#x)" % ram(f, ENEMY0 + ESTRIDE + 0x14, 1))
expect(ram(f, p2 + 0x6F, 1) == 1 and ram(f, p2 + 0x7C, 1) == 4, "member 2 must have high tension (%d, %d)" % (ram(f, p2 + 0x6F, 1), ram(f, p2 + 0x7C, 1)))
expect(ram(f, p2 + 0x93, 1) == 0x98, "member 2 must have Coup de Grace ready (%#x)" % ram(f, p2 + 0x93, 1))
expect(ram(f, PARTY0 + 0x5C, 2) == 9999 and ram(f, PARTY0 + 0x5E, 2) == 9999, "member 1 HP and MP must be 9999")
expect(ram(f, PARTY0 - 2 * STRIDE + 0x70, 1) == 0x40, "member 3 must carry the invincible flag")
last = AT + 320
expect(ram(last, p2 + 0x5C, 2) == ram(last, p2 + 0x58, 2) == 3,
       "'never go down' must copy member 2's HP (3) into the actual HP: HP now %d, actual %d" % (ram(last, p2 + 0x5C, 2), ram(last, p2 + 0x58, 2)))
print("enemy1 HP", ram(f, ENEMY0, 2), "| member 2 tension", ram(f, p2 + 0x6F, 1), "| member 2 HP at the end", ram(last, p2 + 0x5C, 2), "/", ram(last, p2 + 0x58, 2))
print("RESULT: PASS" if not problems else "RESULT: FAIL (" + "; ".join(problems) + ")")
sys.exit(0 if not problems else 1)
