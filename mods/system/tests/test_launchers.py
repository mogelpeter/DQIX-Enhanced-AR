"""Every "Battle any monster you want" launcher (DQIX_MOD_FORCE=n) against a headless game.
   test_launchers.py <project root> <work dir> [first] [count] [jobs] [step]

   Needs a save with the hero in a dungeon where a fight is reached (TEST_SAVE, default game\\dqix.sav; the backup
   dqix-20261113-170934.sav works) and a game without "Monsters don't chase you" (TEST_EXE, e.g. a `dev scratch` build).
   Per monster the game runs 6000 frames with A pressed on a timer; the bottom screen is dumped every 500 frames.
   PASS    ran to the end, no suspicious log line, and a battle screen (orange command panel) was seen
   NOBATTLE ran fine, but no fight started in time (not a failure of the launcher: encounter timing)
   FAIL    crash, hang, or a suspicious log line
   Keeps one screenshot per monster in <work>/shots/<n>.png (the frame with the battle) to look at.
   Writes <work>/launchers.txt with one `id  # name  RESULT` line per monster."""
import concurrent.futures as cf, os, shutil, subprocess, sys

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
first = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
count = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else 999
jobs = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 4
FRAMES = 6000
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE", os.path.join(root, "game", "dqix.sav"))
os.makedirs(os.path.join(work, "shots"), exist_ok=True)
from PIL import Image


def monsters():
    out = []
    for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if line.startswith("entry\t"):
            d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
            if d.get("id", "").startswith("launch:monster:"):
                out.append((d["id"], d["id"].rsplit(":", 1)[1], d["name"]))
    return out


def orange(path):
    im = Image.open(path).convert("RGB"); w, h = im.size
    px = list(im.crop((0, h // 2, w, h)).getdata())
    return sum(1 for r, g, b in px if r > 180 and 90 < g < 200 and b < 120) / len(px)


def run(item):
    cid, num, name = item
    d = os.path.join(work, "run" + num)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6;%d:%s:30" % (f, f + 40, ("UP", "RIGHT", "DOWN", "LEFT")[(f // 90) % 4]) for f in range(900, FRAMES + 100, 90))   # A for menus, a step now and then
    env.update(DQIX_NOWINDOW="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_MODLOG="1",
               DQIX_MOD_FORCE=num, DQIX_INPUT=inp, DQIX_DUMP=d + "," + "500")
    log = open(os.path.join(d, "run.log"), "wb")
    try:
        p = subprocess.run([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                           cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    log.close()
    txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
    bad = [l for l in txt.splitlines() if any(k in l.lower() for k in ("interpreting code", "fatal", "abort", "unhandled", "crash", "out of sync"))]
    best, shot = 0.0, None
    for f in range(4000, FRAMES + 1, 500):
        fp = os.path.join(d, "f%06d.ppm" % f)
        if os.path.exists(fp):
            o = orange(fp)
            if o > best:
                best, shot = o, fp
    if shot:
        Image.open(shot).convert("RGB").save(os.path.join(work, "shots", num + ".png"))
    ran = "stopped after" in txt
    if rc != 0 or not ran or bad:
        res = "FAIL rc=%s ran=%s %s" % (rc, ran, bad[:1])
    elif best > 0.2:
        res = "PASS"
    else:
        res = "NOBATTLE"
    shutil.rmtree(d, ignore_errors=True)
    return cid, name, res


step = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else 1      # 12 = every 12th monster (a spread sample)
items = monsters()[first:first + count:step]
print("launchers:", len(items), "| jobs", jobs, flush=True)
tally = {}
with cf.ThreadPoolExecutor(jobs) as ex, open(os.path.join(work, "launchers.txt"), "a", encoding="utf-8") as out:
    for cid, name, res in ex.map(run, items):
        k = res.split()[0]; tally[k] = tally.get(k, 0) + 1
        out.write("%s  # %s  %s\n" % (cid, name, res)); out.flush()
        print("%-9s %-34s %s" % (k, name[:34], res if k == "FAIL" else ""), flush=True)
print("TOTAL", tally)
print("RESULT:", "PASS" if not tally.get("FAIL") else "FAIL")
sys.exit(1 if tally.get("FAIL") else 0)
