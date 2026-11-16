"""Headless runs for "Vanish" in the field (vanish.c): the hero stands in a dungeon with metal slimes everywhere
(DQIX_MOD_FORCE=3) and A pressed on a timer, so monsters come and touch the party. Two runs from the same save:
   on   the cheat is switched on through the mailbox at frame 1200 and L+R+SELECT pressed at 1300: no battle may start by
        touch after that (firststrike.c logs every "who moves first" question of a starting battle), and the contact
        function must have run in the interpreter without its monster loop ("mod: vanish runs the contact check")
   off  no cheat: battles start by touch (else the test can't tell anything: SKIP)
Pictures of both runs (DQIX_DUMP, every TEST_SHOTS frames, default 1250) are written to <work>/on and <work>/off: a monster
that walked into the hero must walk on, not stand frozen next to him (the first two versions of vanish.c did that).
Needs the game built with the mods and a save with the hero in a dungeon (TEST_SAVE; the backup dqix-20261113-170934.sav
works). About 3 minutes (both runs at once).
   test_vanish_walk.py <project root> <work dir> [frames]"""
import concurrent.futures as cf, mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAMES = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
exe = os.environ.get("TEST_EXE") or os.path.join(root, "game", "dqix.exe")
save = os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav")
RING, AT = 8192, 32
SHOTS = os.environ.get("TEST_SHOTS", "1250")                       # DQIX_DUMP: a picture every that many frames


def run(tag, cheat):
    d = os.path.join(work, tag)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, FRAMES + 100, 90) if not 1290 <= f <= 1310)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
               DQIX_MODLOG="1", DQIX_MOD_FORCE="3", DQIX_INPUT=inp, DQIX_DUMP=d + "," + SHOTS)
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    if cheat:
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
            p.kill(); return None
        while struct.unpack_from("<I", box, 28)[0] < 1200 and p.poll() is None:
            time.sleep(0.01)
        a, b = 0x02F5A5A4, 1                                                       # SET: the cheat "Vanish" is on (its switch)
        msg = [2 << 12 | 5, 7, a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
        w = struct.unpack_from("<I", box, 8)[0]
        for x in msg:
            struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
        struct.pack_into("<I", box, 8, w)
    p.wait(timeout=1200); log.close()
    return open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()


def frame_of(line):
    try:
        return int(line.rsplit("frame", 1)[1].split()[0])
    except (IndexError, ValueError):
        return -1


with cf.ThreadPoolExecutor(2) as ex:
    on, off = ex.submit(run, "on", True), ex.submit(run, "off", False)
    on, off = on.result(), off.result()
if on is None:
    print("RESULT: FAIL (no mailbox: is the game built with the mods?)"); sys.exit(1)
start = lambda txt: [l for l in txt.splitlines() if l.startswith("mod: firststrike")]
van = [l for l in on.splitlines() if l.startswith("mod: vanish on")]
on_after = [l for l in start(on) if frame_of(l) > 1300]
off_after = [l for l in start(off) if frame_of(l) > 1300]
print("vanish:", van[:1], "| battles by touch after frame 1300: on %d, off %d" % (len(on_after), len(off_after)))
bad = [l for l in on.splitlines() if any(k in l.lower() for k in ("fatal", "abort", "unhandled", "crash"))]
if "stopped after" not in on or "stopped after" not in off or bad:
    print("RESULT: FAIL (a game did not run to the end of the frames)", bad[:3]); sys.exit(1)
if not van:
    print("RESULT: FAIL (vanish did not go on)"); sys.exit(1)
if "mod: vanish runs the contact check" not in on:
    print("RESULT: FAIL (the contact check was not run with vanish's changes: the game's instructions are not the expected ones?)"); sys.exit(1)
if not off_after:
    print("RESULT: SKIP (no battle by touch without the cheat: try TEST_SAVE / TEST_EXE)"); sys.exit(2)
if on_after:
    print("RESULT: FAIL (a battle started by touch while vanished)"); sys.exit(1)
print("pictures:", os.path.join(work, "on"), os.path.join(work, "off"))
print("RESULT: PASS")
