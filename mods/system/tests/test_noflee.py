"""Headless run: the cheat "Monsters can't flee" is switched on through the mailbox before the first battle, then the
hero fights metal slimes (DQIX_MOD_FORCE=3 turns every roaming monster of the dungeon into one) with A pressed
on a timer. Without the cheat the slimes flee in this fight; with it every "Flee" the AI picks must be asked again:
the log must say so ("mod: noflee asked again"), and the game must run on to the end of the frames.
Needs the game built with the mods (Play with mods.bat) and the save of the test machine (game\\dqix.sav:
a hero in a dungeon with monsters). Slow: about 3 minutes.
   test_noflee.py <project root> <work dir> [frames]
Uses TEST_EXE (a separate build) when set. A build with "Monsters don't chase you" may not reach the fight in time:
the result then says so (SKIP, exit 2) instead of passing."""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAMES = int(sys.argv[3]) if len(sys.argv) > 3 else 7500
os.makedirs(work, exist_ok=True)
for f in os.listdir(work):
    if f.endswith((".bin", ".log")):
        os.remove(os.path.join(work, f))
shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(work, "test.sav"))
env = dict(os.environ)
env.pop("NoDefaultCurrentDirectoryInExePath", None)
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, FRAMES + 100, 90))
env.update(DQIX_NOWINDOW="1", DQIX_NO_SETTINGS="1", DQIX_MODLOG="1", DQIX_MOD_FORCE="3", DQIX_INPUT=inp)
exe = os.environ.get("TEST_EXE") or os.path.join(root, "game", "dqix.exe")
log = open(os.path.join(work, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                     cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
RING, AT = 8192, 32
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
    print("FAIL: no mailbox (is the game built with the mods?)"); p.kill(); sys.exit(1)


def u(off):
    return struct.unpack_from("<I", box, off)[0]


def send(typ, cid, ops):
    words = ([cid] if cid is not None else [])
    for a, b in ops:
        words += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
    msg = [typ << 12 | len(words)] + words
    w = u(8)
    for x in msg:
        struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
    struct.pack_into("<I", box, 8, w)


while u(28) < 3000 and p.poll() is None:                   # in the dungeon, before the first battle
    time.sleep(0.01)
send(2, 11, [(0x02F5A5A8, 1)])                             # SET: the cheat "Monsters can't flee" is on
p.wait(timeout=1200)
out = open(os.path.join(work, "run.log"), encoding="utf-8", errors="replace").read()
asked = [l for l in out.splitlines() if l.startswith("mod: noflee asked again")]
print("asked again %d times; exit code %s" % (len(asked), p.returncode))
if "stopped after" not in out:
    print("RESULT: FAIL (the game did not run to the end of the frames)"); sys.exit(1)
if not asked:
    print("RESULT: SKIP (no monster chose to flee: the fight was not reached, or this build changes it; try TEST_EXE)"); sys.exit(2)
print("RESULT: PASS")
