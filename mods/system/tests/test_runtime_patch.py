#!/usr/bin/env python3
"""The mods' places in the game's source (incl. the Cheats tab) survive an update of the game.

  test_runtime_patch.py <game folder>

Works on a copy of runtime/ and wrap.txt in the temp folder: ON puts every marked place in, OFF (sync_cheats = no, same as a
fresh update that brought clean files) takes them all out again, ON again must give the exact same files. Nothing in the
game folder is touched.
"""
import os, shutil, subprocess, sys, tempfile

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
    if b"case 364:" not in on1["frontend_sdl.c"] or b"mod_editor_take" not in on1["frontend_sdl.c"] or b"mod_editor_take" not in (on1["mod_menu.c"] or b""):
        errors.append("the game doesn't take the save editor's export (menu command 364, mod_editor_take)")
    if b"Apply cheats.bat" not in on1["update.c"]:
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
