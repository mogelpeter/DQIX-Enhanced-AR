#!/usr/bin/env python3
"""drive.py - play a headless game one command at a time, to try out the mods. Windows.

  drive.py start [--save F] [--exe F] [--field] [--env K=V ...]
                           a new game without window and sound, on a COPY of the save; --field loads it (title -> field)
  drive.py do "A .:60 UP:30 touch=128,100:6 A+R:20"
                           input, then the game waits again. what[:frames], 6 frames if not given; "." = nothing pressed.
                           Buttons A B SELECT START RIGHT LEFT UP DOWN R L X Y LID, touch=X,Y = bottom screen pixels
  drive.py look            the picture of the frame the game is on
  drive.py read ADDR [N]   N bytes of DS main RAM (default 4), ADDR in hex like 020F6D48
  drive.py cheat ID on|off a live cheat (id or name from mods\\system\\bin\\catalog.txt); arrives while the next frames run
  drive.py log [N]         the last N lines of the game's output (the mods report there)
  drive.py stop            end the game

Every command prints "frame N" and "screen <png>" (both DS screens, twice the size: top 0-383, bottom 384-767).
The game side is mods/system/src/runtime/mod_control.c: with DQIX_CONTROL=<folder> the game writes screen.ppm, ram.bin
and state.txt, then waits for cmd.txt. --root as for dev.py; --dir = the session folder (default: in the temp folder).
"""
import argparse, ctypes, json, mmap, os, re, shutil, struct, subprocess, sys, tempfile, time, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev import need_root

KEYS = ["A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L", "X", "Y", "LID"]     # the bit order of input.c
MB, RING = 32, 8192                                             # the cheat mailbox (mod_cheats.c McBox)
IDLE = 1800                                                     # seconds without a command after which the game ends


class Fail(Exception):
    pass


# ------------------------------------------------------------------ input
def parse(script):
    """'A:6 .:60 touch=1,2' -> [(frames, buttons, touch, x, y)]"""
    out = []
    for tok in re.split(r"[\s;]+", script.strip()):
        if not tok:
            continue
        what, _, n = tok.partition(":")
        if n and not (n.isdigit() and int(n) > 0):
            raise Fail("frames must be a number above 0: " + tok)
        mask = touch = x = y = 0
        for k in what.split("+"):
            m = re.fullmatch(r"touch=(\d+),(\d+)", k, re.I)
            if m:
                touch, x, y = 1, int(m.group(1)), int(m.group(2))
                if x > 255 or y > 191:
                    raise Fail("the bottom screen is 256 x 192: " + tok)
            elif k.upper() in KEYS:
                mask |= 1 << KEYS.index(k.upper())
            elif k != ".":
                raise Fail("unknown button \"%s\" (%s, touch=X,Y, or . for nothing)" % (k, " ".join(KEYS)))
        out.append((int(n or 6), mask, touch, x, y))
    if not out:
        raise Fail("empty script")
    return out


def field_script(frame):
    """from the start to standing in the field: the boot menu is the debug title, Start is its second line; then A until loaded"""
    presses = [(700, "DOWN"), (800, "A")] + [(f, "A") for f in range(900, 3400, 90)]
    out, at = [], frame
    for f, k in presses:
        if f < at:
            continue
        if f > at:
            out.append(".:%d" % (f - at))
        out.append(k + ":6"); at = f + 6
    out.append(".:%d" % max(1, 3800 - at))
    return " ".join(out)


# ------------------------------------------------------------------ the process
def alive(pid):
    """is this process id still a dqix game? (ids get reused)"""
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)                       # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code, name, size = ctypes.c_ulong(), ctypes.create_unicode_buffer(1024), ctypes.c_ulong(1024)
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size))
        return code.value == 259 and "dqix" in os.path.basename(name.value).lower()
    finally:
        k.CloseHandle(h)


def tail(d, n):
    try:
        return "\n".join(open(os.path.join(d, "run.log"), "rb").read().decode("utf-8", "replace").splitlines()[-n:])
    except OSError:
        return ""


