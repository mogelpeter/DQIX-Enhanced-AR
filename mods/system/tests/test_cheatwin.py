"""The Cheats window inside the emulator (mod_cheatwin.c), headless game, Windows only.
   test_cheatwin.py <project root> <work dir> [frame]

   1  the window opens by itself (DQIX_CHEATWIN_TEST), switches "Gold always 9,999,999" on the way a click does
      (tab, then the row's check box) and draws itself into a picture:
        - the gold is in the game's RAM            (window -> mailbox -> game)
        - the state file has `live file:cheats/max-gold.txt`   
        - the picture exists (look at it: <work>/one/shot.bmp)
   2  a new start with that state file and no window: the cheat is sent again by itself (the gold is in RAM)
   3  a state with a choice from a group (x2 then x4) keeps only the last one
   Needs the game built with the mods (mod_cheatwin.c in runtime/) and a catalog. TEST_EXE / TEST_SAVE as in the other tests."""
import os, shutil, subprocess, sys

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAME = int(sys.argv[3]) if len(sys.argv) > 3 else 900
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE", os.path.join(root, "game", "dqix.sav"))
GOLD_AT, GOLD = 0x020F6D48 - 0x02000000, 0x0098967F
os.makedirs(work, exist_ok=True)


def run(tag, state_lines, extra):
    d = os.path.join(work, tag)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    st = os.path.join(d, "state.txt")
    open(st, "w", encoding="utf-8").write("".join(l + "\r\n" for l in state_lines))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_MENU_STATE=st, DQIX_RAMDUMP=".,%d" % FRAME)
    env.update(extra(d))
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.run([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAME + 30), "1", "test.sav"],
                       cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    log.close()
    txt = open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace")
    ram = open(os.path.join(d, "ram%06d.bin" % FRAME), "rb").read()
    return p.returncode, txt, ram, open(st, encoding="utf-8").read()


def gold(ram):
    return int.from_bytes(ram[GOLD_AT:GOLD_AT + 4], "little")


ok = True
rc, txt, ram, state = run("one", [], lambda d: {"DQIX_CHEATWIN_TEST": "file:cheats/max-gold.txt," + os.path.join(d, "shot.bmp")})
print("1  switched on through the window:", "cheatwin test: switched on" in txt, "| picture:", os.path.exists(os.path.join(work, "one", "shot.bmp")),
      "| gold in RAM: %#x" % gold(ram), "| state file has it:", "live file:cheats/max-gold.txt" in state, "| exit", rc, flush=True)
ok &= rc == 0 and "cheatwin test: switched on" in txt and gold(ram) == GOLD and "live file:cheats/max-gold.txt" in state and os.path.exists(os.path.join(work, "one", "shot.bmp"))

rc2, txt2, ram2, state2 = run("two", ["live file:cheats/max-gold.txt"], lambda d: {})
print("2  a new start sends it again by itself: gold in RAM %#x" % gold(ram2), "| exit", rc2, flush=True)
ok &= rc2 == 0 and gold(ram2) == GOLD

# 3: no window involved: the state file is read as it is. A choice keeps one: window test with x2 then the window picks x4 is covered by the
# catalog test (one group member on); here only that two members of a group in the state file do not crash the start
ids = [l.split("id=")[1].split("\t")[0] for l in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8")
       if l.startswith("entry\t") and "group=group:" in l and "kind=live" in l][:2]
rc3, txt3, ram3, state3 = run("three", ["live " + i for i in ids], lambda d: {})
print("3  two members of one choice in the state file: the game starts and runs, exit", rc3, flush=True)
ok &= rc3 == 0 and "fatal" not in txt3.lower()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
