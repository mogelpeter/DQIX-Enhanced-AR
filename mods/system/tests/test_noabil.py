"""The Challenges page's "No abilities" (challenges.c no_abilities, switch 02F5A628) in a real battle, headless, Windows. EU and USA game alike.

   test_noabil.py <project root> <work dir>

Two runs, side by side, of the same forced battle (DQIX_MOD_FORCE=3: every roamer a metal slime; the save = tests/dqix_dungeon.sav or TEST_SAVE: the party
in a dungeon, the hero a Minstrel with Dragon Slash first in his Abilities), the same key presses: the hero's first command is that ability, picked in the
menu (Fight, Abilities, the first one, the first target; NOABIL_KEYS overrides, "frame:KEY:hold;...").
   run 1, the switch off:  the game's own log must show NO "no abilities" line (the control: the picked ability is carried out as always)
   run 2, the switch on:   the log must show "mod: no abilities: party member 0's ability N became Defend", N in 63..201 (the skill trees' abilities)
Also checks the catalog entry (live:challenge:noabilities writes 02F5A628) and that nothing else in the log looks like a crash.
Prints RESULT: PASS / FAIL."""
import mmap, os, re, shutil, struct, subprocess, sys, threading, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32
FRAMES = int(os.environ.get("NOABIL_FRAMES", "5700"))     # the battle's first command comes at frame ~4900; the ability is picked by ~5500
KEYS = os.environ.get("NOABIL_KEYS", "5000:A:6;5100:RIGHT:6;5200:A:6;5320:A:6;5440:A:6")    # Fight, Abilities, the list, Dragon Slash, the first target
SAVE = os.environ.get("TEST_SAVE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "dqix_dungeon.sav")
problems = []
if not os.path.isfile(SAVE):
    print("RESULT: SKIP (no save with the party in a dungeon: tests/dqix_dungeon.sav or TEST_SAVE)"); sys.exit(2)

ops = None
for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
    if line.startswith("entry\t"):
        d = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
        if d["id"] == "live:challenge:noabilities":
            ops = [tuple(int(v, 16) for v in o.split(":")) for o in d["ops"].split(",")]
            if d.get("mode") != "always":
                problems.append("the entry must be 'always' (is %s)" % d.get("mode"))
if ops != [(0x02F5A628, 1)]:
    problems.append("catalog entry live:challenge:noabilities must write 02F5A628 = 1 (has %s)" % ops)


def run(tag, on):
    d = os.path.join(work, "noabil-" + tag); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(SAVE, os.path.join(d, "test.sav"))
    inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90)) + (";" + KEYS if KEYS else "")
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
               DQIX_MODLOG="1", DQIX_MOD_FORCE="3", DQIX_INPUT=inp, DQIX_FAST="1")   # FAST: no 60 fps pacing
    log = open(os.path.join(d, "run.log"), "wb")
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                         cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    box = None
    for _ in range(400):
        try:
            b = mmap.mmap(-1, MB + RING * 2, tagname=f"Local\\dqix-mod-cheats-{p.pid}", access=mmap.ACCESS_WRITE)
            if struct.unpack_from("<I", b, 0)[0] == 0x43584451:
                box = b; break
            b.close()
        except OSError:
            pass
        time.sleep(0.05)
    if box is None:
        p.kill(); problems.append("%s: no mailbox (is the game built with the mods?)" % tag); return ""
    u = lambda off: struct.unpack_from("<I", box, off)[0]
    if on and ops:                                         # the switch on from before the battle, as the Challenges page keeps it (mode "always")
        while u(28) < 4000 and p.poll() is None:
            time.sleep(0.005)
        words = [7] + [w for a, v in ops for w in (a & 0xFFFF, a >> 16, v & 0xFFFF, v >> 16)]
        w = u(8)
        for x in [2 << 12 | len(words)] + words:
            struct.pack_into("<H", box, MB + (w % RING) * 2, x); w += 1
        struct.pack_into("<I", box, 8, w)
    try:
        p.wait(timeout=900)
    except subprocess.TimeoutExpired:
        p.kill(); problems.append("%s: the game did not finish" % tag)
    log.close()
    return open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()


out = {}
runs = [threading.Thread(target=lambda tag=tag, on=on: out.__setitem__(tag, run(tag, on))) for tag, on in (("off", False), ("on", True))]
[r.start() for r in runs]; [r.join() for r in runs]
off, on = out.get("off", ""), out.get("on", "")
pat = re.compile(r"mod: no abilities: party member (\d)'s ability (\d+) became Defend")
if pat.search(off):
    problems.append("switch OFF but an ability became Defend: " + pat.search(off).group(0))
hits = pat.findall(on)
if not hits:
    problems.append("switch ON but no ability became Defend (no ability was picked in the battle? NOABIL_KEYS=%r)" % KEYS)
for who, n in hits:
    if not 63 <= int(n) <= 201:
        problems.append("ability number %s outside the skill trees' 63..201" % n)
for tag, out in (("off", off), ("on", on)):
    if re.search(r"Assertion|Segmentation|access violation|abort\(", out):
        problems.append("%s: the game crashed or asserted" % tag)
print("abilities turned into Defend with the switch on:", hits, "| with it off:", pat.findall(off))
print("RESULT: PASS" if not problems else "RESULT: FAIL (" + "; ".join(problems) + ")")
sys.exit(0 if not problems else 1)
