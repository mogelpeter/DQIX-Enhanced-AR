"""Code mods that run live (livepatch.c): headless game, RAM compared at one frame.
   test_livepatch.py <project root> <work dir> [frame]   (TEST_SAVE: a save with the hero in a dungeon, so the field is reached)

   Needs a game built with the mods' live-patch wrappers (mods/system/bin/livepatch.txt exists) and its catalog.
   A  nothing on                         (twice: the run must be repeatable)
   B  DQIX_LP_FORCE=1                    every wrapped function runs in the interpreter: RAM must equal A (a timing counter may be one off)
   C  "x1" of Movement Speed Multiplier  patched with the game's own word: RAM must equal A (within the same few bytes)
   E  all live code mods at once         nothing may crash or print a suspicious line; the log (DQIX_MODLOG) says which patched functions ran
   D  one mod whose function ran in E    alone: its instructions are applied (log line), the game keeps running
   Uses TEST_EXE / TEST_SAVE like the other tests."""
import mmap, os, re, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAME = int(sys.argv[3]) if len(sys.argv) > 3 else 4500
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE", os.path.join(root, "game", "dqix.sav"))
os.makedirs(work, exist_ok=True)
RING, AT = 8192, 32


def entries():
    out = []
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if line.startswith("entry\t"):
            d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
            if d.get("kind") == "live" and d.get("ops"):
                d["ops"] = [tuple(int(x, 16) for x in o.split(":")) for o in d["ops"].split(",")]
                out.append(d)
    return out


def lp(e):
    return all(0x02F60000 <= a < 0x02F70000 for a, b in e["ops"])


LASTLOG = ""


def run(tag, cheats=(), env_extra=None):
    d = os.path.join(work, tag)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_RAMDUMP=".,%d" % FRAME)
    # the boot menu uses none of the field code the mods touch: press A on a timer like the other tests, to get to the field
    env["DQIX_INPUT"] = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6;%d:%s:30" % (f, f + 40, ("UP", "RIGHT", "DOWN", "LEFT")[(f // 90) % 4]) for f in range(900, FRAME + 100, 90))
    env.update(env_extra or {})
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAME + 30), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    if cheats:
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
            p.kill(); return None, "no mailbox"
        u = lambda off: struct.unpack_from("<I", box, off)[0]
        while u(28) < 30 and p.poll() is None:
            time.sleep(0.005)
        for cid, e in enumerate(cheats):
            ws = [cid + 1]
            for a, b in e["ops"]:
                ws += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
            msg = [2 << 12 | len(ws)] + ws
            w = u(8)
            while w - u(12) + len(msg) > RING - 8:
                time.sleep(0.01)
            for x in msg:
                struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
            struct.pack_into("<I", box, 8, w)
    p.wait(timeout=900); log.close()
    txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
    bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unhandled", "crash", "interp: unknown", "out of sync"))]
    global LASTLOG
    LASTLOG = txt
    ram = open(os.path.join(d, "ram%06d.bin" % FRAME), "rb").read() if os.path.exists(os.path.join(d, "ram%06d.bin" % FRAME)) else None
    return ram, (p.returncode, bad)


NOISE = set()          # bytes that differ between two identical runs (a counter near the top of RAM): ignored


def ndiff(a, b):
    return sum(1 for i, (x, y) in enumerate(zip(a, b)) if x != y and i not in NOISE) if a and b else -1


ents = entries()
lps = [e for e in ents if lp(e)]
if not lps:
    print("FAIL: no live code mods in the catalog (is the game built with the live-patch wrappers, and catalog.py run after?)"); sys.exit(1)
by = {e["name"]: e for e in lps}
print("live code mods:", len(lps), flush=True)
ok = True
A, ra = run("A", ())
A2, ra2 = run("A2", ())
NOISE = {i for i, (x, y) in enumerate(zip(A, A2)) if x != y} if A and A2 else set()
print("A  repeatable (apart from %d noisy bytes: %s):" % (len(NOISE), ", ".join("%08x" % (0x02000000 + i) for i in sorted(NOISE)[:6])), len(NOISE) < 64, ra, flush=True)
ok &= A is not None and len(NOISE) < 64 and ra[0] == 0 and not ra[1]
B, rb = run("B", (), {"DQIX_LP_FORCE": "1"})
print("B  interpreter ~ compiled (a timing counter may be one off):", 0 <= ndiff(A, B) <= 16, "(diff bytes %d)" % ndiff(A, B), rb, flush=True)
ok &= B is not None and 0 <= ndiff(A, B) <= 16 and rb[0] == 0 and not rb[1]
# E: every live code mod that clashes with none of the others (one of each address), with the log on
chosen, used = [], set()
for e in lps:
    sites = {a for a, b in e["ops"]}
    if not (sites & used):
        chosen.append(e); used |= sites
E, re_ = run("E", tuple(chosen), {"DQIX_MODLOG": "1"})
elog = LASTLOG
seen = set(re.findall(r"livepatch function ([0-9a-f]{8}) runs", elog))
print("E  %d live code mods at once: game ran, no suspicious line:" % len(chosen), E is not None and re_[0] == 0 and not re_[1], re_, flush=True)
print("E  functions that ran with a mod's instructions in them:", len(seen), sorted(seen)[:8], flush=True)
ok &= E is not None and re_[0] == 0 and not re_[1] and len(seen) >= 1

# which function does each mod patch (mods/system/bin/livepatch.txt: number module address function)
fn_of = {}
for line in open(os.path.join(root, "mods", "system", "bin", "livepatch.txt"), encoding="utf-8"):
    w = line.split()
    if len(w) >= 4 and not line.startswith("#"):
        fn_of[0x02F60000 + 4 * int(w[0])] = w[3]
cands = [e for e in lps if any(fn_of.get(a) in seen for a, b in e["ops"])]
# D: one mod whose function the run reaches, alone: its instructions must be applied (log) and the game must go on
if cands:
    d_e = cands[0]
    D, rd = run("D", (d_e,), {"DQIX_MODLOG": "1"})
    hit = re.search(r"livepatch function ([0-9a-f]{8}) runs", LASTLOG) is not None
    print("D  \"%s\" alone: its instructions were applied:" % d_e["name"], hit, "| RAM differs from the unpatched run by %d bytes" % ndiff(A, D), rd, flush=True)
    ok &= D is not None and hit and rd[0] == 0 and not rd[1]
else:
    print("D  FAIL: no mod's function was reached in this run"); ok = False
# F: a peer in a session sends a word no mod uses ("b ." = endless loop) for a site that is reached: it must be ignored
if cands:
    evil = {"name": "not a mod", "ops": [(a, 0xEAFFFFFE) for a, b in cands[0]["ops"]]}
    F, rf = run("F", (evil,), {"DQIX_MODLOG": "1"})
    refused = re.search(r"livepatch function ([0-9a-f]{8}) runs", LASTLOG) is None
    print("F  a word no mod uses is refused, the game runs on:", refused, rf, flush=True)
    ok &= F is not None and refused and rf[0] == 0 and not rf[1]
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
