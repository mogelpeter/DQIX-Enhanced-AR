#!/usr/bin/env python3
"""dev.py - one entry point to work on the mods fast and to test them cheaply.

  dev.py doctor                 what is missing on this PC (and how to fix it)
  dev.py deploy [--pull]        repo mods\\ -> the game folder's mods\\ (only changed files); --pull = the other way
  dev.py editor [--out EXE]     compile the save editor's helper (only when the source is newer)
  dev.py test [fast|full|NAME ...] [--force] [--jobs N]
  dev.py scratch [--rounds]     build ALL code mods in a scratch copy of the project (the game folder stays as it is)

Where things are (nothing is hard-coded to one PC):
  the game folder = the one with BUILD.bat. Found from, in this order: --root, the DQIX_ROOT environment variable,
  mods\\system\\dev-root.txt (one line: the path), or the parent of the mods\\ folder this file is in.
  Work on the repo copy of mods\\ and deploy: every command deploys first when this file is not in the game folder.

Why it is fast (see docs/WORKFLOW.md in the repo): tests are tiered (fast ~2 min, full ~8 min), results are cached by a hash of every
input so unchanged work is skipped, independent game tests run in parallel on their own ports, and the editor test
runs alone at the end.
"""
import argparse, concurrent.futures as cf, glob, hashlib, json, os, py_compile, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_MODS = os.path.dirname(os.path.dirname(HERE))                       # the mods\ this file lives in (repo or game folder)
USER_FILES = {"menu-state.txt", "editor-lang.txt", "msys2-root.txt", "settings.txt", "dev-root.txt", "built.txt"}
SKIP_DIRS = {"bin", "save-backups", "__pycache__", ".cache"}
TMP = os.path.join(tempfile.gettempdir(), "dqix-mods-tests")


def read(path):
    try:
        return open(path, encoding="utf-8-sig").read().strip()
    except OSError:
        return ""


def is_root(p):
    return bool(p) and os.path.isfile(os.path.join(p, "BUILD.bat")) and os.path.isfile(os.path.join(p, "patches.txt"))


def find_root(arg=None):
    for c in (arg, os.environ.get("DQIX_ROOT"), read(os.path.join(SRC_MODS, "system", "dev-root.txt")), os.path.dirname(SRC_MODS)):
        if is_root(c):
            return os.path.abspath(c)
    return None


def need_root(arg):
    r = find_root(arg)
    if not r:
        sys.exit("Can't find the DQIX Enhanced folder (the one with BUILD.bat).\n"
                 "Give it once:  dev.py --root \"C:\\path\\to\\DQIX Enhanced\" doctor   or write the path into mods\\system\\dev-root.txt")
    return r


# ------------------------------------------------------------------ files: deploy
def tree(base):
    out = {}
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f in USER_FILES or f.endswith(".pyc") or f.startswith("AR-codes-"):
                continue
            p = os.path.join(d, f)
            out[os.path.relpath(p, base)] = p
    return out


