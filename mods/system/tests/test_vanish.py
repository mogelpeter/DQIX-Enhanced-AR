"""Headless run: the cheat "Vanish" is switched on through the mailbox, the buttons L+R+SELECT are pressed twice (held for
a few frames each time): vanish must go on at the first press and off at the second (once per press, not once per frame),
and a press before the cheat is on must do nothing.
   test_vanish.py <project root> <work dir>"""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
os.makedirs(work, exist_ok=True)
for f in os.listdir(work):
    if f.endswith((".bin", ".log")):
        os.remove(os.path.join(work, f))
shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(work, "test.sav"))
env = dict(os.environ)
env.pop("NoDefaultCurrentDirectoryInExePath", None)
FRAMES = 1500
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_MODLOG="1",
           DQIX_INPUT="300:L+R+SELECT:6;700:L+R+SELECT:6;900:L+R+SELECT:30;1100:L+R+SELECT:6")
exe = os.path.join(root, "game", "dqix.exe")
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
    print("FAIL: no mailbox"); p.kill(); sys.exit(1)


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


while u(28) < 500 and p.poll() is None:                    # after the first press (frame 300), before the second
    time.sleep(0.005)
send(2, 7, [(0x02F5A5A4, 1)])                              # SET: the cheat "Vanish" is on (the switch)
while u(28) < 1000 and p.poll() is None:
    time.sleep(0.005)
send(3, 7, [])                                             # CLEAR: switched off again
p.wait(timeout=600)
out = open(os.path.join(work, "run.log"), encoding="utf-8", errors="replace").read()
lines = [l.strip() for l in out.splitlines() if l.startswith("mod: vanish")]
print("\n".join(lines))
ok = [l.split(" at")[0] for l in lines] == ["mod: vanish on", "mod: vanish off"]
# 700: first press with the cheat on -> on, 900 (held 30 frames): -> off once; 1100 after CLEAR: nothing
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
