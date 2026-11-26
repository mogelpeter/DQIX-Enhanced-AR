#!/usr/bin/env python3
"""Does the game that is built have the mods in it that are switched on now?

  build_stamp.py [project folder] check    exit 0 = yes, 10 = no: rebuild
  build_stamp.py [project folder] write    after a build that worked: remember what went in
  build_stamp.py [project folder] editor-check | editor-write    the same for the save editor's helper

What goes into a build from the mods: the code mods' lines in patches.txt and
the mods' own part of the game (runtime/mod_cheats.c, ar_engine.h, mod_menu.c, every file of mods/system/src/runtime), and
the game's files with the marked places (input.c, card.c, menu_win32.c, frontend_sdl.c, update.c, session.c) plus its
version.h and menu.h. mods/system/bin/built.txt keeps a checksum of those, and which code mods
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
    names = ["mod_cheats.c", "ar_engine.h", "mod_menu.c", "mod_data.c", "nuzlocke.c", "lowexp.c", "vanish.c", "noflee.c", "firststrike.c", "livepatch.c", "mod_cheatwin.c", "mod_livepatch_tab.c"]
    # and every other file the mods put into runtime/ (forcebtl.c, challenges.c, ...): a change to one of them alone has to rebuild too
    try:
        names += sorted(n for n in os.listdir(os.path.join(root, "mods", "system", "src", "runtime"))
                        if n.endswith((".c", ".h")) and n not in names)
    except OSError:
        pass
    for name in names:
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
    # the game's own files the mods patch (with their places in them), its version and its menu numbers: an update of the game
    # changes them, and then Apply.bat has to build (repatch.py leaves out a place the new game doesn't build with)
    for name in ("input.c", "card.c", "menu_win32.c", "frontend_sdl.c", "update.c", "session.c", "version.h", "menu.h"):
        try:
            h.update(open(os.path.join(root, "runtime", name), "rb").read().replace(b"\r\n", b"\n"))
        except OSError:
            h.update(b"?")
    ids = [m.group(1) for m in re.finditer(r"^# (\S+) \| ", block, flags=re.M)]
    return h.hexdigest(), ids


def editor(root, what):
    """editor-check: exit 0 = mods/system/bin/dqix-editor.exe was made from this EditorHost.cs, 10 = make it;
    editor-write: remember what it was made from. By content: the release zip's file dates say nothing."""
    bindir = os.path.join(root, "mods", "system", "bin")
    with open(os.path.join(root, "mods", "system", "src", "editor", "EditorHost.cs"), "rb") as f:
        src = hashlib.sha1(f.read().replace(b"\r\n", b"\n")).hexdigest()
    path = os.path.join(bindir, "editor-built.txt")
    if what == "editor-write":
        os.makedirs(bindir, exist_ok=True)
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(src + "\n")
        return 0
    try:
        built = open(path, encoding="ascii").read().strip()
    except OSError:
        built = ""
    return 0 if built == src and os.path.isfile(os.path.join(bindir, "dqix-editor.exe")) else 10


def main():
    args = sys.argv[1:]
    what = args[-1] if args else "check"
    root = os.path.abspath(args[0] if len(args) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if what.startswith("editor-"):
        return editor(root, what)
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
