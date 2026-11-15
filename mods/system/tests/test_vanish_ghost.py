"""Headless run: "Vanish" makes the party a ghost (vanish.c fades the field objects with the game's own Object3D::TransitionInheritedAlpha).
The cheat is switched on through the mailbox at frame 3500 (the hero stands in the field by then), L+R+SELECT is pressed at 3600 (vanish)
and again at 4000 (show up). Checks the log ("mod: ghost 1" after the first press, "mod: ghost 0" after the second) and writes pictures
to <work>/shots (frames 3590, 3800, 4150): the hero should be see-through in the middle one only.
Needs TEST_SAVE = a save with the hero in the field or a dungeon.
   test_vanish_ghost.py <project root> <work dir>"""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
exe = os.environ.get("TEST_EXE") or os.path.join(root, "game", "dqix.exe")
save = os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav")
RING, AT = 8192, 32
d = os.path.join(work, "shots")
shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
shutil.copy(save, os.path.join(d, "test.sav"))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90)) + ";3600:L+R+SELECT:6;3700:B:6;3760:B:6;3820:B:6;4000:L+R+SELECT:6;4100:B:6;4160:B:6"
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
           DQIX_MODLOG="1", DQIX_INPUT=inp, DQIX_DUMP=d + ",1", DQIX_DUMP_AT=os.environ.get("TEST_AT", "3590,3640,3700,4150"))
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), "4400", "1", "test.sav"],
                     cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
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
while struct.unpack_from("<I", box, 28)[0] < 3500 and p.poll() is None:
    time.sleep(0.01)
a, b = 0x02F5A5A4, 0 if os.environ.get("TEST_NOCHEAT") else 1
msg = [2 << 12 | 5, 7, a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
w = struct.unpack_from("<I", box, 8)[0]
for x in msg:
    struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
struct.pack_into("<I", box, 8, w)
p.wait(timeout=900); log.close()
t = open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()
on, off = "mod: ghost 1 " in t, "mod: ghost 0 " in t
print("ghost on:", on, " ghost off again:", off, " pictures in", d)
print("RESULT:", "PASS" if on and off else "FAIL")
sys.exit(0 if on and off else 1)
