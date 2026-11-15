#!/usr/bin/env python3
"""Put the code mods that are on (mods/system/cheats/*.txt) into the game's build.

  apply_code_mods.py [project folder]

The recompiler already has a way to change single ARM instructions while
translating the game: patches.txt (the project removes an anti-piracy trap
with it). This adds the code mods there, between two marker lines, and takes
out the ones that are off. An update of the game brings a fresh patches.txt
without them; running this again (Apply.bat does, every time) puts
them back.

Which mods: the files in mods/system/cheats that say "enabled: yes", and the codes from
the cheat database that are switched on in the Cheats window (mods/system/menu-state.txt).
catalog.py works every one of them out against your ROM's code (build/extract,
written by the last build), so a mod that doesn't fit your ROM, or that can't be
checked, is left out rather than breaking the game.

Exit code: 0 = nothing changed, 10 = patches.txt changed (rebuild the game),
1 = something is wrong.
"""
import glob
import os
import re
import struct
import sys

# the marker is found by its exact text in games that have it: never reword it (it names the patcher's old name)
BEGIN = "# >>> mods (added by mods/tools/apply_code_mods.py; an update removes this, Play with mods.bat puts it back)"
END = "# <<< mods"

# USA main-module address -> European (tools/region.py's table, if it's not there)
EUR_SHIFTS_FALLBACK = [(0x0200F3B8, 0x0200FB20, 0x08), (0x0200FB20, 0x020EEBD0, 0x10)]


def eur_shifts(root):
    sys.path.insert(0, os.path.join(root, "tools"))
    try:
        import region
        return region.EUR_SHIFTS
    except Exception:
        return EUR_SHIFTS_FALLBACK
    finally:
        sys.path.pop(0)


def simple_yaml_overlays(path):
    """overlays.yaml as written by tools/extract_rom.py: id, base_address, file_name."""
    out, cur = [], None
    for line in open(path):
        m = re.match(r"\s*-?\s*(\w+):\s*(\S+)", line)
        if not m:
            continue
        k, v = m.groups()
        if line.lstrip().startswith("- "):
            cur = {}
            out.append(cur)
        if cur is not None:
            cur[k] = v
    return out


def yaml_value(path, key):
    for line in open(path):
        m = re.match(rf"\s*{key}:\s*(\S+)", line)
        if m:
            return int(m.group(1), 0)
    raise KeyError(key)


class Module:
    def __init__(self, name, base, data):
        self.name, self.base, self.data = name, base, data

    def word(self, addr):
        o = addr - self.base
        if o < 0 or o + 4 > len(self.data) or o % 4:
            return None
        return struct.unpack_from("<I", self.data, o)[0]


def load_modules(extract):
    mods = [Module("main", yaml_value(os.path.join(extract, "arm9/arm9.yaml"), "base_address"),
                   open(os.path.join(extract, "arm9/arm9.bin"), "rb").read())]
    for ov in simple_yaml_overlays(os.path.join(extract, "arm9_overlays/overlays.yaml")):
        if "id" not in ov:
            continue
        mods.append(Module(f"ov{int(ov['id']):03d}", int(ov["base_address"], 0),
                           open(os.path.join(extract, "arm9_overlays", ov["file_name"]), "rb").read()))
    return mods


# The Nuzlocke page is not finished: off for now. The code (src/runtime/nuzlocke.c, the catalog entries, cheats/nuzlocke-*.txt, the menu text in
# apply_runtime_mod.py) is all still here; set this to True in apply_code_mods.py AND apply_runtime_mod.py and rebuild to bring it back.
NUZLOCKE_ENABLED = False


def hand_files(root):
    """-> (live cheat files, code mod files) of mods/system/cheats, told apart by their content:
    a file with "patch <address> <word>" lines changes the game's code, any other is a live cheat.
    r4-*.txt (the R4 database) and files starting with _ are not hand-made."""
    live, code = [], []
    for f in sorted(glob.glob(os.path.join(root, "mods", "system", "cheats", "*.txt"))):
        base = os.path.basename(f)
        if base.startswith("_") or base.lower().startswith("r4-") or (not NUZLOCKE_ENABLED and base.startswith("nuzlocke-")):
            continue
        is_code = any(re.match(r"patch\s", l.strip()) for l in open(f, encoding="utf-8-sig"))
        (code if is_code else live).append(f)
    return live, code


