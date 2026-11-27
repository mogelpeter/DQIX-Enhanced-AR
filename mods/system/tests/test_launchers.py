"""Every "Battle any monster you want" choice (catalog entries live:monster:*) in a real battle, headless, Windows.
   test_launchers.py <project root> <work dir> [first] [count] [jobs] [step]

   Needs a save with the hero in a dungeon where a fight is reached (TEST_SAVE, default tests\\dqix_dungeon.sav). Every
   roamer is a metal slime (DQIX_MOD_FORCE=3), so one reaches the hero; the choice is switched on through the mailbox the
   way the Cheats window does it, and the battle that starts must be against it. A pressed on a timer, 6000 frames.
   PASS    the battle started as chosen (a legacy level: with its stats), ran to the end, no suspicious log line
   NOBATTLE ran fine, but the log shows no battle against it
   FAIL    crash, hang, or a suspicious log line (the run's folder is kept)
   Writes <work>/launchers.txt with one `id  # name  RESULT` line per monster. About 5 minutes for all with 10 jobs."""
import concurrent.futures as cf, mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
first = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
count = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 999
jobs = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 4
step = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else 1      # 12 = every 12th monster (a spread sample)
FRAMES = int(os.environ.get("TEST_FRAMES", "6000"))
exe = os.environ.get("TEST_EXE") or os.path.join(root, "game", "dqix.exe")
dungeon = os.path.join(root, "mods", "system", "tests", "dqix_dungeon.sav")
save = os.environ.get("TEST_SAVE") or (dungeon if os.path.isfile(dungeon) else os.path.join(root, "game", "dqix.sav"))
RING, AT = 8192, 32
os.makedirs(work, exist_ok=True)


def monsters():
    out = []
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if line.startswith("entry\t"):
            d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
            if d.get("id", "").startswith("live:monster:"):
                out.append((d["id"], d["name"], [tuple(int(x, 16) for x in o.split(":")) for o in d["ops"].split(",")]))
    return out


def mailbox(p):
    for _ in range(400):
        try:
            box = mmap.mmap(-1, AT + RING * 2, tagname="Local\\dqix-mod-cheats-%d" % p.pid, access=mmap.ACCESS_WRITE)
            if struct.unpack_from("<I", box, 0)[0] == 0x43584451:
                return box
            box.close()
        except OSError:
            pass
        time.sleep(0.02)
    return None


def run(item):
    cid, name, ops = item
    d = os.path.join(work, cid.replace(":", "_"))
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, FRAMES + 100, 90))
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_MODLOG="1",
               DQIX_FAST="1", DQIX_MOD_FORCE="3", DQIX_INPUT=inp)
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    box, rc = mailbox(p), "timeout"
    try:
        if box is not None:
            while struct.unpack_from("<I", box, 28)[0] < 1000 and p.poll() is None:
                time.sleep(0.005)
            words = [7]                                         # SET: the choice is on from now on (id 7)
            for a, b in ops:
                words += [a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
            w = struct.unpack_from("<I", box, 8)[0]
            for x in [2 << 12 | len(words)] + words:
                struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
            struct.pack_into("<I", box, 8, w)
        rc = p.wait(timeout=900)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()
    log.close()
    txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
    bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unhandled", "crash", "out of sync"))]
    ran = "stopped after" in txt
    started = "becomes %d x" % (ops[0][1] & 0xFFF) in txt and (":lv" not in cid or "mod: legacy boss" in txt)
    if box is None:
        res = "FAIL no mailbox (is the game built with the mods?)"
    elif rc != 0 or not ran or bad:
        res = "FAIL rc=%s ran=%s %s" % (rc, ran, bad[:1])
    else:
        res = "PASS" if started else "NOBATTLE"
    if res == "PASS":
        shutil.rmtree(d, ignore_errors=True)
    return cid, name, res


items = monsters()[first:first + count:step]
print("monsters:", len(items), "| jobs", jobs, flush=True)
tally = {}
with cf.ThreadPoolExecutor(jobs) as ex, open(os.path.join(work, "launchers.txt"), "a", encoding="utf-8") as out:
    for cid, name, res in ex.map(run, items):
        k = res.split()[0]; tally[k] = tally.get(k, 0) + 1
        out.write("%s  # %s  %s\n" % (cid, name, res)); out.flush()
        print("%-9s %-34s %s" % (k, name[:34], res if k == "FAIL" else ""), flush=True)
print("TOTAL", tally)
ok = bool(items) and tally.get("PASS", 0) == len(items)          # nothing found or no battle is not a pass
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