def load(d):
    try:
        return json.load(open(os.path.join(d, "session.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def store(d, s):
    json.dump(s, open(os.path.join(d, "session.json"), "w", encoding="utf-8"))


def running(d):
    s = load(d)
    if not s or not alive(s["pid"]):
        raise Fail("no game running (drive.py start)" + ("\n" + tail(d, 8) if s else ""))
    return s


def state(d):
    try:
        seq, frame = open(os.path.join(d, "state.txt"), encoding="ascii").read().split()
        return int(seq), int(frame)
    except (OSError, ValueError):
        return None


def wait(d, pid, seq, timeout):
    """until the game has carried out command `seq` and waits again -> its frame"""
    end = time.time() + timeout
    while time.time() < end:
        st = state(d)
        if st and st[0] == seq:
            return st[1]
        if not alive(pid):
            raise Fail("the game ended:\n" + tail(d, 12))
        time.sleep(0.01)
    raise Fail("no answer from the game in %d s (is it built with the mods? drive.py stop)\n%s" % (timeout, tail(d, 8)))


def send(d, s, lines):
    s["seq"] += 1; store(d, s)
    tmp = os.path.join(d, "cmd.tmp")
    open(tmp, "w", encoding="ascii").write("%d\n%s\n" % (s["seq"], "\n".join(lines)))
    for _ in range(200):
        try:
            os.replace(tmp, os.path.join(d, "cmd.txt")); return
        except PermissionError:                                 # the game is reading the last one
            time.sleep(0.01)
    raise Fail("can't write cmd.txt")


def run_script(d, s, script):
    segs = parse(script)
    send(d, s, ["%d %d %d %d %d" % x for x in segs])
    return wait(d, s["pid"], s["seq"], 60 + sum(x[0] for x in segs) // 30)


# ------------------------------------------------------------------ what the game shows
def picture(d, frame):
    """screen.ppm (256 x 384) -> a PNG twice the size"""
    data = open(os.path.join(d, "screen.ppm"), "rb").read()
    px = data[data.index(b"255\n") + 4:]
    w, h = 256, 384
    raw = bytearray()
    for y in range(h):
        row = px[y * w * 3:(y + 1) * w * 3]
        big = bytearray(w * 6)
        for c in range(3):
            big[c::6] = row[c::3]; big[3 + c::6] = row[c::3]
        raw += (b"\0" + big) * 2

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    for f in os.listdir(d):
        if re.fullmatch(r"f\d+\.png", f):
            os.remove(os.path.join(d, f))
    out = os.path.join(d, "f%06d.png" % frame)                  # a new name per frame: a viewer can't show an old one
    open(out, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w * 2, h * 2, 8, 2, 0, 0, 0))
                          + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))
    return out


def report(d, frame):
    print("frame %d" % frame)
    print("screen " + picture(d, frame))


# ------------------------------------------------------------------ commands
def cmd_start(a, d):
    s = load(d)
    if s and alive(s["pid"]):
        raise Fail("a game already runs here (frame %s): drive.py stop" % (state(d) or ("?", "?"))[1])
    root = need_root(a.root)
    exe = os.path.abspath(a.exe or os.path.join(root, "game", "dqix.exe"))
    tests = os.path.join(root, "mods", "system", "tests")
    save = a.save or next((p for p in (os.path.join(tests, "dqix_dungeon.sav"), os.path.join(tests, "dqix_test.sav"), os.path.join(root, "game", "dqix.sav")) if os.path.isfile(p)), None)
    if not os.path.isfile(exe):
        raise Fail("no game at " + exe)
    if not save or not os.path.isfile(save):
        raise Fail("no save file: " + str(save))
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f in ("cmd.txt", "state.txt", "screen.ppm", "ram.bin", "session.json", "run.log", "test.sav"):
            os.remove(os.path.join(d, f))
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_CONTROL=".", DQIX_CONTROL_IDLE=str(IDLE), DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1",
               DQIX_CHEATWIN_OFF="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_FAST="1", DQIX_MODLOG="1")
    for kv in a.env or []:
        k, _, v = kv.partition("="); env[k] = v
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), "0", "1", "test.sav"],
                         cwd=d, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    s = {"pid": p.pid, "seq": 0, "root": root, "cheats": {}}
    store(d, s)
    frame = wait(d, p.pid, 0, 60)
    if a.field:
        frame = run_script(d, s, field_script(frame))
    print("save " + save + " (a copy)")
    report(d, frame)


def cmd_do(a, d):
    s = running(d)
    report(d, run_script(d, s, " ".join(a.script)))


def cmd_look(a, d):
    running(d)
    st = state(d)
    if not st:
        raise Fail("the game has not reported yet")
    report(d, st[1])