def digest(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def sync(src, dst, quiet=False):
    """copy changed files src -> dst (never the user's own state files); returns the list that changed"""
    changed = []
    for rel, p in tree(src).items():
        q = os.path.join(dst, rel)
        if os.path.isfile(q) and digest(p) == digest(q):
            continue
        os.makedirs(os.path.dirname(q), exist_ok=True)
        shutil.copy2(p, q)
        changed.append(rel)
    if changed and not quiet:
        print("  deployed:", ", ".join(changed[:8]) + (f" (+{len(changed) - 8} more)" if len(changed) > 8 else ""))
    return changed


def ensure_deployed(root):
    live = os.path.join(root, "mods")
    if os.path.abspath(live) != os.path.abspath(SRC_MODS):
        sync(SRC_MODS, live)
    return live


def cmd_deploy(a):
    root = need_root(a.root)
    live = os.path.join(root, "mods")
    src, dst = (live, SRC_MODS) if a.pull else (SRC_MODS, live)
    if os.path.abspath(src) == os.path.abspath(dst):
        print("repo and game folder are the same place: nothing to do"); return 0
    ch = sync(src, dst, quiet=True)
    print(("pulled" if a.pull else "deployed"), len(ch), "file(s)" + (": " + ", ".join(ch[:10]) if ch else " (already identical)"))
    return 0


# ------------------------------------------------------------------ the save editor's helper
def csc_path():
    for fw in ("Framework64", "Framework"):
        p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", fw, "v4.0.30319", "csc.exe")
        if os.path.isfile(p):
            return p
    return None


def build_editor(root, out=None):
    live = os.path.join(root, "mods", "system")
    src = os.path.join(live, "src", "editor", "EditorHost.cs")
    exe = out or os.path.join(live, "bin", "dqix-editor.exe")
    if os.path.isfile(exe) and os.path.getmtime(exe) >= os.path.getmtime(src):
        return exe, False
    csc = csc_path()
    if not csc:
        sys.exit("The C# compiler (csc.exe of .NET Framework 4) isn't on this PC: it comes with Windows 10/11.")
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    cmd = [csc, "-nologo", "-target:winexe", "-platform:x64", "-optimize+", "-out:" + exe]
    ico = os.path.join(root, "build", "icon", "dqix.ico")
    if os.path.isfile(ico):
        cmd.append("-win32icon:" + ico)
    cmd += ["-r:System.Windows.Forms.dll", "-r:System.Core.dll", src]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode:
        print(r.stdout + r.stderr); sys.exit("editor helper: compile failed")
    return exe, True


def cmd_editor(a):
    root = need_root(a.root); ensure_deployed(root)
    exe, built = build_editor(root, a.out)
    print(("compiled " if built else "up to date: ") + exe)
    return 0


def game_running():
    r = subprocess.run(["tasklist", "/fi", "imagename eq dqix.exe"], capture_output=True)      # bytes: the console code page differs per PC
    return b"dqix.exe" in (r.stdout or b"").lower()


# ------------------------------------------------------------------ the tests
def input_key(root):
    """a hash of everything a test result depends on: the mods' sources, the catalog, the built game"""
    h = hashlib.sha1()
    live = os.path.join(root, "mods", "system")
    for pat in ("src/*/*", "tools/*.py", "tools/*.sh", "tests/*.py", "cheats/*", "bin/catalog.txt"):
        for f in sorted(glob.glob(os.path.join(live, pat))):
            h.update(f.encode() + digest(f).encode())
    for f in ("dqix.exe", "dqixcore.dll"):
        p = os.path.join(root, "game", f)
        if os.path.isfile(p):
            st = os.stat(p); h.update(f"{f}{st.st_size}{int(st.st_mtime)}".encode())
    return h.hexdigest()


def t_static(root, work):
    """in seconds, no game: python compiles, the C# 5 rule, the catalog is readable, nothing blocked can be switched on"""
    live = os.path.join(root, "mods", "system"); problems = []
    for f in glob.glob(os.path.join(live, "tools", "*.py")) + glob.glob(os.path.join(live, "tests", "*.py")):
        try:
            py_compile.compile(f, cfile=os.path.join(work, "x.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            problems.append(str(e)[:200])
    rp = subprocess.run([sys.executable, "-X", "utf8", os.path.join(live, "tests", "test_runtime_patch.py"), root], capture_output=True, text=True)
    if rp.returncode != 0:                                  # the Cheats tab and the other marked places in the game's source
        problems.append("test_runtime_patch.py: " + (rp.stdout + rp.stderr)[-300:])
    rp = subprocess.run([sys.executable, "-X", "utf8", os.path.join(live, "tests", "test_repatch.py"), root], capture_output=True, text=True)
    if rp.returncode != 0:                                  # re-patching after updates: relaxed places, table menus, a failed build
        problems.append("test_repatch.py: " + (rp.stdout + rp.stderr)[-400:])
    cs = open(os.path.join(live, "src", "editor", "EditorHost.cs"), encoding="utf-8").read()
    for pat, why in ((r'\$"', 'string interpolation'), (r'\w\?\.\w', '?. operator'), (r'nameof\(', 'nameof'), (r'\bout var\b', 'out var')):
        if re.search(pat, cs):
            problems.append("EditorHost.cs uses " + why + " (Windows' csc is C# 5)")
    cat = os.path.join(live, "bin", "catalog.txt")
    if not os.path.isfile(cat):
        problems.append("no mods\\system\\bin\\catalog.txt: run Apply.bat catalog")
        entries = {}
    else:
        entries = {}
        for n, line in enumerate(open(cat, encoding="utf-8"), 1):
            if not line.startswith("entry\t"):
                continue
            d = dict(p.split("=", 1) for p in line.rstrip("\n").split("\t")[1:] if "=" in p)
            entries[d["id"]] = d
            if d.get("kind") == "live":
                if not d.get("ops"):
                    problems.append(f"catalog line {n}: live cheat without code: {d.get('name')}")
                elif not all(re.fullmatch(r"[0-9A-Fa-f]{8}:[0-9A-Fa-f]{8}", o) for o in d["ops"].split(",")):
                    problems.append(f"catalog line {n}: unreadable code in {d.get('name')}")
            if d.get("kind") == "code" and not d.get("patch"):
                problems.append(f"catalog line {n}: built-in mod without patch: {d.get('name')}")
    state = os.path.join(live, "menu-state.txt")
    for line in read(state).splitlines():
        p = line.split(None, 1)
        if len(p) == 2 and p[0] in ("live", "code", "launch") and entries and p[1].strip() not in entries:
            problems.append(f"menu-state.txt names a cheat that is not in the list: {p[1].strip()}")
        if len(p) == 2 and p[0] in ("live", "code") and entries.get(p[1].strip(), {}).get("kind") == "blocked":
            problems.append(f"a blocked cheat is switched on: {p[1].strip()}")
    for p in problems:
        print("  PROBLEM:", p)
    print(f"static: {len(entries)} catalog entries, {len(problems)} problem(s)")
    print("RESULT:", "FAIL" if problems else "PASS")
    return 0 if not problems else 1


def py_test(root, script, args, env=None):
    live = os.path.join(root, "mods", "system")
    e = dict(os.environ); e.pop("NoDefaultCurrentDirectoryInExePath", None)
    e["PYTHONIOENCODING"] = "utf-8"; e.update(env or {})
    return subprocess.run([sys.executable, "-u", os.path.join(live, "tests", script), root] + args, cwd=root, env=e, capture_output=True, text=True, errors="replace")


def judge(name, r):
    out = r.stdout + r.stderr
    if "RESULT: PASS" in out:
        return True, out
    if "RESULT:" in out:
        return False, out
    return r.returncode == 0, out


def t_editor(root, work):
    """the editor's helper: serves the cached editor, hands out / takes back a scratch save, refuses wrong tokens, keeps the language"""
    exe, _ = build_editor(root)
    res = os.path.join(work, "editor-selftest.txt")
    try:
        subprocess.run([exe, "--editor-selftest", res], capture_output=True, timeout=90)
        txt = open(res, encoding="utf-8").read() if os.path.isfile(res) else "no result"
    except subprocess.TimeoutExpired:
        txt = "timeout"
    print("editor host:", txt)
    bad = txt != "PASS" and not txt.startswith("FAIL prepare")
    if txt.startswith("FAIL prepare"):
        print("  (no internet for the first download: skipped)")
    print("RESULT:", "FAIL" if bad else "PASS")
    return 1 if bad else 0


def t_nzdata(root, work):
    """the Nuzlocke randomizers on the ROM's own tables (tests/test_nuzlocke_data.c, compiled with MSYS2's gcc): permutations only, the same seed
    twice gives the same result, another seed another one, one species -> one species in the encounters"""
    msys = read(os.path.join(root, "mods", "system", "msys2-root.txt")) or r"C:\msys64"
    gcc = next((g for g in (os.path.join(msys, "ucrt64", "bin", "gcc.exe"), os.path.join(msys, "mingw64", "bin", "gcc.exe")) if os.path.isfile(g)), None)
    rom = os.path.join(root, "game", "data", "dqix.nds")
    if not gcc or not os.path.isfile(rom):
        print("no gcc (%s) or no ROM copy (%s)" % (gcc, rom)); print("RESULT: FAIL"); return 1
    exe = os.path.join(work, "t.exe")
    c = subprocess.run([gcc, "-O1", "-I", os.path.join(root, "runtime"), "-o", exe, os.path.join(root, "mods", "system", "tests", "test_nuzlocke_data.c")],
                       capture_output=True, text=True, errors="replace", env=dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ.get("PATH", "")))
    if c.returncode:
        print(c.stderr[-1500:]); print("RESULT: FAIL (compile)"); return 1
    r = subprocess.run([exe, rom], capture_output=True, text=True, errors="replace")
    print(r.stdout)
    return 0 if r.returncode == 0 else 1


# name -> (runner, parallel?, expected seconds). Runner(root, work, port) -> (ok, text)
def runners(root, work):
    w = lambda n: os.path.join(work, n)
    def fn(script, args, env=None):
        return lambda port: judge(script, py_test(root, script, [w(script + str(port))] + [x.replace("{port}", str(port)) for x in args], env))
    def inproc(f, name):
        def run(port):
            import io, contextlib
            os.makedirs(w(name), exist_ok=True)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = f(root, w(name))
            return rc == 0, buf.getvalue()
        return run
    return {
        "static":         (inproc(t_static, "static"), True, 3),
        "live-fast":      (fn("test_live.py", ["1500"]), True, 30),
        "session-fast":   (fn("test_session.py", ["{port}"]), True, 40),
        "all-quick":      (fn("test_all.py", ["single"], {"TEST_LIMIT": "12"}), True, 60),
        "live":           (fn("test_live.py", ["6000"]), True, 110),
        "session":        (fn("test_session.py", ["{port}"]), True, 40),
        "all-single":     (fn("test_all.py", ["single"]), True, 150),
        "all-session":    (fn("test_all.py", ["session", "", "{port}"]), True, 160),
        "cheatwin":       (fn("test_cheatwin.py", ["900"]), True, 60),             # the Cheats window inside the game (mod_cheatwin.c)
        "livepatch":      (fn("test_livepatch.py", ["4500"]), True, 400),         # live code mods; needs TEST_SAVE = a save with the hero in a dungeon
        "firststrike":    (fn("test_firststrike.py", []), True, 200),             # "Always strike first" (firststrike.c); needs TEST_SAVE as above
        "vanish-walk":    (fn("test_vanish_walk.py", []), True, 200),             # Vanish in the field: no battle, no frozen monster (vanish.c); TEST_SAVE as above
        "battle-live":    (fn("test_battle_live.py", []), True, 130),             # the live battle cheats in a forced battle (Battle cheats window); TEST_SAVE as above
        "undo-fun":       (fn("test_undo_fun.py", []), True, 90),                 # Fun cheats switched off put the game back (SET_UNDO); TEST_SAVE as above
        # cheats with buttons, the buttons really pressed (test_keys.py); TEST_SAVE as above
        "keys":           (fn("test_keys.py", ["db:6fec10fd|Increase/Decrease Size", "A+L,A+R", "20"]), True, 120),
        "keys-bag":       (fn("test_keys.py", ["db:26b3f9a9|99 of the bag item under the cursor", "START+R", "10"],
                              {"TEST_PRE": "3700:X:6;3780:A:6;3860:A:6;3940:DOWN:6;3990:DOWN:6;4040:DOWN:6;4100:A:6", "TEST_AT": "4200"}), True, 120),
        "zoom-grotto":    (fn("test_zoom_grotto.py", []), True, 150),
        # the Nuzlocke page: the randomizers on the ROM's tables, and every rule in a real game (test_nuzlocke.py); the rules need TEST_SAVE as above
        "nz-data":        (inproc(t_nzdata, "nz-data"), True, 20),
        **{"nz-" + n: (fn("test_nuzlocke.py", [n]), True, 150)
           for n in ("control", "perma", "persist", "link", "hero", "goldhalf", "goldall", "newrun", "battle", "battleko")},
        "editor":         (inproc(t_editor, "editor"), False, 10),
    }


TIERS = {
    "fast": ["static", "live-fast", "session-fast", "all-quick", "editor"],
    "nuzlocke": ["nz-data"] + ["nz-" + n for n in ("control", "perma", "persist", "link", "hero", "goldhalf", "goldall", "newrun", "battle", "battleko")],
    "full": ["static", "live", "session", "all-single", "all-session", "cheatwin", "editor"],
}


def cmd_test(a):
    root = need_root(a.root); ensure_deployed(root)
    if game_running():
        sys.exit("A dqix.exe is running (your game?): tests would collide with it. Close it first.")
    names = []
    for n in (a.what or ["fast"]):
        names += TIERS.get(n, [n])
    names = list(dict.fromkeys(names))
    os.makedirs(TMP, exist_ok=True)
    work = os.path.join(TMP, "run"); shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    table = runners(root, work)
    for n in names:
        if n not in table:
            sys.exit(f"no test called {n}. Tests: {', '.join(table)}; tiers: {', '.join(TIERS)}")
    if not os.path.isfile(os.path.join(root, "game", "dqix.exe")) and any(n != "static" for n in names):
        sys.exit("The game isn't built yet (game\\dqix.exe is missing): run BUILD.bat first.")
    exe, built = build_editor(root)
    if built:
        print("editor helper compiled")
    key = input_key(root)
    cache_file = os.path.join(root, "mods", "system", "bin", "test-cache.json")
    try:
        cache = json.load(open(cache_file))
    except (OSError, ValueError):
        cache = {}
    if cache.get("key") != key:
        cache = {"key": key, "passed": {}}
    results, t0 = {}, time.time()
    sys.path.insert(0, HERE)
    import progress                                       # the Claude Code status line shows this (.claude/statusline.py)
    running, lock = [], __import__("threading").Lock()

    def show():
        progress.set("dev test", len(results), len(names), ", ".join(running))

    def go(n, port):
        t = time.time()
        if n in cache["passed"] and not a.force:
            return n, True, "cached PASS", 0.0
        with lock:
            running.append(n); show()
        try:
            ok, out = table[n][0](port)
        finally:
            with lock:
                running.remove(n)
        open(os.path.join(work, n + ".log"), "w", encoding="utf-8").write(out)
        return n, ok, out, time.time() - t

    par = [n for n in names if table[n][1]]
    seq = [n for n in names if not table[n][1]]
    port = 47200
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = []
        for i, n in enumerate(par):
            futs.append(ex.submit(go, n, port + i * 3))
        for f in futs:
            r = f.result(); results[r[0]] = r; show()
            print(f"{'PASS' if r[1] else 'FAIL'}  {r[0]:<13} {r[3]:6.1f}s" + ("  (unchanged since the last pass: skipped)" if r[2] == "cached PASS" else ""), flush=True)
    for i, n in enumerate(seq):                           # the editor test runs alone, after the rest
        r = go(n, port + 60 + i); results[n] = r; show()
        print(f"{'PASS' if r[1] else 'FAIL'}  {n:<13} {r[3]:6.1f}s" + ("  (unchanged since the last pass: skipped)" if r[2] == "cached PASS" else ""), flush=True)
    for n, r in results.items():
        if r[1] and r[2] != "cached PASS":
            cache["passed"][n] = True
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    json.dump(cache, open(cache_file, "w"))
    progress.clear()
    bad = [n for n, r in results.items() if not r[1]]
    for n in bad:
        print(f"\n--- {n} (log: {os.path.join(work, n + '.log')}) ---\n" + "\n".join(results[n][2].splitlines()[-25:]))
    print(f"\n{len(results) - len(bad)}/{len(results)} passed in {time.time() - t0:.0f}s" + ("" if not bad else "  FAILED: " + ", ".join(bad)))
    return 1 if bad else 0


# ------------------------------------------------------------------ doctor
def cmd_doctor(a):
    root = find_root(a.root); bad = 0

    def line(ok, what, fix=""):
        nonlocal bad
        print(("  ok    " if ok else "  MISSING ") + what + ("" if ok else "\n          -> " + fix)); bad += (not ok)
    print("DQIX Enhanced mods: checking this PC")
    line(sys.platform == "win32", "Windows", "the cheats window and the editor helper are Windows programs")
    line(bool(csc_path()), "C# compiler (csc.exe, .NET Framework 4)", "it is part of Windows 10/11: enable .NET Framework 4.x in Windows features")
    line(sys.version_info >= (3, 8), f"Python {sys.version.split()[0]}", "install Python 3.8+ (python.org), or run through MSYS2's python3")
    line(bool(root), "DQIX Enhanced folder (with BUILD.bat)" + (": " + root if root else ""), "run:  dev.py --root \"<folder>\" doctor   (or put the path in mods\\system\\dev-root.txt)")
    if root:
        mods = os.path.join(root, "mods", "system")
        line(os.path.isdir(mods), "mods\\ folder in it", "run:  dev.py deploy")
        line(any(f.lower().endswith(".nds") for f in os.listdir(os.path.join(root, "rom"))) if os.path.isdir(os.path.join(root, "rom")) else False, "ROM in rom\\", "put your own Dragon Quest IX .nds in the rom folder")
        line(os.path.isfile(os.path.join(root, "game", "dqix.exe")), "game built (game\\dqix.exe)", "run BUILD.bat once (needs internet the first time for MSYS2)")
        line(os.path.isfile(os.path.join(root, "build", "recomp", "dispatch_table.c")), "build\\recomp (the mods are checked against it)", "run BUILD.bat")
        msys = read(os.path.join(mods, "msys2-root.txt")) or r"C:\msys64"
        line(os.path.isfile(os.path.join(msys, "usr", "bin", "bash.exe")), "MSYS2 build tools: " + msys, "BUILD.bat installs them; Apply.bat finds them")
        line(os.path.isfile(os.path.join(mods, "bin", "catalog.txt")), "cheat list (mods\\system\\bin\\catalog.txt)", "run  Apply.bat catalog")
        line(not game_running(), "no game running right now", "close dqix.exe before tests")
    print("\nAll good." if not bad else f"\n{bad} thing(s) to fix.")
    return 1 if bad else 0


# ------------------------------------------------------------------ scratch build of every code mod
def cmd_scratch(a):
    root = need_root(a.root); ensure_deployed(root)
    msys = read(os.path.join(root, "mods", "system", "msys2-root.txt")) or r"C:\msys64"
    bash = os.path.join(msys, "usr", "bin", "bash.exe")
    if not os.path.isfile(bash):
        sys.exit("MSYS2 not found: " + msys)
    proj = os.path.join(TMP, "proj")
    os.makedirs(proj, exist_ok=True)
    print("copying the project (not game\\, not rom\\) to", proj)
    for d in ("build", "runtime", "recomp", "tools", "third_party", "config", "extras", "skins", "fonts", "mods", "wfc", "packaging", "docs"):
        if os.path.isdir(os.path.join(root, d)):
            subprocess.run(["robocopy", os.path.join(root, d), os.path.join(proj, d), "/E", "/COPY:DAT", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", "save-backups"], capture_output=True)
    for f in ("build.mk", "patches.txt", "hle.txt", "hle7.txt", "interpret.txt", "tags.txt", "wrap.txt", "BUILD.bat"):
        shutil.copy2(os.path.join(root, f), os.path.join(proj, f))
    os.makedirs(os.path.join(proj, "game"), exist_ok=True)
    subprocess.run(["robocopy", os.path.join(root, "game", "data"), os.path.join(proj, "game", "data"), "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"], capture_output=True)
    shutil.copy2(os.path.join(root, "game", "dqix.sav"), os.path.join(proj, "game", "dqix.sav"))
    sys.path.insert(0, os.path.join(proj, "mods", "system", "tools"))
    import catalog
    import apply_code_mods as acm
    _, entries, _ = catalog.build(proj)
    rounds = []
    for e in entries:                                      # entries that patch the same instruction differently go in later rounds
        if e["kind"] != "code" or e["id"].startswith("launch:"):
            continue
        pm = {(n, ad): wd for n, ad, wd in e["patch"]}
        for r in rounds:
            if not any(k in r["used"] and r["used"][k] != wd for k, wd in pm.items()):
                break
        else:
            r = {"used": {}, "e": []}; rounds.append(r)
        r["used"].update(pm); r["e"].append(e)
    todo = rounds if a.rounds else rounds[:1]
    env = dict(os.environ, MSYSTEM="UCRT64", CHERE_INVOKING="1"); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    rom = [f for f in glob.glob(os.path.join(root, "rom", "*.nds"))][0].replace("\\", "/")
    for i, r in enumerate(todo):
        ids = [e["id"] for e in r["e"] if not e["file"]]
        files = {e["file"] for e in r["e"] if e["file"]}
        open(os.path.join(proj, "mods", "system", "menu-state.txt"), "w").write("\n".join(["code " + x for x in ids]) + "\nflag warned\n")
        for f in acm.hand_files(proj)[1]:
            s = open(f, encoding="utf-8-sig").read()
            on = any(n.replace("\\", "/").endswith("/" + os.path.basename(f)) or n == os.path.basename(f) for n in files)
            open(f, "w", encoding="utf-8").write(re.sub(r"(?m)^#\s*enabled\s*:.*$", "# enabled: " + ("yes" if on else "no"), s))
        print(f"round {i}: {len(r['e'])} code mods: " + ", ".join(e["name"] for e in r["e"][:6]) + (" ..." if len(r["e"]) > 6 else ""), flush=True)
        sh = f"cd '{proj.replace(chr(92), '/')}' && python3 mods/system/tools/catalog.py . >/dev/null; sh mods/system/tools/put_in.sh >/dev/null; ./tools/build-game.sh '{rom}' >/dev/null 2>&1; echo build=$?"
        out = subprocess.run([bash, "-lc", sh], env=env, capture_output=True, text=True, errors="replace").stdout.strip()
        print("  ", out)
        if "build=0" not in out:
            print("  BUILD FAILED"); return 1
        e2 = dict(env, TEST_EXE=os.path.join(proj, "game", "dqix.exe"))
        for script, args in (("test_session.py", [os.path.join(TMP, f"s{i}"), str(47300 + i)]), ("test_live.py", [os.path.join(TMP, f"l{i}"), "3000"]), ("test_vanish.py", [os.path.join(TMP, f"v{i}")])):
            o = subprocess.run([sys.executable, "-u", os.path.join(proj, "mods", "system", "tests", script), proj] + args, cwd=proj, env=e2, capture_output=True, text=True, errors="replace").stdout
            keep = [l.strip() for l in o.splitlines() if "RESULT" in l or "different" in l or "FAIL" in l]
            print("  ", script, "|", " ; ".join(keep))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the DQIX Enhanced folder (with BUILD.bat)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(f=cmd_doctor)
    p = sub.add_parser("deploy"); p.add_argument("--pull", action="store_true"); p.set_defaults(f=cmd_deploy)
    p = sub.add_parser("editor"); p.add_argument("--out"); p.set_defaults(f=cmd_editor)
    p = sub.add_parser("test"); p.add_argument("what", nargs="*"); p.add_argument("--force", action="store_true"); p.add_argument("--jobs", type=int, default=3); p.set_defaults(f=cmd_test)
    p = sub.add_parser("scratch"); p.add_argument("--rounds", action="store_true", help="also the alternatives that clash (x4, x8 ... Always Fail)"); p.set_defaults(f=cmd_scratch)
    a = ap.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
