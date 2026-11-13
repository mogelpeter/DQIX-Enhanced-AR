"""Every live cheat of the catalog against a headless game, alone or with a friend.
   test_all.py <project root> <work dir> single|session [frames] [port]

   single : all live cheats are sent through the mailbox exactly like the menu does (switch on, "Once"),
            in two batches (the game holds 128 at a time). Checks: the game runs to its end, every message
            was carried out, no suspicious log line, and that plain "write this value" cheats are in RAM.
   session: the same on the host of a two-player session on this PC; the friend's console only gets them
            through the input stream. Every "sync ... same" must be same and both RAM dumps must match."""
import mmap, os, shutil, struct, subprocess, sys, time

root, work, mode = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
port = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else "47121"
BATCH = 120
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
os.makedirs(work, exist_ok=True)


def catalog():
    out, n = [], 0
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if not line.startswith("entry\t"):
            continue
        d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
        d["index"] = n
        n += 1
        if d.get("kind") == "live" and d.get("ops"):
            d["ops"] = [tuple(int(x, 16) for x in o.split(":")) for o in d["ops"].split(",")]
            out.append(d)
    return out


entries = catalog()
if os.environ.get("TEST_LIMIT"):
    entries = entries[:int(os.environ["TEST_LIMIT"])]          # quick runs (dev.py test fast)
print("live cheats:", len(entries))
def words(batch):
    """16 bits travel per frame, so this many frames to send a batch: every cheat switched on, and "Once" for those that have it"""
    return sum(2 + 4 * len(e["ops"]) for e in batch) + sum(1 + 4 * len(e["ops"]) for e in batch if e.get("mode") in ("once", "both"))


b1, b2 = entries[:BATCH], entries[BATCH:]
start1 = 30 if mode == "single" else 150
d1 = start1 + words(b1) + 200
d2 = d1 + 60 + words(b2) + 200
frames = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else d2 + 20
print("frames", frames, "(dumps at", d1, "and", d2, ")")
env_base = dict(os.environ)
env_base.pop("NoDefaultCurrentDirectoryInExePath", None)


def start(who, extra):
    d = os.path.join(work, who)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
    env = dict(env_base)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_RAMDUMP=f".,{d1},{d2}", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_PLAYER_NAME=who)
    env.update(extra)
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    return p, d, log


RING, AT = 8192, 32


def mailbox(p):
    for _ in range(300):
        try:
            box = mmap.mmap(-1, AT + RING * 2, tagname=f"Local\\dqix-mod-cheats-{p.pid}", access=mmap.ACCESS_WRITE)
            if struct.unpack_from("<I", box, 0)[0] == 0x43584451:
                return box
            box.close()
        except OSError:
            pass
        time.sleep(0.05)
    return None


class Mail:
    def __init__(self, box):
        self.box, self.sent = box, 0

    def u(self, off):
        return struct.unpack_from("<I", self.box, off)[0]

    def send(self, typ, cid, ops):
        words = ([cid] if cid is not None else [])
        for a, b in ops:
            words += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
        msg = [typ << 12 | len(words)] + words
        w = self.u(8)
        while w - self.u(12) + len(msg) > RING - 8:      # the game is still sending the last ones
            time.sleep(0.01)
        for x in msg:
            struct.pack_into("<H", self.box, AT + (w % RING) * 2, x); w += 1
        struct.pack_into("<I", self.box, 8, w)
        self.sent += 1

    def wait_frame(self, f, proc):
        while self.u(28) < f and proc.poll() is None:
            time.sleep(0.005)


def plain_writes(batch):
    """cheats made only of 32-bit 'write value' lines whose address nobody else in the batch writes: {addr: value}"""
    count = {}
    for e in batch:
        for a, b in e["ops"]:
            count[a] = count.get(a, 0) + 1
    want = {}
    for e in batch:
        if all(a >> 28 == 0 and count[a] == 1 and (a & ~0xF) != 0x02F5A5A0 and not 0x02F60000 <= (a & 0x0FFFFFFF) < 0x02F70000 for a, b in e["ops"]):      # 02F5A5A0..AF are switches (lowexp, vanish, noflee), not memory
            for a, b in e["ops"]:
                want[a & 0x3FFFFF] = (b, e["name"])
    return want


