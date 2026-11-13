"""Two players on this PC, headless: does the session stay in sync?
   test_session.py <project root> <work dir> <port> [host env NAME=VALUE ...]"""
import os, shutil, subprocess, sys, time

root, work, port = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
extra = dict(a.split("=", 1) for a in sys.argv[4:])
frames = "900"
procs = []
for who, ses in (("host", f"host:{port}:2"), ("join", f"join:127.0.0.1:{port}")):
    d = os.path.join(work, who)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
    env = dict(os.environ)
    env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_SESSION=ses, DQIX_PLAYER_NAME=who, DQIX_NO_UPNP="1", DQIX_NO_RELAY="1")
    if who == "host":
        env.update(extra)
    log = open(os.path.join(d, "run.log"), "wb")
    procs.append(subprocess.Popen([os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe")), os.path.join(root, "game", "data", "dqix.nds"),
                                   os.path.join(root, "game", "data", "code"), frames, "1", "test.sav"], cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT))
    time.sleep(2)
t0 = time.time()
while any(p.poll() is None for p in procs) and time.time() - t0 < 240:
    time.sleep(1)
for p in procs:
    if p.poll() is None:
        p.kill()
good = True
for who in ("host", "join"):
    try:
        lines = open(os.path.join(work, who, "session", "front.log"), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        print(who, "no front.log"); good = False; continue
    sync = [l for l in lines if "sync with" in l or "OUT OF SYNC" in l]
    print(who, "| checks:", len(sync), "| same:", sum("same" in l for l in sync), "| different:", sum("DIFFERENT" in l for l in sync))
    for l in sync[:3]:
        print("   ", l[:150])
    good &= len(sync) > 0 and not any("DIFFERENT" in l or "OUT OF SYNC" in l for l in sync)
print("RESULT:", "PASS" if good else "FAIL")
sys.exit(0 if good else 1)
