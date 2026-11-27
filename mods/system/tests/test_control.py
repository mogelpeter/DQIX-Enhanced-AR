"""Remote control (tools/drive.py + src/runtime/mod_control.c): a headless game that waits between commands. Windows.

   test_control.py <project root> <work dir>

   1  start: the game stops at once, writes a picture and stays on that frame while nothing is asked of it
   2  do: exactly the frames asked for pass; a script with an unknown button is refused and nothing moves
   3  start --field + touch: the buttons load the save, the stylus lands on the pixel asked for
   4  cheat: "Gold always 9,999,999" switched on arrives in the game's RAM
   5  stop: the game ends by itself; the save it was given is unchanged (it plays on a copy)
Needs the game built with the mods. TEST_EXE / TEST_SAVE as in the other tests."""
import hashlib, os, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.join(HERE, "..", "tools", "drive.py")
save = os.environ.get("TEST_SAVE") or os.path.join(HERE, "dqix_test.sav")
if not os.path.isfile(save):
    save = os.path.join(root, "game", "dqix.sav")
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
session = os.path.join(work, "drive")
errors = []


def drive(*args):
    p = subprocess.run([sys.executable, "-X", "utf8", DRIVE, "--root", root, "--dir", session, *args],
                       capture_output=True, text=True, errors="replace", timeout=300)
    return p.returncode, p.stdout + p.stderr


def field(out, name):
    for line in out.splitlines():
        if line.startswith(name + " "):
            return line[len(name) + 1:].strip()
    return ""


def frame(out):
    f = field(out, "frame")
    return int(f) if f.isdigit() else -1


def ram(addr, n):
    rc, out = drive("read", "%08x" % addr, str(n))
    if rc or ":" not in out:
        return b""
    return bytes.fromhex(out.split(":", 1)[1].strip().replace(" ", ""))


def check(ok, what, out=""):
    print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
    if not ok:
        errors.append(what)
        print("        " + "\n        ".join(out.strip().splitlines()[-8:]), flush=True)
    return ok


def digest(p):
    return hashlib.sha1(open(p, "rb").read()).hexdigest()


before = digest(save)
try:
    drive("stop")                                           # a leftover of an earlier run
    rc, out = drive("start", "--save", save, "--exe", exe)
    if check(rc == 0 and frame(out) >= 0, "1 start: the game answers", out):
        f0, png = frame(out), field(out, "screen")
        check(os.path.isfile(png) and open(png, "rb").read(8) == b"\x89PNG\r\n\x1a\n", "1 start: a picture is there", out)
        time.sleep(1.5)
        rc, out = drive("look")
        check(rc == 0 and frame(out) == f0, "1 the game waits (frame %d stays)" % f0, out)
        rc, out = drive("start", "--save", save, "--exe", exe)
        check(rc != 0, "1 a second start is refused while one runs", out)
        rc, out = drive("do", ".:100")
        check(rc == 0 and frame(out) == f0 + 100, "2 do .:100 moves exactly 100 frames", out)
        rc, out = drive("do", "FOO:3")
        check(rc != 0 and "FOO" in out, "2 an unknown button is refused", out)
        rc, out = drive("look")
        check(frame(out) == f0 + 100, "2 ... and nothing moved", out)
    drive("stop")
    rc, out = drive("start", "--save", save, "--exe", exe, "--field")
    if check(rc == 0 and frame(out) > 3000, "3 start --field", out):
        ptr = ram(0x020F33E0, 4)
        check(len(ptr) == 4 and ptr != b"\0\0\0\0", "3 the buttons loaded the save (field pointer %s)" % ptr.hex(), out)
        rc, out = drive("do", "touch=100,50:10")
        at = ram(0x02114E84, 8)
        got = (int.from_bytes(at[:4], "little", signed=True), int.from_bytes(at[4:], "little", signed=True)) if len(at) == 8 else None
        check(rc == 0 and got == (100, 50), "3 touch=100,50 lands there (game says %s)" % (got,), out)
        rc, out = drive("cheat", "file:cheats/max-gold.txt", "on")
        check(rc == 0, "4 cheat on", out)
        rc, out = drive("do", ".:200")
        gold = int.from_bytes(ram(0x020F6D48, 4), "little")
        check(rc == 0 and gold == 9999999, "4 the gold is in the game's RAM (%d)" % gold, out)
finally:
    rc, out = drive("stop")
check(rc == 0 and "stopped" in out, "5 stop: the game ends", out)
rc, out = drive("look")
check(rc != 0, "5 ... and is gone", out)
check(digest(save) == before, "5 the save given to it is unchanged")
print("RESULT: " + ("FAIL (%d)" % len(errors) if errors else "PASS"))
sys.exit(1 if errors else 0)
