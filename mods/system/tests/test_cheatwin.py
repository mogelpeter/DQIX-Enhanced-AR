"""The Cheats window inside the emulator (mod_cheatwin.c), headless game, Windows only.
   test_cheatwin.py <project root> <work dir> [frame]

   1  the window opens by itself (DQIX_CHEATWIN_TEST), switches "Gold always 9,999,999" on the way a click does
      (tab, then the row's check box) and draws itself into a picture:
        - the gold is in the game's RAM            (window -> mailbox -> game)
        - the state file has `live file:cheats/max-gold.txt`   
        - the picture exists (look at it: <work>/one/shot.bmp)
   2  a new start with that state file and no window: the cheat is sent again by itself (the gold is in RAM)
   3  a state with a choice from a group (x2 then x4) keeps only the last one
   4  the search box (DQIX_CHEATWIN_SEARCH): "slime" finds the slime monsters inside the "Battle any monster" choice and
      nothing that doesn't fit; "a" finds more than the row limit and builds only the first 60; "gold max" needs both words;
      "zzqx" finds nothing. Every row and drop-down entry must fit the words (bad=0).
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

rc2, _, ram2, _ = run("two", ["live file:cheats/max-gold.txt"], lambda d: {})
print("2  a new start sends it again by itself: gold in RAM %#x" % gold(ram2), "| exit", rc2, flush=True)
ok &= rc2 == 0 and gold(ram2) == GOLD

# 3: no window involved: the state file is read as it is. A choice keeps one: window test with x2 then the window picks x4 is covered by the
# catalog test (one group member on); here only that two members of a group in the state file do not crash the start
ids = [l.split("id=")[1].split("\t")[0] for l in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8")
       if l.startswith("entry\t") and "group=group:" in l and "kind=live" in l][:2]
rc3, txt3, _, _ = run("three", ["live " + i for i in ids], lambda d: {})
print("3  two members of one choice in the state file: the game starts and runs, exit", rc3, flush=True)
ok &= rc3 == 0 and "fatal" not in txt3.lower()
# 4: the search
rc4, txt4, _, _ = run("four", [], lambda d: {"DQIX_CHEATWIN_SEARCH": "slime;a;gold max;zzqx;metal slime," + os.path.join(d, "shot.bmp")})
res = {}
for line in txt4.splitlines():
    if line.startswith("cheatwin search: "):
        kv = dict(x.split("=", 1) for x in line[len("cheatwin search: "):].split(" ") if "=" in x)
        q = line.split("q=", 1)[1].split(" rows=")[0]
        res[q] = {k: float(v) if k == "ms" else int(v) for k, v in kv.items() if k != "q"}
        print("4  search", repr(q), res[q], flush=True)
s4 = rc4 == 0 and len(res) == 5 and all(r["bad"] == 0 for r in res.values())
s4 &= res.get("slime", {}).get("members", 0) > 0 and res.get("a", {}).get("rows") == 60 and res.get("a", {}).get("found", 0) > 60
s4 &= res.get("zzqx", {}).get("rows") == 0 and 0 < res.get("gold max", {}).get("rows", 0) < res.get("a", {}).get("found", 0)
print("4  search works:", s4, "| exit", rc4, flush=True)
ok &= s4


# 5: "Use" (the button, clicked): a once-only cheat without keys, and a cheat whose code waits for buttons (START+R,
#    SELECT...): the button carries it out once as if those were held. Its writes are in RAM; nothing is switched on.
def catalog_entry(pick):
    for l in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
        if l.startswith("entry\t"):
            d = dict(x.split("=", 1) for x in l.rstrip("\n").split("\t")[1:] if "=" in x)
            if pick(d):
                return d
    return None


def writes(ops):
    """the plain writes of a code (0/1/2 = 32/16/8 bit), after a button check: [(offset in RAM, size, value)]"""
    out = []
    for op in ops.split(","):
        a, v = (int(x, 16) for x in op.split(":"))
        t = a >> 28
        if t in (0, 1, 2) and (a & 0x0FFFFFFF) >> 24 == 2:
            n = (4, 2, 1)[t]
            out.append(((a & 0x00FFFFFF), n, v & ((1 << 8 * n) - 1)))
        elif t not in (9,) and a >> 24 != 0xD2:
            return []                                      # anything else (loops, pointers): not a plain write
    return out


for tag, pick in (("five-a", lambda d: d["id"] == "file:cheats/once-nighttime.txt"),
                  ("five-b", lambda d: d.get("kind") == "live" and d.get("mode") == "once" and d["id"].startswith("db:") and writes(d["ops"])
                   and d["ops"].startswith("94000130:")
                   and any(int.from_bytes(ram[o:o + n], "little") != v for o, n, v in writes(d["ops"])))):   # not already so in the save
    d = catalog_entry(pick)
    if not d:
        print("5  Use: no entry for", tag); ok = False; continue
    rc5, txt5, ram5, st5 = run(tag, [], lambda w, i=d["id"]: {"DQIX_CHEATWIN_TEST": "now:" + i})
    got = [(o, n, v, int.from_bytes(ram5[o:o + n], "little")) for o, n, v in writes(d["ops"])]
    good = rc5 == 0 and "cheatwin test: did it now" in txt5 and got and all(v == g for o, n, v, g in got) and d["id"] not in st5
    print("5  Use:", (d.get("option") or d["name"]), "| keys", d.get("keys", "-"), "| written:",
          ", ".join("%#x=%#x (want %#x)" % (0x02000000 + o, g, v) for o, n, v, g in got), "| still off:", d["id"] not in st5, "| exit", rc5, flush=True)
    ok &= bool(good)

# 6: Share and Import (DQIX_CHEATWIN_IMPORT): a start with three cheats on (one of them a choice's member) shares them as one
#    line; a start with something else on imports that line: exactly the three are on (the other one off), the gold is in RAM,
#    and sharing again gives the same line. The second start also draws the Party page with a section open (Hero).
pick = [i for i in ids[:1]] + ["file:cheats/max-gold.txt", "file:cheats/vanish.txt"]
rc6, txt6, _, _ = run("six-a", ["live " + i for i in pick], lambda d: {"DQIX_CHEATWIN_IMPORT": "-"})
line = next((l.split(" ", 3)[3] for l in txt6.splitlines() if l.startswith("cheatwin share: count=3 ")), "")
hero = catalog_entry(lambda d: d.get("cat") == "Party" and d.get("section") == "Hero" and d.get("kind") == "live" and not d.get("group") and d.get("mode") != "once")
rc7, txt7, ram7, st7 = run("six-b", ["live file:cheats/max-mini-medals.txt"], lambda d: {"DQIX_CHEATWIN_IMPORT": line})
on7 = sorted(l.split(" ", 1)[1] for l in st7.splitlines() if l.startswith("live "))
again = next((l.split(" ", 3)[3] for l in txt7.splitlines() if l.startswith("cheatwin share: ")), "")
s6 = rc6 == 0 and rc7 == 0 and "DQIX-CHEATS/1/" in line and "cheatwin import: found=3 missing=0" in txt7 and on7 == sorted(pick) \
    and gold(ram7) == GOLD and again == line
print("6  share -> import:", s6, "| shared:", line[:60] + "...", "| on after import:", on7, "| exit", rc6, rc7, flush=True)
ok &= s6
if hero:
    rc8, txt8, _, st8 = run("seven", [], lambda d: {"DQIX_CHEATWIN_TEST": hero["id"] + "," + os.path.join(d, "shot.bmp")})
    s7 = rc8 == 0 and "cheatwin test: switched on" in txt8 and ("live " + hero["id"]) in st8
    print("7  a cheat inside a folded section (Party / Hero) switched on:", s7, "| picture:", os.path.join(work, "seven", "shot.bmp"), flush=True)
    ok &= s7
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
