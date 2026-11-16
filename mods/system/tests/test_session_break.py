"""Sessions that break, two games on this PC, headless, the Cheats window's agent running (incident log, Reconnect, the host's cheats for the guest).

   test_session_break.py <project root> <work dir> <port> <scenario>

   reconnect  the guest's game is killed in a running session: the host must write the break (and its cheats) into session-incidents.txt, answer the
              Reconnect question (DQIX_RECONNECT_TEST=yes), start again by itself and host the same port again; a new guest (DQIX_JOIN_RETRY) joins and the
              two stay in sync.
   desync     the guest's own console is changed outside the input stream (DQIX_TEST_DESYNC): the host must say OUT OF SYNC and log it.
   relay      through the real relay (internet): a session with a chosen code, then the same code again (what Reconnect does). SKIP without the relay.
   long       about 40 cheats on the host, some switched off and on again while the game runs (also ids the guest's list doesn't know): no crash, in sync.
Prints RESULT: PASS / FAIL / SKIP."""
import mmap, os, random, shutil, struct, subprocess, sys, time

root, work, port, scenario = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3], sys.argv[4]
FRAMES = {"reconnect": 3011, "desync": 1511, "relay": 1313, "long": 3511}[scenario]
EXE = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32
procs = []


def read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def launch(who, ses, extra=None, state=(), frames=FRAMES):
    d = os.path.join(work, who)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav"), os.path.join(d, "test.sav"))
    st = os.path.join(d, "state.txt")
    open(st, "w", encoding="utf-8").write("".join(l + "\r\n" for l in state))
    env = dict(os.environ)
    env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.pop("DQIX_CHEATWIN_OFF", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_SESSION=ses, DQIX_PLAYER_NAME=who, DQIX_NO_UPNP="1",
               DQIX_MENU_STATE=st, DQIX_MODLOG="1")
    if scenario != "relay":
        env["DQIX_NO_RELAY"] = "1"
    env.update(extra or {})
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([EXE, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    procs.append(p)
    return p, d


def front(d):
    return read(os.path.join(d, "session", "front.log"))


def same_count(d):
    return sum("sync with" in l and "same" in l for l in front(d).splitlines())


def bad(d):
    t = front(d)
    return "DIFFERENT" in t or "OUT OF SYNC" in t


def wait(cond, secs):
    t0 = time.time()
    while time.time() - t0 < secs:
        if cond():
            return True
        time.sleep(1)
    return False


def cleanup():
    for p in procs:
        if p.poll() is None:
            p.kill()
    # a game the Reconnect started by itself is not our child: found by its unique frame count on the command line
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='dqix.exe'\" | Where-Object { $_.CommandLine -match ' %d 1 test.sav' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % FRAMES],
                   capture_output=True)


def result(ok, text=""):
    cleanup()
    print("RESULT:", "PASS" if ok else "FAIL" + (" (" + text + ")" if text else ""))
    sys.exit(0 if ok else 1)


SOME = ["live file:cheats/max-gold.txt", "live file:cheats/first-strike.txt", "live file:cheats/monsters-cant-flee.txt"]

if scenario == "reconnect":
    h, hd = launch("host", f"host:{port}:2", {"DQIX_RECONNECT_TEST": "yes"}, SOME)
    time.sleep(2)
    g, gd = launch("join", f"join:127.0.0.1:{port}")
    if not wait(lambda: same_count(hd) > 0, 120):
        result(False, "the session never ran")
    print("1  the session runs, in sync")
    g.kill()                                                               # the guest's game dies
    inc = os.path.join(hd, "session-incidents.txt")
    if not wait(lambda: "left or was lost" in read(inc) or "session ended" in read(inc), 60):
        result(False, "no incident written: " + read(inc)[:200])
    t = read(inc)
    print("2  incident logged:", t.splitlines()[0][:110])
    if "max-gold" not in t.lower() and "gold" not in t.lower():
        result(False, "the incident doesn't list the cheats that were on")
    print("3  the cheats that were on are in the log")
    # Reconnect (answered yes by the test): the host starts again by itself and hosts again
    if not wait(lambda: "hosting" in front(hd) and "sync with" not in front(hd) and h.poll() is not None, 90):
        result(False, "the host did not host again by itself")
    print("4  the host started again and waits for players")
    g2, gd2 = launch("join2", f"join:127.0.0.1:{port}", {"DQIX_JOIN_RETRY": "30"})
    ok = wait(lambda: same_count(hd) > 0 and same_count(gd2) > 0, 150)
    print("5  the new guest joined, host checks in sync: %d, guest: %d" % (same_count(hd), same_count(gd2)))
    result(ok and not bad(hd) and not bad(gd2), "no sync after the reconnect")

elif scenario == "desync":
    h, hd = launch("host", f"host:{port}:2", {"DQIX_RECONNECT_TEST": "no"}, SOME)
    time.sleep(2)
    g, gd = launch("join", f"join:127.0.0.1:{port}", {"DQIX_RECONNECT_TEST": "no", "DQIX_TEST_DESYNC": "500"})
    # the PC that has the changed console's copy compares the other PC's fingerprints: here the host notices (the guest's own console is the one that drifted)
    ok = wait(lambda: "OUT OF SYNC" in front(hd), 150)
    print("1  the host says OUT OF SYNC:", ok)
    ok2 = wait(lambda: "OUT OF SYNC" in read(os.path.join(hd, "session-incidents.txt")), 30)
    print("2  the host wrote it into session-incidents.txt (with its cheats):", ok2)
    print(read(os.path.join(hd, "session-incidents.txt"))[:400])
    result(ok and ok2)

elif scenario == "relay":
    code = "".join(random.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))
    shown = "DQ-%s-%s" % (code[:4], code[4:])
    results = []
    for run in (1, 2):                                                     # the second time with the same code: what Reconnect does
        for p in procs:
            if p.poll() is None:
                p.kill()
        time.sleep(3)
        h, hd = launch("host", f"host:{port}:2", {"DQIX_RELAY_CODE": code}, SOME)
        if not wait(lambda: shown in front(hd), 45):                      # the relay shows the code in the host's log when it is registered
            print(front(hd)[-500:]); cleanup(); print("RESULT: SKIP (the relay is not reachable from here)"); sys.exit(0)
        time.sleep(3)
        g, gd = launch("join", f"join:{shown}", {"DQIX_JOIN_RETRY": "10"})
        ok = wait(lambda: same_count(hd) > 0 and same_count(gd) > 0, 120)
        print("run %d (code %s): in sync through the relay: %s" % (run, shown, ok), flush=True)
        if not ok:
            print(front(hd)[-600:])
            print(front(gd)[-600:])
        results.append(ok)
    result(all(results))

