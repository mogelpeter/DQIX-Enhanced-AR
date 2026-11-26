#!/usr/bin/env python3
"""The mods' places in the game's source (incl. the Cheats tab) survive an update of the game.

  test_runtime_patch.py <game folder>

Works on a copy of runtime/ and wrap.txt in the temp folder: ON puts every marked place in, OFF (sync_cheats = no, same as a
fresh update that brought clean files) takes them all out again, ON again must give the exact same files. Nothing in the
game folder is touched.
"""
import os, re, shutil, subprocess, sys, tempfile

root = os.path.abspath(sys.argv[1])
tool = os.path.join(os.path.dirname(__file__), "..", "tools", "apply_runtime_mod.py")
src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
tmp = tempfile.mkdtemp(prefix="dqix-rtpatch-")
try:
    shutil.copytree(os.path.join(root, "runtime"), os.path.join(tmp, "runtime"))
    shutil.copy2(os.path.join(root, "wrap.txt"), tmp)
    shutil.copytree(src_dir, os.path.join(tmp, "mods", "system", "src"))

    def run(setting):
        os.makedirs(os.path.join(tmp, "mods"), exist_ok=True)
        open(os.path.join(tmp, "mods", "settings.txt"), "w").write("sync_cheats = %s\n" % setting)
        p = subprocess.run([sys.executable, "-X", "utf8", tool, tmp], capture_output=True, text=True)
        return p.returncode, p.stdout

    def snap():
        d = {}
        for n in ("input.c", "card.c", "menu_win32.c", "frontend_sdl.c", "update.c", "mod_menu.c", "mod_cheats.c", "noflee.c", "lowexp.c", "firststrike.c"):
            p = os.path.join(tmp, "runtime", n)
            d[n] = open(p, "rb").read() if os.path.isfile(p) else None
        return d

    errors = []
    run("no")                                             # start from clean files, whatever the game folder had
    clean = snap()
    rc, out = run("yes")
    on1 = snap()
    if "[skipped]" in out:
        errors.append("a place was skipped:\n" + out)
    for n in ("input.c", "menu_win32.c", "frontend_sdl.c", "update.c"):
        if b">>> mods" not in (on1[n] or b""):
            errors.append(n + " has no mods marker")
    if on1["mod_menu.c"] is None:
        errors.append("mod_menu.c not put in")
    if b"&Cheats..." not in on1["menu_win32.c"] or b"&Save editor..." not in on1["menu_win32.c"] or b"&Treasure maps..." not in on1["menu_win32.c"]:
        errors.append("the Cheats tab is missing an item in the menu bar (Cheats..., Save editor..., Treasure maps...)")
    if b"case 9364:" not in on1["frontend_sdl.c"] or b"mod_editor_take" not in on1["frontend_sdl.c"] or b"mod_editor_take" not in (on1["mod_menu.c"] or b""):
        errors.append("the game doesn't take the save editor's export (menu command 9364, mod_editor_take)")
    if b"(IntPtr)9364," not in open(os.path.join(src_dir, "editor", "EditorHost.cs"), "rb").read():
        errors.append("the save editor helper doesn't send menu command 9364")
    # the mods' menu numbers must be free in the game's own menu (v34 took 360-363 for Transmog: "duplicate case value")
    header = re.sub(r"/\*.*?\*/", "", open(os.path.join(tmp, "runtime", "menu.h"), encoding="utf-8").read(), flags=re.S)
    taken, value = {}, -1
    for body in re.findall(r"enum\s*\{([^}]*MI_[^}]*)\}", header):
        for item in filter(None, (x.strip() for x in body.split(","))):
            name, _, given = (x.strip() for x in item.partition("="))
            value = int(given, 0) if given else value + 1
            taken[value] = name
    mine = {int(n) for n in re.findall(rb"item\(\w+, (\d+),", on1["menu_win32.c"])}
    for block in re.findall(rb">>> mods:.*?<<< mods", on1["frontend_sdl.c"], re.S):
        mine |= {int(n) for n in re.findall(rb"case (\d+):", block)}
    mine -= {int(n) for n in re.findall(rb"item\(\w+, (\d+),", clean["menu_win32.c"])}
    clash = sorted(mine & set(taken))
    if not taken or not mine or clash:
        errors.append("menu numbers: " + (", ".join(f"{n} is the game's {taken[n]}" for n in clash) or "none found to compare"))
    # an update of the game must count as "needs a rebuild", else Apply.bat leaves the build (and its recovery) to others
    stamp = os.path.join(os.path.dirname(tool), "build_stamp.py")
    os.makedirs(os.path.join(tmp, "game"), exist_ok=True)
    open(os.path.join(tmp, "game", "dqix.exe"), "wb").close()
    check = lambda what: subprocess.run([sys.executable, "-X", "utf8", stamp, tmp, what]).returncode
    check("write")
    if check("check") != 0:
        errors.append("build_stamp: a build just stamped counts as outdated")
    for n in ("version.h", "frontend_sdl.c", "session.c", "menu.h"):
        p = os.path.join(tmp, "runtime", n)
        before = open(p, "rb").read()
        open(p, "ab").write(b"/* a newer game */\n")
        if check("check") != 10:
            errors.append(f"build_stamp: a changed runtime/{n} (game update) doesn't ask for a rebuild")
        open(p, "wb").write(before)
    # the save editor's helper is remade when its source differs, whatever the dates say (the release zip dates its files
    # 2026-01-01, older than a helper made before the update, which then kept sending the old menu command)
    os.makedirs(os.path.join(tmp, "mods", "system", "bin"), exist_ok=True)
    open(os.path.join(tmp, "mods", "system", "bin", "dqix-editor.exe"), "wb").close()
    cs = os.path.join(tmp, "mods", "system", "src", "editor", "EditorHost.cs")
    if check("editor-check") != 10:
        errors.append("build_stamp: a save editor helper of unknown source counts as current")
    check("editor-write")
    if check("editor-check") != 0:
        errors.append("build_stamp: a save editor helper just made counts as outdated")
    open(cs, "ab").write(b"// a newer helper\n")
    os.utime(cs, (1767225600, 1767225600))
    if check("editor-check") != 10:
        errors.append("build_stamp: a changed EditorHost.cs with an old date doesn't remake the helper")
    bat = open(os.path.join(os.path.dirname(tool), "..", "..", "Apply.bat"), "rb").read()
    if b"editor-check" not in bat or b"editor-write" not in bat:
        errors.append("Apply.bat doesn't ask build_stamp.py whether the save editor helper is current")
    if b"Apply.bat" not in on1["update.c"]:
        errors.append("the updater does not put the mods back")
    if on1["noflee.c"] is None:
        errors.append("noflee.c not put in")
    if "main 0208a91c noflee" not in open(os.path.join(tmp, "wrap.txt"), encoding="utf-8").read():
        errors.append("wrap.txt has no line for noflee")
    rc2, _ = run("yes")
    if rc2 != 0 or snap() != on1:
        errors.append("second ON changed something (not idempotent)")
    run("no")
    if snap() != clean:
        errors.append("OFF does not give back the clean files")
    run("yes")
    if snap() != on1:
        errors.append("ON after an update-like clean state differs from the first ON")
    print("RESULT: " + ("FAIL\n" + "\n".join(errors) if errors else "PASS"))
    sys.exit(1 if errors else 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
