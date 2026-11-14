"""The cheat "Zoom Then Push [R] to Grotto Cave Location", end to end in a headless game (Windows).

   test_zoom_grotto.py <project root> <work dir>

What the cheat does (cheats/r4-*.txt, Grotto Caves Code): while R is held and the game is in treasure-map mode
(020F97BC = 0x0101, the "Put Map Away" state), it copies the map's grotto location (020F97C8: map id, x, y, z) into the
warp destination that Zoom and Evac fly to (020F37D0, 37E0..37E8). A treasure map can't be had in a headless test save,
so a second cheat stands in for treasure-map mode with Stornway's location as "the grotto". Two runs at once:
   on   the party casts Evac (out of Guarantomb), then Zoom to ZERE while holding R, with the cheat on -> lands in Stornway
   off  the same without the cheat                                                                  -> lands in Zere
Needs TEST_SAVE = the dungeon save of NOTES 2026-11-14 (hero in Guarantomb, knows Evac and Zoom). Slow: about 2 minutes."""
import concurrent.futures as cf, mmap, os, shutil, struct, subprocess, sys, time

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE") or os.path.join(root, "game", "dqix.sav")
STORNWAY = (0x00004E22, 0xFFFD8800, 0x000012E1, 0xFFFF1800)        # Zoom's destination record for Stornway (map id, x, y, z)
ops_b = None
for line in open(os.path.join(root, "mods", "system", "bin", "catalog.txt"), encoding="utf-8"):
    if line.startswith("entry\t") and ("id=db:933b3879\t" in line or "Grotto Cave Location\t" in line):    # EU id / the USA list's name
        d = dict(x.split("=", 1) for x in line.rstrip("\n").split("\t")[1:] if "=" in x)
        ops_b = [tuple(int(x, 16) for x in o.split(":")) for o in d["ops"].split(",")]
if not ops_b:
    print("RESULT: FAIL (the cheat db:933b3879 is not in the catalog)"); sys.exit(1)
ops_a = [(0x120F97BC, 0x0101)] + [(0x020F97C8 + 4 * i, v) for i, v in enumerate(STORNWAY)]
EV = "3700:X:6;3780:RIGHT:6;3830:A:6;3900:A:6;3960:DOWN:6;4000:DOWN:6;4060:A:6;4200:A:6;4300:A:6"          # Evac
ZM = "4700:X:6;4780:RIGHT:6;4830:A:6;4900:A:6;4980:A:6;5060:DOWN:6;5140:A:6;5150:R:200;5400:A:6"          # Zoom to Zere, R held
INP = "700:DOWN:6;800:A:6;" + ";".join("%d:A:6" % f for f in range(900, 3400, 90)) + ";" + EV + ";" + ZM
RING, MB = 8192, 32


def run(tag, cheats):
    d = os.path.join(work, tag); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ, DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1",
               DQIX_NO_RELAY="1", DQIX_INPUT=INP, DQIX_RAMDUMP=".,6160")
    env.pop("NoDefaultCurrentDirectoryInExePath", None)
    p = subprocess.Popen([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), "6200", "1", "test.sav"],
                         cwd=d, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        p.kill(); return None
    u = lambda off: struct.unpack_from("<I", box, off)[0]
    while u(28) < 4400 and p.poll() is None:                      # outside after Evac, before Zoom
        time.sleep(0.01)
    for cid, ops in cheats:
        words = [cid]
        for a, v in ops:
            words += [a & 0xFFFF, a >> 16, v & 0xFFFF, v >> 16]
        msg = [2 << 12 | len(words)] + words
        wp = u(8)
        for x in msg:
            struct.pack_into("<H", box, MB + (wp % RING) * 2, x); wp += 1
        struct.pack_into("<I", box, 8, wp)
    p.wait(timeout=900)
    try:
        r = open(os.path.join(d, "ram006160.bin"), "rb").read()
    except OSError:
        return None
    dest = struct.unpack_from("<I", r, 0x0F37D0)[0], struct.unpack_from("<3I", r, 0x0F37E0)
    return (dest[0],) + dest[1]


with cf.ThreadPoolExecutor(2) as ex:
    on = ex.submit(run, "on", [(90, ops_a), (91, ops_b)])
    off = ex.submit(run, "off", [(90, ops_a)])
    on, off = on.result(), off.result()
fmt = lambda t: "none" if t is None else " ".join("%08x" % x for x in t)
print("with the cheat:    destination", fmt(on), "(Stornway is", fmt(STORNWAY) + ")")
print("without the cheat: destination", fmt(off))
ok = on == STORNWAY and off is not None and off != STORNWAY
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
