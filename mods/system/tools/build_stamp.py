#!/usr/bin/env python3
"""Does the game that is built have the mods in it that are switched on now?

  build_stamp.py [project folder] check    exit 0 = yes, 10 = no: rebuild
  build_stamp.py [project folder] write    after a build that worked: remember what went in

What goes into a build from the mods: the code mods' lines in patches.txt and
the mods' own part of the game (runtime/mod_cheats.c, ar_engine.h, mod_menu.c and the
marked places in input.c, card.c, menu_win32.c, frontend_sdl.c, update.c). mods/system/bin/built.txt keeps a checksum of those, and which code mods
they were (the Cheats window shows "needs a rebuild" from it). Without this, a
build that failed half-way would be taken for done the next time.
"""
import hashlib
import os
import re
import sys

BEGIN = "# >>> mods"
END = "# <<< mods"


def now(root):
    h = hashlib.sha1()
    block = ""
    try:
        text = open(os.path.join(root, "patches.txt"), encoding="utf-8").read().replace("\r\n", "\n")
        m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), text, flags=re.S)
        block = m.group(0) if m else ""
    except OSError:
        pass
    h.update(block.encode("utf-8"))
    for name in ("mod_cheats.c", "ar_engine.h", "mod_menu.c", "mod_data.c", "nuzlocke.c", "lowexp.c", "vanish.c", "noflee.c", "firststrike.c", "livepatch.c", "mod_cheatwin.c", "mod_livepatch_tab.c"):
        try:
            h.update(open(os.path.join(root, "runtime", name), "rb").read().replace(b"\r\n", b"\n"))
        except OSError:
            h.update(b"-")
    try:                                                   # the mods' lines in wrap.txt (which game functions are wrapped)
        w = open(os.path.join(root, "wrap.txt"), encoding="utf-8").read().replace("\r\n", "\n")
        m = re.search(re.escape(BEGIN) + r".*?" + re.escape(END), w, flags=re.S)
        h.update((m.group(0) if m else "").encode("utf-8"))
    except OSError:
        pass
    for name in ("input.c", "card.c", "menu_win32.c", "frontend_sdl.c", "update.c"):   # is each place in the game patched?
        try:
            h.update(b"1" if b">>> mods" in open(os.path.join(root, "runtime", name), "rb").read() else b"0")
        except OSError:
            h.update(b"?")
    ids = [m.group(1) for m in re.finditer(r"^# (\S+) \| ", block, flags=re.M)]
    return h.hexdigest(), ids


def main():
    args = sys.argv[1:]
    what = args[-1] if args else "check"
    root = os.path.abspath(args[0] if len(args) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    path = os.path.join(root, "mods", "system", "bin", "built.txt")
    stamp, ids = now(root)
    if what == "write":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"stamp {stamp}\n" + "".join(f"code {i}\n" for i in ids))
        return 0
    try:
        built = open(path, encoding="utf-8").readline().split()[1]
    except (OSError, IndexError):
        built = ""
    if built != stamp or not os.path.isfile(os.path.join(root, "game", "dqix.exe")):
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
