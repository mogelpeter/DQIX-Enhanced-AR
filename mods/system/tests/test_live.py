"""Headless run of the built game on a copy of the save, with cheats sent through the mailbox.
   test_live.py <project root> <work dir> [frames]"""
import mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
frames = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
os.makedirs(work, exist_ok=True)
for f in os.listdir(work):
    if f.endswith(".bin") or f.endswith(".log"):
        os.remove(os.path.join(work, f))
shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(work, "test.sav"))
env = dict(os.environ)
env.pop("NoDefaultCurrentDirectoryInExePath", None)
d1, d2 = frames * 2 // 3, frames - 20
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_RAMDUMP=f".,{d1},{d2}", DQIX_INPUT=f"{d1 + 200}:SELECT:40")
exe = os.path.join(root, "game", "dqix.exe")
log = open(os.path.join(work, "run.log"), "wb")
t0 = time.time()
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"],
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
    print("FAIL: no mailbox (is the mods' part in the game?)"); p.kill(); sys.exit(1)
print("mailbox version", struct.unpack_from("<I", box, 4)[0])


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


while u(28) < 30 and p.poll() is None:
    time.sleep(0.005)
print("sending at frame", u(28), "gen", u(16))
T = 0x02340000                                                                       # a part of RAM the game never uses (was text: the "before SELECT" check failed for that)
send(2, 1, [(0x020F6D48, 0x0098967F)])                                            # SET: gold, every frame
send(2, 2, [(0x94000130, 0xFFFB0000), (T, 0x11111111), (0xD2000000, 0)])            # SET: only while SELECT is held
send(1, None, [(0x94000130, 0xFDFF0000), (T + 4, 0x22222222), (0xD2000000, 0)])     # RUN: its key counts as held
send(1, None, [(0xC0000000, 0xFFFFFFFF), (T + 8, 0x33333333), (0xD2000000, 0)])     # RUN: an endless loop must not freeze the game
send(2, 3, [(T + 12, 0x44444444)])
send(3, 3, [])                                                                    # CLEAR 3 again
last, stalled = -1, time.time()
while p.poll() is None:
    time.sleep(0.5)
    f = u(28)
    if f != last:
        last, stalled = f, time.time()
    elif time.time() - stalled > 20:                 # no frame for 20 s in a row (the last frames are slow: dumps, exit)
        print("FAIL: the game stopped at frame", f); p.kill(); break
    if time.time() - t0 > 600:
        print("FAIL: timeout at frame", f); p.kill(); break
print("exit code", p.returncode, "frames", u(28), "messages done", u(24), "seconds %.1f" % (time.time() - t0))
log.close()


def ram(frame, addr, n=4):
    with open(os.path.join(work, f"ram{frame:06d}.bin"), "rb") as f:
        f.seek(addr & 0x3FFFFF)
        return int.from_bytes(f.read(n), "little")


ok = True
def check(what, got, want):
    global ok
    good = got == want
    ok &= good
    print(("ok   " if good else "FAIL ") + what + f": {got:#x}" + ("" if good else f" (expected {want:#x})"))

try:
    check("gold at dump 1", ram(d1, 0x020F6D48), 0x0098967F)
    check("gold at dump 2", ram(d2, 0x020F6D48), 0x0098967F)
    check("SELECT code before SELECT", ram(d1, T), 0)
    check("SELECT code after SELECT", ram(d2, T), 0x11111111)
    check("fired once, key counted as held", ram(d1, T + 4), 0x22222222)
    check("endless loop wrote once and let go", ram(d1, T + 8), 0x33333333)
    check("cleared cheat stays", ram(d2, T + 12), 0x44444444)
except OSError as e:
    ok = False
    print("FAIL: no RAM dump:", e)
txt = open(os.path.join(work, "run.log"), "rb").read().decode("utf-8", "replace")
bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unknown", "unhandled", "crash", "out of sync"))]
print("log lines:", len(txt.splitlines()), "| suspicious:", len(bad))
for l in bad[:15]:
    print("   ", l[:200])
print("RESULT:", "PASS" if ok and p.returncode == 0 else "FAIL")