def cmd_read(a, d):
    running(d)
    at = int(a.addr, 16)
    if not 0x02000000 <= at <= 0x02400000 - a.n:
        raise Fail("main RAM is 02000000..023FFFFF")
    with open(os.path.join(d, "ram.bin"), "rb") as f:
        f.seek(at - 0x02000000)
        print("%08x: %s" % (at, f.read(a.n).hex(" ")))


def cmd_cheat(a, d):
    s = running(d)
    found = []
    for line in open(os.path.join(s["root"], "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if line.startswith("entry\t"):
            e = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
            if a.id == e["id"]:
                found = [e]; break
            if a.id.lower() == (e.get("option") or e.get("name", "")).lower():
                found.append(e)
    if not found:
        raise Fail("no cheat \"%s\" in the catalog" % a.id)
    if len(found) > 1:
        raise Fail("several cheats are called that: " + ", ".join(e["id"] for e in found))
    e = found[0]
    if e.get("kind") != "live" or not e.get("ops"):
        raise Fail("\"%s\" is not a live cheat (%s): it can't be switched while the game runs" % (a.id, e.get("kind")))
    if a.state == "on":
        num = s["cheats"].setdefault(e["id"], len(s["cheats"]) + 1)
        words = [num]
        for op in e["ops"].split(","):
            x, y = (int(v, 16) for v in op.split(":"))
            words += [x & 0xFFFF, x >> 16, y & 0xFFFF, y >> 16]
        msg = [(5 if e.get("undo") == "1" else 2) << 12 | len(words)] + words
    else:
        if e["id"] not in s["cheats"]:
            raise Fail("that cheat was not switched on here")
        msg = [3 << 12 | 1, s["cheats"][e["id"]]]
    box = mmap.mmap(-1, MB + RING * 2, tagname="Local\\dqix-mod-cheats-%d" % s["pid"], access=mmap.ACCESS_WRITE)
    magic, wr, rd = struct.unpack_from("<I", box, 0)[0], struct.unpack_from("<I", box, 8)[0], struct.unpack_from("<I", box, 12)[0]
    if magic != 0x43584451:
        raise Fail("no cheat mailbox: is the game built with the mods?")
    if (wr - rd) % 2**32 + len(msg) > RING - 8:
        raise Fail("the mailbox is full: let some frames run first (drive.py do .:600)")
    for w in msg:
        struct.pack_into("<H", box, MB + (wr % RING) * 2, w); wr = (wr + 1) % 2**32
    struct.pack_into("<I", box, 8, wr)
    store(d, s)
    print("%s %s: arrives during the next %d frames or so" % (e.get("option") or e.get("name"), a.state, len(msg) + 10))


def cmd_log(a, d):
    print(tail(d, a.n))


def cmd_stop(a, d):
    s = load(d)
    if not s or not alive(s["pid"]):
        print("no game was running"); return
    send(d, s, ["quit"])
    end = time.time() + 10
    while time.time() < end and alive(s["pid"]):
        time.sleep(0.05)
    if alive(s["pid"]):
        os.kill(s["pid"], 9)                                    # our own test game, and it doesn't listen
        print("stopped (it had to be ended: it did not answer)")
    else:
        print("stopped")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the DQIX Enhanced folder (with BUILD.bat)")
    ap.add_argument("--dir", default=os.path.join(tempfile.gettempdir(), "dqix-drive"), help="the session folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("--save"); p.add_argument("--exe"); p.add_argument("--field", action="store_true"); p.add_argument("--env", action="append"); p.set_defaults(f=cmd_start)
    p = sub.add_parser("do"); p.add_argument("script", nargs="+"); p.set_defaults(f=cmd_do)
    sub.add_parser("look").set_defaults(f=cmd_look)
    p = sub.add_parser("read"); p.add_argument("addr"); p.add_argument("n", nargs="?", type=int, default=4); p.set_defaults(f=cmd_read)
    p = sub.add_parser("cheat"); p.add_argument("id"); p.add_argument("state", choices=("on", "off")); p.set_defaults(f=cmd_cheat)
    p = sub.add_parser("log"); p.add_argument("n", nargs="?", type=int, default=20); p.set_defaults(f=cmd_log)
    sub.add_parser("stop").set_defaults(f=cmd_stop)
    a = ap.parse_args()
    try:
        a.f(a, os.path.abspath(a.dir))
    except Fail as e:
        print("drive: " + str(e)); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