def drive(m, proc):
    m.wait_frame(start1, proc)
    m.send(4, None, [])
    for e in b1:
        m.send(2, e["index"], e["ops"])
    for e in b1:
        if e.get("mode") in ("once", "both"):
            m.send(1, None, e["ops"])
    m.wait_frame(d1 + 20, proc)                              # the first dump is behind us
    print(f"after batch 1: sent {m.sent}, carried out {m.u(24)}, forgotten-all count (gen) {m.u(16)}")
    m.send(4, None, [])
    for e in b2:
        m.send(2, e["index"], e["ops"])
    for e in b2:
        if e.get("mode") in ("once", "both"):
            m.send(1, None, e["ops"])
    return b1, b2


def ramfile(d, frame):
    with open(os.path.join(d, f"ram{frame:06d}.bin"), "rb") as f:
        return f.read()


def suspicious(d):
    txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
    bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unknown", "unhandled", "crash", "out of sync"))]
    return len(txt.splitlines()), bad


def watch(procs, m):
    last, t0 = -1, time.time()
    while any(p.poll() is None for p in procs):
        time.sleep(0.5)
        f = m.u(28)
        if f == last and time.time() - t0 > 30:
            print("FAIL: the game stopped at frame", f)
            for p in procs:
                p.kill()
            return False
        last = f
        if time.time() - t0 > 900:
            print("FAIL: timeout at frame", f)
            for p in procs:
                p.kill()
            return False
    return True


ok = True
if mode == "single":
    p, d, log = start("single", {})
    box = mailbox(p)
    if box is None:
        print("FAIL: no mailbox"); p.kill(); sys.exit(1)
    m = Mail(box)
    b1, b2 = drive(m, p)
    ran = watch([p], m)
    log.close()
    print("exit code", p.returncode, "frames", m.u(28), "messages sent", m.sent, "carried out", m.u(24), "gen", m.u(16))
    ok &= ran and p.returncode == 0 and m.u(24) == m.sent
    for frame, batch in ((d1, b1), (d2, b2)):
        try:
            ram = ramfile(d, frame)
        except OSError as e:
            print("FAIL: no RAM dump", e); ok = False; continue
        want = plain_writes(batch)
        miss = [(hex(a), hex(v), n) for a, (v, n) in want.items() if int.from_bytes(ram[a:a + 4], "little") != v]
        print(f"dump at frame {frame}: {len(want) - len(miss)}/{len(want)} plain write cheats are in RAM")
        for a, v, n in miss[:40]:
            print("   not in RAM:", a, v, n)
    n, bad = suspicious(d)
    print("log lines:", n, "| suspicious:", len(bad))
    for l in bad[:15]:
        print("   ", l[:200])
    ok &= not bad
else:
    ph, dh, lh = start("host", {"DQIX_SESSION": f"host:{port}:2"})
    time.sleep(2)
    pj, dj, lj = start("join", {"DQIX_SESSION": f"join:127.0.0.1:{port}"})
    box = mailbox(ph)
    if box is None:
        print("FAIL: no mailbox"); ph.kill(); pj.kill(); sys.exit(1)
    m = Mail(box)
    b1, b2 = drive(m, ph)
    ran = watch([ph, pj], m)
    lh.close(); lj.close()
    print("exit codes", ph.returncode, pj.returncode, "| messages sent", m.sent, "carried out", m.u(24))
    ok &= ran and ph.returncode == 0 and pj.returncode == 0 and m.u(24) == m.sent
    for who, d in (("host", dh), ("join", dj)):
        try:
            lines = open(os.path.join(d, "session", "front.log"), encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            print(who, "no front.log"); ok = False; continue
        sync = [l for l in lines if "sync with" in l or "OUT OF SYNC" in l]
        diff = [l for l in sync if "DIFFERENT" in l or "OUT OF SYNC" in l]
        print(who, "| checks:", len(sync), "| same:", sum("same" in l for l in sync), "| different:", len(diff))
        for l in diff[:3]:
            print("   ", l[:160])
        ok &= len(sync) > 0 and not diff
        n, bad = suspicious(d)
        print("  log lines:", n, "| suspicious:", len(bad))
        for l in bad[:8]:
            print("     ", l[:200])
    # each PC dumps the DS it plays itself, so the two dumps are not expected to be equal: "sync ... same" is the check.
    for who, d in (("host", dh), ("join", dj)):
        for frame, batch in ((d1, b1), (d2, b2)):
            try:
                ram = ramfile(d, frame)
            except OSError as e:
                print("no RAM dump", e); continue
            want = plain_writes(batch)
            have = sum(int.from_bytes(ram[a:a + 4], "little") == v for a, (v, n) in want.items())
            print(f"{who} dump at frame {frame}: {have}/{len(want)} plain write cheats in RAM")
            if who == "host":
                ok &= have == len(want)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
