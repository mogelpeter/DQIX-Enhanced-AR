"""The Nuzlocke rules (nuzlocke.c) in a real game, headless, Windows. Works on the European and the USA game alike (the party's RAM is at the same
addresses in both); the game folder is <project root>\\game.

   test_nuzlocke.py <project root> <work dir> <scenario> [--keep]

The game is started with a save that has a party of three in a dungeon (TEST_SAVE, default: game\\dqix.sav), the rules are sent through the cheat
mailbox the way the Cheats window does, and the party is hurt and "revived" with one-off codes. The RAM at fixed frames and the run log tell what
the rules did. Scenarios:
   control   no rule on: a member at 0 HP and then at 50 HP stays at 50 (the test's own revive works)
   perma     Permadeath: member 2 falls, the code that revives it is undone every frame; the others live; nuzlocke-run.txt has one name
   persist   (after perma, same work dir) the game starts again: member 2 is dead from the first frame, nobody fell this time
   link      Permadeath + soul link: member 2 falls, member 1 (the pair) falls with it, member 3 lives
   hero      Permadeath + the hero ends the run: the hero falls, everybody falls
   goldhalf  Permadeath + lose half the gold: 1000 gold -> 500 after a death
   goldall   Permadeath + lose all gold
   battle    Permadeath, a whole battle (every roamer a metal slime, DQIX_MOD_FORCE=3): nobody falls by mistake while the battle starts, runs and ends
   battleko  Permadeath, in a battle: member 2's battle HP is set to 0, then to 50 again; it falls once and stays at 0 (the battle's own copy at +0x5C)
   newrun    Permadeath, member 2 falls, then "Start a new run": the 50 HP of the next revive stay, the run file is gone
Prints RESULT: PASS / FAIL."""
import mmap, os, re, shutil, struct, subprocess, sys, time

root, work, scen = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
RING, MB = 8192, 32
B = 0x02000000
BASE = [0x020F54B4 - i * 0x964 for i in range(4)]            # a party member's record (his name); the field HP is 0x30 into it
GOLD = 0x020F6D48
SW = {"perma": 0x02F5A5C0, "hero": 0x02F5A5C4, "link": 0x02F5A5C8, "half": 0x02F5A5CC, "all": 0x02F5A5D0, "new": 0x02F5A5FC}
RULES = {"battle": ["perma"], "battleko": ["perma"], "control": [], "perma": ["perma"], "persist": ["perma"], "link": ["perma", "link"], "hero": ["perma", "hero"],
         "goldhalf": ["perma", "half"], "goldall": ["perma", "all"], "newrun": ["perma"]}
if scen not in RULES:
    print("RESULT: FAIL (unknown scenario %s)" % scen); sys.exit(1)

if scen == "persist" and not os.path.exists(os.path.join(work, "nuzlocke-perma", "nuzlocke-run.txt")):      # needs the dead of "perma": make them
    r = subprocess.run([sys.executable, os.path.abspath(__file__), root, work, "perma"], capture_output=True, text=True, errors="replace")
    if "RESULT: PASS" not in r.stdout:
        print(r.stdout[-800:]); print("RESULT: FAIL (the perma run that persist needs failed)"); sys.exit(1)

T_RULES, T_HURT, T_CHECK1, T_REVIVE, T_CHECK2, T_NEW, T_REVIVE2, T_CHECK3, T_END = 3500, 3700, 3790, 3820, 3920, 3950, 4000, 4100, 4150
dumps = [T_RULES - 20, T_CHECK1, T_CHECK2, T_CHECK3]
if scen in ("battle", "battleko"):
    T_END = 5700; dumps = [T_RULES - 20, 5250, 5450, 5650]


def op16(addr, val):                                           # an Action Replay 16-bit write
    return (0x10000000 | addr, val)


def op32(addr, val):
    return (addr, val)


d = os.path.join(work, "nuzlocke-" + scen if scen != "persist" else "nuzlocke-perma")
if scen != "persist":
    shutil.rmtree(d, ignore_errors=True)
os.makedirs(d, exist_ok=True)
for f in ("test.sav",):
    if scen != "persist":
        shutil.copy(os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav"), os.path.join(d, f))
for old in os.listdir(d):
    if old.startswith("ram"):
        os.remove(os.path.join(d, old))
inp = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
           DQIX_MODLOG="1", DQIX_INPUT=inp, **({"DQIX_MOD_FORCE": "3"} if scen in ("battle", "battleko") else {}), DQIX_RAMDUMP=".," + ",".join(map(str, dumps)))
log = open(os.path.join(d, "run.log"), "wb")
p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(T_END), "1", "test.sav"],
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
    print("RESULT: FAIL (no mailbox: is the game built with the mods?)"); p.kill(); sys.exit(1)
u = lambda off: struct.unpack_from("<I", box, off)[0]


def send(typ, ident, ops):
    words = ([ident] if ident is not None else [])
    for a, v in ops:
        words += [a & 0xFFFF, a >> 16, v & 0xFFFF, v >> 16]
    msg = [typ << 12 | len(words)] + words
    w = u(8)
    for x in msg:
        struct.pack_into("<H", box, MB + (w % RING) * 2, x); w += 1
    struct.pack_into("<I", box, 8, w)


def at(frame, what):                                           # send `what` so that it is carried out by `frame` (16 bits per frame)
    while u(28) < frame and p.poll() is None:
        time.sleep(0.005)
    what()


