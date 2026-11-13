#!/usr/bin/env python3
"""Write every mod and cheat in this folder as Action Replay DS codes for the
ROM the game was built from: mods/system/AR-codes-EU.txt (European ROM, YDQP) or
mods/system/AR-codes-USA.txt (YDQE).

  make_ar_list.py [project folder]

The live cheats (mods/cheats) are Action Replay codes already and change
data, which is at the same addresses in both versions: they are copied as
they are. The code mods (mods/system/cheats) change instructions. Those in an overlay
are at the same address in both versions; those in the main program are 16
bytes further on in the European ROM (8 for a few near the start). Each is
written for this ROM, with the instruction that is there now read from the
ROM itself as the code's "only if" line, so a code can't write into the wrong
game. A mod whose instructions aren't in this ROM is left out and named.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_code_mods as acm


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    extract = os.path.join(root, "build", "extract")
    if not os.path.isfile(os.path.join(extract, "arm9", "arm9.bin")):
        print("   The game hasn't been built yet (no build\\extract).")
        return 1
    region = "usa"
    try:
        region = open(os.path.join(root, "build", "obj", "region.txt")).read().strip() or "usa"
    except OSError:
        pass
    eur = region == "eur"
    shifts = acm.eur_shifts(root) if eur else []

    def to_rom(a):
        for lo, hi, sh in shifts:
            if lo <= a < hi:
                return a + sh
        return a

    modules = acm.load_modules(extract)
    out = []
    w = out.append
    w(f"Dragon Quest IX: Sentinels of the Starry Skies ({'Europe, YDQP' if eur else 'USA, YDQE'})")
    w("Action Replay DS codes for everything in this mods folder")
    w("=" * 60)
    w("Made by mods\\system\\tools\\make_ar_list.py from your own ROM's code: every code that")
    w("changes an instruction was checked against it. In DQIX Enhanced you don't type")
    w("these in: use the files in mods\\cheats and mods\\system\\code. This list is for a real")
    w("Action Replay, or an emulator's cheat list.")
    w("")
    w("")
    w("CODES THAT CHANGE THE GAME'S CODE  (mods\\system\\cheats)")
    w("-" * 60)
    left_out, n_entries = [], 0
    live_files, code_files = acm.hand_files(root)
    for f in code_files:
        name, _, checks, patches, errors = acm.parse_mod(f)
        if errors:
            left_out.append((name, "; ".join(errors)))
            continue
        fits = []
        for m in modules:
            # (a mod may also give a European ROM's own main-program addresses: apply_code_mods.py)
            for ra in ([to_rom, lambda a: a] if m.name == "main" and eur else [to_rom if m.name == "main" else (lambda a: a)]):
                if all(m.word(ra(a)) == v for a, v in checks) and all(m.word(ra(a)) is not None for a, _ in patches):
                    fits.append((m, ra))
                    break
        if not fits:
            left_out.append((name, "its instructions aren't in this ROM"))
            continue
        m, ra = fits[0]
        w(f"{name}    [{'main program' if m.name == 'main' else 'overlay ' + str(int(m.name[2:]))}; {os.path.basename(f)}]")
        first = checks[0][0]              # the mod's own "must be there" line, or its first changed instruction
        w(f"5{ra(first) & 0x0FFFFFFF:07X} {m.word(ra(first)):08X}")
        n_entries += 1
        for a, v in patches:
            w(f"0{ra(a) & 0x0FFFFFFF:07X} {v:08X}")
        w("D2000000 00000000")
        w("")
    w("")
    w("CODES THAT CHANGE DATA  (mods\\system\\cheats; the same in the USA and European versions)")
    w("-" * 60)
    for f in live_files:
        base = os.path.basename(f)
        name, mode, lines = base[:-4], "always", []
        for line in open(f, encoding="utf-8-sig"):
            s = line.strip()
            if s.startswith("#"):
                k, _, v = s.lstrip("# ").partition(":")
                if k.strip().lower() == "name":
                    name = v.strip()
                if k.strip().lower() == "mode":
                    mode = v.strip().lower()
                continue
            p = s.split()
            if len(p) == 2 and all(len(x) == 8 for x in p):
                lines.append(f"{p[0].upper()} {p[1].upper()}")
        if not lines:
            continue
        has_key = any(l.startswith("94000130") for l in lines)
        note = "" if mode != "once" else ("  (press SELECT)" if has_key else "  (switch it on, then off again: it only has to run once)")
        w(f"{name}{note}    [{base}]")
        n_entries += 1
        out.extend(lines)
        w("")
    if left_out:
        w("")
        w("LEFT OUT")
        w("-" * 60)
        for name, why in left_out:
            w(f"{name}: {why}")
    path = os.path.join(root, "mods", "system", f"AR-codes-{'EU' if eur else 'USA'}.txt")
    text = "\r\n".join(out) + "\r\n"
    old = None
    try:
        old = open(path, encoding="utf-8", newline="").read()
    except OSError:
        pass
    if old != text:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    print(f"   {os.path.basename(path)}: {n_entries} codes" + (f", {len(left_out)} left out" if left_out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
