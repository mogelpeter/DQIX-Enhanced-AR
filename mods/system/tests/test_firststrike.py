"""Headless runs for the cheat "Always strike first" (firststrike.c): the hero walks a dungeon with metal slimes everywhere
(DQIX_MOD_FORCE=3) and A pressed on a timer, so a battle starts by touch. Two runs from the same save:
   on   the cheat is switched on through the mailbox before the first battle: where the field asks who moves first
        (bl 021970a0 at 0x02196b40) the answer must come from the cheat ("mod: firststrike party first")
   off  no cheat: the same question is asked and the game answers itself ("mod: firststrike game says ...")
Both must run to the end of the frames. Needs the game built with the mods and a save with the hero in a dungeon
(TEST_SAVE; the backup dqix-20261113-170934.sav works). A build with "Monsters don't chase you" built in may not reach
a fight: the result then says SKIP (exit 2). Slow: about 3 minutes (both runs at once).
   test_firststrike.py <project root> <work dir> [frames]"""
import concurrent.futures as cf, mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAMES = int(sys.argv[3]) if len(sys.argv) > 3 else 7500
exe = os.environ.get("TEST_EXE") or os.path.join(root, "game", "dqix.exe")
save = os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav")
RING, AT = 8192, 32


def run(tag, cheat):
    d = os.path.join(work, tag)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, FRAMES + 100, 90))
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
               DQIX_MODLOG="1", DQIX_MOD_FORCE="3", DQIX_INPUT=inp)
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
        while struct.unpack_from("<I", box, 28)[0] < 1200 and p.poll() is None:     # save loaded, before the first battle (USA: about frame 2950)
            time.sleep(0.01)
        a, b = 0x02F5A5AC, 1                                                       # SET: the cheat "Always strike first" is on
        msg = [2 << 12 | 5, 12, a & 0xFFFF, a >> 16, b & 0xFFFF, b >> 16]
        w = struct.unpack_from("<I", box, 8)[0]
        for x in msg:
            struct.pack_into("<H", box, AT + (w % RING) * 2, x); w += 1
        struct.pack_into("<I", box, 8, w)
    p.wait(timeout=1200); log.close()
    return open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()


with cf.ThreadPoolExecutor(2) as ex:
    on, off = ex.submit(run, "on", True), ex.submit(run, "off", False)
    on, off = on.result(), off.result()
if on is None:
    print("RESULT: FAIL (no mailbox: is the game built with the mods?)"); sys.exit(1)
first = [l for l in on.splitlines() if l.startswith("mod: firststrike party first")]
game_on = [l for l in on.splitlines() if l.startswith("mod: firststrike game says")]
game_off = [l for l in off.splitlines() if l.startswith("mod: firststrike game says")]
print("on: cheat answered %d time(s), game answered %d | off: game answered %d time(s): %s"
      % (len(first), len(game_on), len(game_off), ", ".join(l.split("says ")[1] for l in game_off[:6])))
if "stopped after" not in on or "stopped after" not in off:
    print("RESULT: FAIL (a game did not run to the end of the frames)"); sys.exit(1)
if not first and not game_off:
    print("RESULT: SKIP (no battle started by touch: the fight was not reached; try TEST_SAVE / TEST_EXE)"); sys.exit(2)
if not first or game_on:
    print("RESULT: FAIL (with the cheat on, the question was not answered by the cheat)"); sys.exit(1)
print("RESULT: PASS")