hp = lambda slot: BASE[slot] + 0x30
at(T_RULES - 80, lambda: send(2, 1, [op32(SW[r], 1) for r in RULES[scen]]) if RULES[scen] else None)
if scen.startswith("gold"):
    at(T_RULES - 40, lambda: send(1, None, [op32(GOLD, 1000)]))
if scen == "battleko":
    at(5150 - 40, lambda: send(1, None, [op16(BASE[1] + 0x5C, 0)]))
    at(5350 - 40, lambda: send(1, None, [op16(BASE[1] + 0x5C, 50)]))
if scen not in ("battle", "battleko"):
  at(T_HURT - 40, lambda: send(1, None, [op16(hp(0 if scen == "hero" else 1), 0)]))           # the hero falls (hero scenario), else member 2
if scen not in ("battle", "battleko"):
  at(T_REVIVE - 20, lambda: send(1, None, [op16(hp(0 if scen == "hero" else 1), 50)]))
if scen == "newrun":
    at(T_NEW - 20, lambda: send(1, None, [op32(SW["new"], 1)]))
    at(T_REVIVE2 - 20, lambda: send(1, None, [op16(hp(1), 50)]))
p.wait(timeout=900); log.close()

log_text = open(os.path.join(d, "run.log"), "rb").read().decode("latin1")
falls = re.findall(r"nuzlocke: party member (\d) falls \(([^)]*)\)", log_text)
runfile = os.path.join(d, "nuzlocke-run.txt")
dead_lines = [l for l in open(runfile).read().splitlines() if l.startswith("dead")] if os.path.exists(runfile) else []


def ram(frame, addr, n=2):
    b = open(os.path.join(d, "ram%06d.bin" % frame), "rb").read()
    return int.from_bytes(b[addr - B:addr - B + n], "little")


names_present = [ram(dumps[0], BASE[i], 1) != 0 for i in range(4)]
problems = []


def expect(cond, text):
    if not cond:
        problems.append(text)


print("scenario %s: falls=%s run file=%d dead; present=%s" % (scen, falls, len(dead_lines), names_present), flush=True)
expect(names_present[0] and names_present[1], "the test save has no party of at least two")
h1 = h2 = h3 = h0 = [0, 0, 0, 0]
if scen not in ("battle", "battleko"):
    h1 = [ram(T_CHECK1, hp(i)) for i in range(4)]
    h2 = [ram(T_CHECK2, hp(i)) for i in range(4)]
    h3 = [ram(T_CHECK3, hp(i)) for i in range(4)]
    print("HP after the fall %s, after the revive %s, last %s" % (h1, h2, h3))
    h0 = [ram(dumps[0], hp(i)) for i in range(4)]
if scen == "battleko":
    bhp = [ram(f, BASE[1] + 0x5C) for f in dumps[1:]]
    print("member 2 battle HP at the dumps:", bhp)
    expect(bhp[0] == 0 or bhp[1] == 0, "the battle KO must show (%s)" % bhp)
    expect(bhp[2] == 0, "the revive to 50 must be undone (%s)" % bhp)
    expect(len(falls) == 1 and falls[0][0] == "2", "exactly member 2 must fall (%s)" % falls)
if scen in ("battle", "battleko"):
    inbattle = [ram(f, BASE[0] + 0x58) != 0 for f in dumps[1:]]
    print("in a battle at the dumps:", inbattle)
    expect(any(inbattle), "no battle was reached (the dungeon save is needed: TEST_SAVE)")
    expect(scen == "battleko" or not falls, "nobody should fall in this battle (%s)" % falls)
if scen == "control":
    expect(not falls and h2[1] == 50, "control: no rule on, the revive to 50 should stay (%s)" % h2)
elif scen in ("perma", "persist"):
    expect(h2[1] == 0 and h3[1] == 0, "member 2 must stay at 0 HP after the revive code (%s %s)" % (h2, h3))
    expect(h2[0] > 0 and h3[0] > 0, "the hero must live (%s)" % h2)
    if scen == "perma":
        expect(len(falls) == 1 and falls[0][0] == "2", "exactly member 2 must fall (%s)" % falls)
        expect(len(dead_lines) == 1, "the run file must name one dead member (%s)" % dead_lines)
    else:
        expect(h0[1] == 0 or h1[1] == 0, "persist: member 2 must be dead from the start (%s)" % h1)
        expect(not falls, "persist: nobody should fall again (%s)" % falls)
elif scen == "link":
    expect(h2[0] == 0 and h2[1] == 0, "member 1 and 2 must both be at 0 (%s)" % h2)
    expect(names_present[2] and h2[2] > 0, "member 3 must live (%s)" % h2)
    expect(any(w == "soul link" for _, w in falls), "the log must say the soul link took member 1 (%s)" % falls)
elif scen == "hero":
    expect(all(h2[i] == 0 for i in range(4) if names_present[i]), "everybody must be at 0 (%s)" % h2)
    expect(any(w == "the hero fell" for _, w in falls), "the log must say the hero fell (%s)" % falls)
elif scen in ("goldhalf", "goldall"):
    g = ram(T_CHECK2, GOLD, 4)
    want = 500 if scen == "goldhalf" else 0
    expect(g == want, "gold must be %d after the death, is %d" % (want, g))
elif scen == "newrun":
    expect(h2[1] == 0, "member 2 must be dead before the new run (%s)" % h2)
    expect(h3[1] == 50, "after Start a new run the revive to 50 must stay (%s)" % h3)
    expect(not os.path.exists(runfile), "the run file must be gone")
print("RESULT: PASS" if not problems else "RESULT: FAIL (" + "; ".join(problems) + ")")
sys.exit(0 if not problems else 1)