else:                                                                      # long
    cat = [dict(x.split("=", 1) for x in l.rstrip("\n").split("\t")[1:] if "=" in x) for l in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8") if l.startswith("entry\t")]
    pick = [d for d in cat if d.get("kind") == "live" and d.get("mode") in ("always", "") and d.get("ops") and not d.get("group") and d.get("cat") != "Live battle"
            and len(d["ops"].split(",")) < 40][:40]
    print("%d cheats" % len(pick))
    h, hd = launch("host", f"host:{port}:2", {"DQIX_RECONNECT_TEST": "no"}, [])
    time.sleep(2)
    g, gd = launch("join", f"join:127.0.0.1:{port}", {"DQIX_RECONNECT_TEST": "no"})
    box = None
    for _ in range(400):
        try:
            b = mmap.mmap(-1, MB + RING * 2, tagname=f"Local\\dqix-mod-cheats-{h.pid}", access=mmap.ACCESS_WRITE)
            if struct.unpack_from("<I", b, 0)[0] == 0x43584451:
                box = b
                break
            b.close()
        except OSError:
            pass
        time.sleep(0.05)
    if box is None:
        result(False, "no mailbox")

    def frame():
        return struct.unpack_from("<I", box, 28)[0]

    def send(typ, ident, ops):
        words = [ident]
        for o in ops:
            a, v = (int(x, 16) for x in o.split(":"))
            words += [a & 0xFFFF, a >> 16, v & 0xFFFF, v >> 16]
        msg = [typ << 12 | len(words)] + words
        w = struct.unpack_from("<I", box, 8)[0]
        for x in msg:
            struct.pack_into("<H", box, MB + (w % RING) * 2, x)
            w += 1
        struct.pack_into("<I", box, 8, w)

    def at(f):
        t0 = time.time()
        while frame() < f and h.poll() is None and time.time() - t0 < 300:
            time.sleep(0.02)

    at(800)                                                                # in the session: everything on
    for i, d in enumerate(pick):
        send(2, 100 + i, d["ops"].split(","))
        time.sleep(0.15)
    at(1700)                                                               # half off
    for i in range(0, len(pick), 2):
        send(3, 100 + i, [])
        time.sleep(0.15)
    at(2500)                                                               # and on again
    for i in range(0, len(pick), 2):
        send(2, 100 + i, pick[i]["ops"].split(","))
        time.sleep(0.15)
    for p in (h, g):
        try:
            p.wait(timeout=400)
        except subprocess.TimeoutExpired:
            p.kill()
    rcs = [h.returncode, g.returncode]
    print("exit codes", rcs, "| in sync: host %d, guest %d | different: %s" % (same_count(hd), same_count(gd), bad(hd) or bad(gd)))
    t = read(os.path.join(hd, "run.log")) + read(os.path.join(gd, "run.log"))
    result(rcs == [0, 0] and same_count(hd) > 5 and same_count(gd) > 5 and not bad(hd) and not bad(gd) and "fatal" not in t.lower(), "see the logs in " + work)
