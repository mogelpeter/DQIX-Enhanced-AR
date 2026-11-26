"""Two players on this PC, headless, the Cheats window's agent running (not DQIX_CHEATWIN_OFF): the host has cheats on, the guest has none.
   The guest's window must take the host's cheats (its own console gets the gold), nobody may crash, and the session must stay in sync.
   test_session_cheats.py <project root> <work dir> <port>"""
import os, shutil, subprocess, sys, time

root, work, port = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
FRAMES, DUMP = 1200, 1000
GOLD_AT, GOLD = 0x020F6D48 - 0x02000000, 0x0098967F
HOST_STATE = ["live file:cheats/max-gold.txt", "live file:cheats/lower-level-more-exp.txt", "live file:cheats/vanish.txt", "live file:cheats/first-strike.txt",
              "live file:cheats/monsters-cant-flee.txt"]
procs = []
for who, ses in (("host", f"host:{port}:2"), ("join", f"join:127.0.0.1:{port}")):
    d = os.path.join(work, who)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
    st = os.path.join(d, "state.txt")
    open(st, "w", encoding="utf-8").write("".join(l + "\r\n" for l in (HOST_STATE if who == "host" else [])))
    env = dict(os.environ)
    env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_SESSION=ses, DQIX_PLAYER_NAME=who, DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
               DQIX_MENU_STATE=st, DQIX_RAMDUMP=".,%d" % DUMP, DQIX_MODLOG="1")
    env.pop("DQIX_CHEATWIN_OFF", None)
    log = open(os.path.join(d, "run.log"), "wb")
    procs.append(subprocess.Popen([os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe")), os.path.join(root, "game", "data", "dqix.nds"),
                                   os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"], cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT))
    time.sleep(2)
t0 = time.time()
while any(p.poll() is None for p in procs) and time.time() - t0 < 300:
    time.sleep(1)
rcs = []
for p in procs:
    if p.poll() is None:
        p.kill(); rcs.append("hung")
    else:
        rcs.append(p.returncode)
good = all(rc == 0 for rc in rcs)
for who in ("host", "join"):
    try:
        lines = open(os.path.join(work, who, "session", "front.log"), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        print(who, "no front.log"); good = False; continue
    sync = [l for l in lines if "sync with" in l or "OUT OF SYNC" in l]
    print(who, "| checks:", len(sync), "| same:", sum("same" in l for l in sync), "| different:", sum("DIFFERENT" in l for l in sync))
    good &= len(sync) > 0 and not any("DIFFERENT" in l or "OUT OF SYNC" in l for l in sync)
    try:
        ram = open(os.path.join(work, who, "ram%06d.bin" % DUMP), "rb").read()
        gold = int.from_bytes(ram[GOLD_AT:GOLD_AT + 4], "little")
    except OSError:
        gold = -1
    print(who, "| gold in its RAM: %#x (want %#x)" % (gold, GOLD))
    good &= gold == GOLD
print("exit codes:", rcs)
print("RESULT:", "PASS" if good else "FAIL")
sys.exit(0 if good else 1)
