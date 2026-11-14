"""Headless run: switching a Fun cheat off puts the game back (mod_cheats.c SET_UNDO, catalog.py UNDO).
The hero stands in the field (TEST_SAVE: a save outside a battle; the backup dqix-20261113-170934.sav works). Through the
mailbox, the way the Cheats window sends them (type 5 when the catalog says undo=1):
   2000 Big Head on, 2400 off      the head's scale words ([020F33E0] + 0x3D8) must be what they were at 1990 again by 2450
   2700 Invisible Party Members on, 3100 off   the party members' heights it lowers must not stay lowered (3150)
Pictures (DQIX_DUMP every 100 frames) in <work> for a look at the party; RAM dumps at 1990, 2300, 2450, 2690, 3000, 3150.
   test_undo_fun.py <project root> <work dir>"""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
save = os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav")
FRAMES = 3400
RING, AT = 8192, 32


def catalog_entry(name):
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        f = dict(x.split("=", 1) for x in p[1:] if "=" in x)
        if p[0] == "entry" and (f.get("option") == name or f.get("name") == name):
            ops = [tuple(int(v, 16) for v in o.split(":")) for o in f.get("ops", "").split(",") if o]
            return ops, f.get("undo") == "1"
    return None, False


head, head_undo = catalog_entry("Big Head")
hide, hide_undo = catalog_entry("Invisible Party Members")
if not head or not hide:
    print("RESULT: FAIL (Big Head / Invisible Party Members not in the catalog)"); sys.exit(1)
if not (head_undo and hide_undo):
    print("RESULT: FAIL (the catalog doesn't mark them undo=1)"); sys.exit(1)

shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
shutil.copy(save, os.path.join(work, "test.sav"))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
           DQIX_RAMDUMP=".,1990,2300,2450,2690,3000,3150", DQIX_DUMP=work + ",100",
           DQIX_INPUT="700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 1460, 90)))      # load the quick save, into the field
p = subprocess.Popen([os.path.join(root, "game", "dqix.exe"), os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"),
                      str(FRAMES), "1", "test.sav"], cwd=work, env=env, stdout=open(os.path.join(work, "run.log"), "wb"), stderr=subprocess.STDOUT)
box = None
for _ in range(200):
    try:
        box = mmap.mmap(-1, AT + RING * 2, tagname=f"Local\\dqix-mod-cheats-{p.pid}", access=mmap.ACCESS_WRITE)
        if struct.unpack_from("<I", box, 0)[0] == 0x43584451:
            break
        box.close(); box = None
    except OSError:
        pass
    time.sleep(0.05)
if box is None:
    print("RESULT: FAIL (no mailbox)"); p.kill(); sys.exit(1)


def u(off):
    return struct.unpack_from("<I", box, off)[0]


def send(typ, cid, ops):
    words = [cid]
    for a, b in ops:
        words += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
    w = u(8)
    for x in [typ << 12 | len(words)] + words:
        struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
    struct.pack_into("<I", box, 8, w)


def at(frame):
    while u(28) < frame and p.poll() is None:
        time.sleep(0.005)


at(2000); send(5, 1, head)
at(2400); send(3, 1, [])
at(2700); send(5, 2, hide)
at(3100); send(3, 2, [])
p.wait(timeout=600)


def ram(frame, addr, n=4):
    with open(os.path.join(work, f"ram{frame:06d}.bin"), "rb") as f:
        f.seek(addr & 0x3FFFFF)
        return int.from_bytes(f.read(n), "little")


ok = True
try:
    hero = ram(1990, 0x020F33E0)
    before, on, after = (ram(fr, hero + 0x3D8, 8) & 0xFFFFFFFFFFFF for fr in (1990, 2300, 2450))
    print(f"hero object {hero:08x}: head scale before {before:012x}, on {on:012x}, after off {after:012x}")
    ok = hero >> 24 == 0x02 and on != before and after == before
    # Invisible Party Members: party members' heights = the hero's - 0xF00000 (under the floor) while [020F1F7C] = 1
    for a in (0x022CD2E8, 0x022DE9A4, 0x022F0060, 0x022CD2D4, 0x022DE990, 0x022F004C):
        b, o, f = (ram(fr, a) for fr in (2690, 3000, 3150))
        lowered = o != b
        print(f"  {a:08x}: before {b:08x}, on {o:08x}, after off {f:08x}" + ("" if lowered else "  (not changed by the cheat here)"))
        if lowered and f == o:
            ok = False
except OSError as e:
    print("no RAM dump:", e); ok = False
print("pictures:", work)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
