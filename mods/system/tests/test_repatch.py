"""The automatic re-patching (apply_runtime_mod.py + repatch.py) on a copy of the game's source files, no build:

   test_repatch.py <project root>

   1  a game patched by an older version (markers, no kept copy): every place on, the game's own copy recovered
   2  an update that changed spaces, line breaks and comments around the places: found anyway ("relaxed")
   3  an update that builds the menu bar from a table (no "Help" line): the Cheats tab goes in the other way
   4  a failed build: the compiler's errors point at the right places (marked lines, the mods' own files, a missing name)
   5  that place is left out (sites-off.txt), the others stay; the game's file is its own copy plus the rest
   6  the next update (the game's file changed): the place is tried again
   7  everything off (sync_cheats = no): the game's files are exactly their own copies again"""
import os, re, shutil, subprocess, sys, tempfile

root = os.path.abspath(sys.argv[1])
tools = os.path.join(root, "mods", "system", "tools")
sys.path.insert(0, tools)
import apply_runtime_mod as arm
import repatch

NAMES = sorted({n for n, *_ in arm.SITES})
errors = []
tmp = tempfile.mkdtemp(prefix="dqix-repatch-")
try:
    os.makedirs(os.path.join(tmp, "runtime"))
    for n in NAMES + ["wrap.txt"]:
        src = os.path.join(root, "runtime", n) if n != "wrap.txt" else os.path.join(root, n)
        shutil.copy2(src, os.path.join(tmp, "runtime", n) if n != "wrap.txt" else os.path.join(tmp, n))
    shutil.copytree(os.path.join(root, "mods", "system", "src"), os.path.join(tmp, "mods", "system", "src"))
    if os.path.isdir(os.path.join(root, "mods", "plugins", "sdk")):
        shutil.copytree(os.path.join(root, "mods", "plugins", "sdk"), os.path.join(tmp, "mods", "plugins", "sdk"))
    settings = os.path.join(tmp, "mods", "settings.txt")
    open(settings, "w").write("sync_cheats = yes\n")
    rt = lambda n: os.path.join(tmp, "runtime", n)
    keep = lambda n: os.path.join(tmp, "mods", "system", "bin", "pristine", n)
    rd = lambda p: open(p, encoding="utf-8", newline="").read()

    def run(*extra):
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(tools, "apply_runtime_mod.py"), tmp] + list(extra), capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def report():
        return dict(l.split(" ", 1) for l in rd(os.path.join(tmp, "mods", "system", "bin", "repatch.txt")).splitlines() if l and not l.startswith("#"))

    # 1
    rc, out = run()
    rep = report()
    bad = [k for k in arm.SITE_KEYS if not rep.get(k, "").startswith("on")]
    if bad:
        errors.append("1: not on: " + ", ".join(f"{k}={rep.get(k)}" for k in bad))
    for n in NAMES:
        if not os.path.isfile(keep(n)) or ">>> mods:" in rd(keep(n)):
            errors.append(f"1: no clean copy of {n}")
    print("1  older patched game:", rep, flush=True)

    # 2: an update with other spacing/comments at the places
    def update(n, fn):
        t = fn(rd(keep(n)))
        open(rt(n), "w", encoding="utf-8", newline="").write(t)
    old_menu = 'HMENU help = sub(g_bar, L"&Help");' in rd(keep("menu_win32.c"))     # the older game (v33); newer ones use a table
    if old_menu:
        update("menu_win32.c", lambda t: t.replace('    HMENU help = sub(g_bar, L"&Help");', '    HMENU  help =  sub( g_bar,\n        L"&Help" );   /* the last menu */'))
    else:
        update("menu_win32.c", lambda t: t.replace("    SetMenu(g_hwnd, g_bar);\n", "    SetMenu( g_hwnd,  g_bar );   /* the bar */\n"))
    update("frontend_sdl.c", lambda t: t.replace("    case MI_UPDATE: update_menu(); break;", "    case MI_UPDATE:\n        update_menu();\n        break;"))
    rc, out = run()
    rep = report()
    if not (rep.get("menu", "").startswith("on (relaxed") and rep.get("act", "").startswith("on (relaxed")):
        errors.append(f"2: relaxed places not found: menu={rep.get('menu')} act={rep.get('act')}")
    if 'L"&Cheats"' not in rd(rt("menu_win32.c")) or "case 9360:" not in rd(rt("frontend_sdl.c")):
        errors.append("2: the places are not in the files")
    print("2  reformatted update:", rep.get("menu"), "|", rep.get("act"), flush=True)

    # 3: a menu bar from a table (newer games): no Help line at all
    update("menu_win32.c", lambda t: re.sub(r'[ \t]*HMENU\s+help\s*=.*?;[^\n]*\n', "", t, count=1, flags=re.S))
    rc, out = run()
    rep = report()
    m = rd(rt("menu_win32.c"))
    if not rep.get("menu", "").startswith("on") or "form 2" not in rep.get("menu", "") or "InsertMenuW(g_bar" not in m:
        errors.append(f"3: table menus: {rep.get('menu')}")
    print("3  table menus:", rep.get("menu"), flush=True)

    # 4: what a failed build's errors point at
    lines = m.splitlines()
    at = next(i for i, l in enumerate(lines) if "InsertMenuW(g_bar" in l) + 1
    own = next(i for i, l in enumerate(lines) if re.search(r"SetMenu\(\s*g_hwnd", l)) + 1
    log = (f"runtime/menu_win32.c:{at}:9: error: 'x' undeclared\n"
           "runtime/mod_cheatwin.c:12:1: error: something\n"
           "C:/x/ld.exe: build/obj/rt/frontend_sdl.o: in function `go': undefined reference to `mod_editor_take'\n"
           f"runtime/menu_win32.c:{own + 3}:1: error: the game's own\n")
    keys, other = repatch.why(tmp, log)
    if keys != ["menu", "input", "act"] or len(other) != 1:
        errors.append(f"4: errors read as {keys} / {other}")
    print("4  errors point at:", keys, "| the game's own:", len(other), flush=True)

    # 5: leave "menu" out after the failed build
    rc, out = run("--off", "menu")
    rep = report()
    m = rd(rt("menu_win32.c"))
    if rep.get("menu") != "off" or ">>> mods:" in m or m != rd(keep("menu_win32.c")) or not rep.get("act", "").startswith("on"):
        errors.append(f"5: menu not left out cleanly ({rep.get('menu')})")
    if "[off] Cheats tab in the menu bar" not in out:
        errors.append("5: not said")
    print("5  left out:", rep.get("menu"), "| act still", rep.get("act"), flush=True)
    rc, out = run()
    if report().get("menu") != "off":
        errors.append("5: menu came back without an update")

    # 6: the next update changes the game's file: tried again
    update("menu_win32.c", lambda t: "/* v35 */\n" + t)
    rc, out = run()
    rep = report()
    if not rep.get("menu", "").startswith("on") or "trying it again" not in out or os.path.isfile(os.path.join(tmp, "mods", "system", "bin", "sites-off.txt")):
        errors.append(f"6: not tried again after the update ({rep.get('menu')})")
    print("6  after the next update:", rep.get("menu"), flush=True)

    # 7: everything off
    open(settings, "w").write("sync_cheats = no\n")
    rc, out = run()
    for n in NAMES:
        if rd(rt(n)) != rd(keep(n)):
            errors.append(f"7: {n} is not the game's own copy")
    print("7  all off: the files are the game's own:", not any(e.startswith("7") for e in errors), flush=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("RESULT:", "PASS" if not errors else "FAIL")
for e in errors:
    print("  ", e)
sys.exit(0 if not errors else 1)
