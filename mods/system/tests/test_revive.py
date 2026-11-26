"""Revive (mods/system/src/runtime/mod_cheats.c, MC_SWITCH_REVIVE): a fallen party member (HP 0) comes back, headless, in a real game. EU and USA alike.

   test_revive.py <project root> <work dir>          (TEST_SAVE = a party of at least 2 in a dungeon)

Two parts, from the same run:
  1. in the field (frame 3000): member 2's HP (+0x30) is set to 0, then the catalog cheat "Revive fallen party members" (file:cheats/revive.txt) is sent:
     the HP must be what it was (the game saw him with that HP), member 3 must be untouched.
  2. in a forced battle (DQIX_MOD_FORCE=3, frame 5000): member 2's HP now (+0x58) is set to 0, then the battle window's button "Revive" of member 2
     (live:battle:p2:revive) is sent: +0x58 must be his maximum (+0x5C). Member 3's HP now is lowered to 5 and must stay 5 (the button only revives).
Prints RESULT: PASS / FAIL."""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32
B = 0x02000000
PARTY0, STRIDE = 0x020F54B4, 0x964
P2, P3 = PARTY0 - STRIDE, PARTY0 - 2 * STRIDE
F1, AT = 3000, 5000
dumps = [F1 - 20, F1 + 150, AT - 10, AT + 250]

entries = {}
for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
    if line.startswith("entry\t"):
        d = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
        entries[d["id"]] = d


def ops_of(eid):
    d = entries.get(eid)
    if not d or not d.get("ops"):
        print("RESULT: FAIL (no catalog entry %s)" % eid); sys.exit(1)
    return [tuple(int(v, 16) for v in o.split(":")) for o in d["ops"].split(",")]


d = os.path.join(work, "revive"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
shutil.copy(os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_MOD_FORCE="3",
           DQIX_MODLOG="1", DQIX_INPUT=inp, DQIX_RAMDUMP=".," + ",".join(map(str, dumps)))
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(AT + 300), "1", "test.sav"],
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


W16 = 0x10000000
at(F1, lambda: send(1, None, [(W16 | P2 + 0x30, 0)]))
at(F1 + 60, lambda: send(1, None, ops_of("file:cheats/revive.txt")))
at(AT, lambda: send(1, None, [(W16 | P2 + 0x58, 0), (W16 | P3 + 0x58, 5)]))
at(AT + 100, lambda: send(1, None, ops_of("live:battle:p2:revive")))
p.wait(timeout=900); log.close()


def ram(frame, addr, n=2):
    data = open(os.path.join(d, "ram%06d.bin" % frame), "rb").read()
    return int.from_bytes(data[addr - B:addr - B + n], "little")


problems = []
hp0 = ram(F1 - 20, P2 + 0x30)
expect = lambda c, t: problems.append(t) if not c else None
expect(hp0 > 0, "member 2 has no HP in the save (a party of at least 2 is needed)")
expect(ram(F1 + 150, P2 + 0x30) == hp0, "field: member 2's HP must be %d again, is %d" % (hp0, ram(F1 + 150, P2 + 0x30)))
expect(ram(F1 + 150, P3 + 0x30) == ram(F1 - 20, P3 + 0x30), "field: member 3 must not change")
mx = ram(AT - 10, P2 + 0x5C)
expect(ram(AT - 10, PARTY0 + 0x5C) > 0, "no battle was reached (TEST_SAVE = the dungeon save)")
expect(ram(AT + 250, P2 + 0x58) == mx and mx > 0, "battle: member 2's HP now must be his maximum %d, is %d" % (mx, ram(AT + 250, P2 + 0x58)))
expect(ram(AT + 250, P3 + 0x58) == 5, "battle: member 3 (alive, HP 5) must stay at 5, is %d" % ram(AT + 250, P3 + 0x58))
txt = open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()
expect("mod: revive party member 2" in txt, "the log has no revive line")
print("field HP %d -> %d | battle max %d, HP now after revive %d, member 3 %d" % (hp0, ram(F1 + 150, P2 + 0x30), mx, ram(AT + 250, P2 + 0x58), ram(AT + 250, P3 + 0x58)))
print("RESULT: PASS" if not problems else "RESULT: FAIL (" + "; ".join(problems) + ")")
sys.exit(0 if not problems else 1)
