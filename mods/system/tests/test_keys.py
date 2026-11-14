"""A cheat that works with buttons, tested the way a player uses it: switched on for good, then the buttons are really
pressed in the game (not "all held" as in test_effects.py). Headless, Windows.

   test_keys.py <project root> <work dir> <cheat id> <keys>[,<keys>...] [frames]

   e.g. test_keys.py . work db:6fec10fd A+L,A+R 20     (hold A+L for 20 frames, then A+R for 20 frames)

Each phase holds its buttons for <frames> frames. The RAM before and after a phase is compared with what an independent
copy of the Action Replay engine (ar_port.py) does with exactly those buttons, frame by frame: every byte it predicts must
be in RAM (one frame more or less is allowed, the button may reach the engine a frame late). A phase whose code writes
nothing (its condition is not met in this game state) is reported as NOCHANGE, not as a pass.

Game state: TEST_SAVE (a save; default game\\dqix.sav), TEST_ENV ("K=V;K=V"), TEST_PRE ("frame:what:frames;..." extra
presses before the first phase, e.g. to open a menu), TEST_AT (frame of the first phase, default 3800: in the field with
the dungeon save of NOTES 2026-11-14), TEST_SHOT=n (a screen dump every n frames into <work>/keys, to see the state).
Prints RESULT: PASS / FAIL / NOCHANGE."""
import mmap, os, shutil, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ar_port import predict, key_mask

root, work, cid = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
phases = sys.argv[4].split(",")
N = int(sys.argv[5]) if len(sys.argv) > 5 else 20
AT = int(os.environ.get("TEST_AT") or 3800)
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32

entry = None
for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
    if line.startswith("entry\t"):
        d = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
        if d["id"] in cid.split("|") or (d.get("option") or d.get("name")) in cid.split("|"):     # an id, or (other ROM) the name
            entry = d
if not entry or not entry.get("ops"):
    print("RESULT: FAIL (no live cheat %s in the catalog)" % cid); sys.exit(1)
ops = [tuple(int(x, 16) for x in o.split(":")) for o in entry["ops"].split(",")]
print("cheat:", entry["name"], "| phases:", ", ".join(phases), "| %d frames each" % N, flush=True)

starts = [AT + i * (N + 60) for i in range(len(phases))]
dumps = []
for s in starts:
    dumps += [s - 2, s + N + 4]
frames = max(starts[-1] + N + 40, int(os.environ.get("TEST_END") or 0))      # TEST_END: run on (e.g. to reopen a menu)
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90))
if os.environ.get("TEST_PRE"):
    inp += ";" + os.environ["TEST_PRE"]
inp += ";" + ";".join("%d:%s:%d" % (s, k.strip(), N) for s, k in zip(starts, phases))

d = os.path.join(work, "keys"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
shutil.copy(os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
           DQIX_INPUT=inp, DQIX_RAMDUMP=".," + ",".join(map(str, dumps)))
if os.environ.get("TEST_SHOT"):                                # screen dumps every TEST_SHOT frames (f<frame>.ppm), to see the state
    env["DQIX_DUMP"] = d + "," + os.environ["TEST_SHOT"]
for kv in os.environ.get("TEST_ENV", "").split(";"):
    if "=" in kv:
        env[kv.split("=", 1)[0]] = kv.split("=", 1)[1]
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"],
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
words = [77]                                                    # SET: the cheat is on from now on (id 77)
for a, b in ops:
    words += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
msg = [2 << 12 | len(words)] + words
# a message reaches the game 16 bits per frame: send it early enough to be complete well before the first phase
while u(28) < AT - len(msg) - 120 and p.poll() is None:
    time.sleep(0.01)
w = u(8)
for x in msg:
    struct.pack_into("<H", box, MB + (w % RING) * 2, x); w += 1
struct.pack_into("<I", box, 8, w)
p.wait(timeout=900); log.close()

result = "PASS"
for i, keys in enumerate(phases):
    try:
        before = bytearray(open(os.path.join(d, "ram%06d.bin" % dumps[2 * i]), "rb").read())
        after = open(os.path.join(d, "ram%06d.bin" % dumps[2 * i + 1]), "rb").read()
    except OSError:
        print("  %s: no RAM dump" % keys); result = "FAIL"; continue
    best = None
    for n in (N, N - 1, N + 1, N + 2):
        ram = bytearray(before); want = {}
        for _ in range(n):
            for a, size, v in predict(ops, ram, key_mask(keys)):
                for k, byte in enumerate(v.to_bytes(size, "little")):
                    want[(a & 0x3FFFFF) + k] = byte
        changed = {a: v for a, v in want.items() if before[a] != v}
        bad = [a for a, v in changed.items() if after[a] != v]
        if best is None or len(bad) < len(best[1]):
            best = (n, bad, changed)
    n, bad, changed = best
    if not changed:
        print("  %-8s NOCHANGE: with these buttons the code writes nothing in this game state" % keys)
        result = "NOCHANGE" if result == "PASS" else result
    elif bad:
        a = bad[0]
        print("  %-8s FAIL: %d of %d bytes not as predicted, first %08x want %02x got %02x (before %02x)"
              % (keys, len(bad), len(changed), 0x02000000 + a, changed[a], after[a], before[a]))
        result = "FAIL"
    else:
        sample = sorted(changed)[:6]
        print("  %-8s PASS: %d bytes as predicted after %d frames (%s)" % (keys, len(changed), n,
              ", ".join("%08x %02x->%02x" % (0x02000000 + a, before[a], changed[a]) for a in sample)))
txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
if any(k in txt.lower() for k in ("fatal", "abort", "unhandled", "crash")) or p.returncode != 0:
    print("  suspicious log or exit code", p.returncode); result = "FAIL"
print("RESULT:", result)
sys.exit(0 if result == "PASS" else 2 if result == "NOCHANGE" else 1)