def parse_mod(path):
    name, on, checks, patches, errors = os.path.basename(path)[:-4], False, [], [], []
    for n, line in enumerate(open(path, encoding="utf-8-sig"), 1):
        s = line.strip()
        if s.startswith("#"):
            m = re.match(r"#\s*(\w+)\s*:\s*(.*)", s)
            if m and m.group(1).lower() == "name":
                name = m.group(2).strip()
            if m and m.group(1).lower() == "enabled":
                on = m.group(2).strip().lower() in ("yes", "y", "on", "true", "1")
            continue
        p = s.split("#")[0].split()
        if not p:
            continue
        try:
            if p and p[-1].startswith("@"):                    # @module: see mod_tags
                p = p[:-1]
            if p[0].lower() == "check" and len(p) == 3:
                checks.append((int(p[1], 16), int(p[2], 16)))
            elif p[0].lower() == "patch" and len(p) == 4:      # patch <addr> <old> <new>
                a = int(p[1], 16)
                checks.append((a, int(p[2], 16)))
                patches.append((a, int(p[3], 16)))
            elif p[0].lower() == "patch" and len(p) == 3:      # patch <addr> <new> (needs a check)
                patches.append((int(p[1], 16), int(p[2], 16)))
            else:
                errors.append(f"line {n}: not understood: {s}")
        except ValueError:
            errors.append(f"line {n}: not a hex number: {s}")
    if patches and not checks:
        errors.append("no 'check' line: a mod has to say what it expects to find")
    return name, on, checks, patches, errors


def mod_tags(path):
    """{address: module name} for the lines of a hand-made code mod that end in @main / @ov002 ...: a mod that changes several
    modules of the game (the checks and patches of a tag are looked for in that module only)"""
    out = {}
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if s.startswith("#"):
            continue
        p = s.split("#")[0].split()
        if len(p) >= 3 and p[0].lower() in ("check", "patch") and p[-1].startswith("@"):
            try:
                out[int(p[1], 16)] = p[-1][1:]
            except ValueError:
                pass
    return out


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    patches_txt = os.path.join(root, "patches.txt")
    if not os.path.isfile(patches_txt):
        print("   No patches.txt here: is this the DQIX Enhanced folder?", root)
        return 1
    if not os.path.isfile(os.path.join(root, "build", "recomp", "dispatch_table.c")):
        print("   The game hasn't been built yet (no build\\recomp): build it once, then run this again.")
        return 1
    # Which mods are on: a file in mods\system\cheats says so itself ("enabled: yes"); a code from the
    # database is on when the Cheats window's state file (mods\system\menu-state.txt) names it. catalog.py has
    # worked each one out against this ROM: only instructions it found there get this far.
    import catalog
    rom = catalog.Rom(root)
    _, entries, _ = catalog.build(root)
    chosen = catalog.read_state(root)["code"]
    lines, used = [], {}
    for e in entries:
        on = e["on"] if e["file"] else e["id"] in chosen
        if not on or e["kind"] not in ("code", "blocked") or e["id"].startswith("launch:"):
            continue
        if e["kind"] == "blocked":
            if e["file"]:
                print(f"   [skipped] {e['name']}: {e['reason']}")
            continue
        clash = [k for k in ((n, a) for n, a, w in e["patch"]) if k in used and used[k][0] != dict(((n, a), w) for n, a, w in e["patch"])[k]]
        if clash:
            print(f"   [skipped] {e['name']}: changes the same instruction as \"{used[clash[0]][1]}\" (turn one of them off)")
            continue
        lines.append(f"# {e['id']} | {e['name']}")
        for n, a, w in e["patch"]:
            if (n, a) not in used:
                # patches.txt takes the USA version's addresses (region.py moves the main program's)
                lines.append(f"{n} {rom.from_rom(a) if n == 'main' else a:08x} {w:08x}")
            used[(n, a)] = (w, e["name"])
        print(f"   [on] {e['name']}")
    if not lines:
        print("   No code mods are on.")

    text = open(patches_txt, encoding="utf-8").read()
    if not lines and BEGIN not in text:
        return 0
    stripped = re.sub(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "\n", text, flags=re.S)
    stripped = stripped.rstrip("\n") + "\n"
    new = stripped + ("\n" + BEGIN + "\n" + "\n".join(lines) + "\n" + END + "\n" if lines else "")
    if new != text:
        with open(patches_txt, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        print("   The code mods changed: the game will be rebuilt (only what changed).")
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
