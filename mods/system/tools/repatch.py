#!/usr/bin/env python3
"""Build the game with the mods, and when the build fails because of one of the mods' places in the game's code,
build it again without that place (Apply cheats.bat runs this, also after an update of the game).

  repatch.py [project folder]           build; on a failure caused by the mods: leave that place out, build again
  repatch.py [project folder] --why LOG which places of the mods the compiler errors in LOG point at (no build)

The build's output goes to the screen as always and to mods/system/bin/build.log. A failed build is read like this:
  - an error in a marked place of the game's file (/* >>> mods ... <<< mods */): that place
  - an error in one of the mods' own files in runtime/ (mod_cheats.c, mod_menu.c, lowexp.c ...): the place they come with
  - an error in the recompiled code (build/...): the live code mods (their lines in wrap.txt)
  - "undefined reference to `x'": the place whose lines call x
That place is written to mods/system/bin/sites-off.txt (apply_runtime_mod.py leaves it out until the game's file changes,
e.g. with the next update), the mods are put in again without it and the game is built again; at most four times.
An error that isn't the mods' (the game itself) stops it: nothing of the game's own code is touched.

Exit code: 0 = the game is built, 1 = it isn't.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_runtime_mod as arm

OWN = {f: "input" for f in arm.FILES}
OWN.update({f: "act" for f in arm.MENU_FILES})
OWN.update({f: "wrap" for f in arm.WRAP_FILES + ["mod_livepatch_tab.c"]})
BEGIN_KEY = {}
for _i, (_n, _o, _p, _b, _w) in enumerate(arm.SITES):
    BEGIN_KEY[_b.strip()] = arm.SITE_KEYS[_i]
for _k, _vs in arm.VARIANTS.items():
    for _o, _p, _b in _vs:
        BEGIN_KEY[_b.strip()] = _k


def key_at(root, name, line):
    """the place of the mods whose marked lines hold line `line` of runtime/name, or None"""
    try:
        lines = open(os.path.join(root, "runtime", name), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    for k in range(min(line, len(lines)) - 1, -1, -1):
        t = lines[k].strip()
        if t.startswith("/* <<< mods") and k != line - 1:
            return None                                 # a marked block ended above it: the line is the game's own
        if t.startswith("/* >>> mods:"):
            return BEGIN_KEY.get(t)
    return None


def key_calling(root, symbol):
    """the place whose marked lines (or own files) use this name"""
    for i, (name, *_rest) in enumerate(arm.SITES):
        try:
            text = open(os.path.join(root, "runtime", name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for block in re.findall(r"/\* >>> mods:.*?/\* <<< mods \*/", text, re.S):
            if re.search(r"\b" + re.escape(symbol) + r"\b", block):
                return BEGIN_KEY.get(block.splitlines()[0].strip(), arm.SITE_KEYS[i])
    for f, key in OWN.items():
        try:
            if re.search(r"\b" + re.escape(symbol) + r"\b", open(os.path.join(root, "runtime", f), encoding="utf-8", errors="replace").read()):
                return key
        except OSError:
            pass
    return None


def why(root, log):
    """-> (places of the mods to leave out, errors that are the game's own)"""
    keys, other = [], []
    for line in log.splitlines():
        m = re.search(r"(?:^|[\s/])(runtime|build)/([\w./-]+?\.[ch]):(\d+):(?:\d+:)? (?:fatal )?error", line)
        if m:
            where, f, n = m.group(1), m.group(2), int(m.group(3))
            base = os.path.basename(f)
            k = OWN.get(base) if where == "runtime" else "wrap"
            if k is None and where == "runtime":
                k = key_at(root, base, n)
            (keys if k else other).append(k or line.strip())
            continue
        m = re.search(r"undefined reference to `([A-Za-z_]\w*)'", line)
        if m:
            k = key_calling(root, m.group(1))
            (keys if k else other).append(k or line.strip())
    return list(dict.fromkeys(keys)), other


def win(p):
    """a Windows path with backslashes (the MSYS2 Python writes C:/...; cmd reads "/x" as a switch)"""
    return os.path.abspath(p).replace("/", chr(92))


def build(root):
    """BUILD.bat, its output on the screen and in mods/system/bin/build.log. -> (exit code, the output)"""
    env = {k: v for k, v in os.environ.items() if k.upper() != "NODEFAULTCURRENTDIRECTORYINEXEPATH"}
    env["DQIX_NOPAUSE"] = "1"
    cmd = win(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe"))
    log_path = os.path.join(root, "mods", "system", "bin", "build.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    out = []
    with open(log_path, "wb") as log:
        bat = win(os.path.join(root, "BUILD.bat"))
        p = subprocess.Popen([cmd, "/d", "/c", "call", bat], cwd=win(root), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in p.stdout:
            log.write(raw)
            sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
            out.append(raw.decode("utf-8", "replace"))
        p.wait()
    return p.returncode, "".join(out)


def put_in(root, off=None):
    args = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "apply_runtime_mod.py"), root]
    if off:
        args += ["--off", ",".join(off)]
    return subprocess.run(args).returncode


def main():
    a = [x for x in sys.argv[1:]]
    root = os.path.abspath(a[0] if a and not a[0].startswith("--") else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if "--why" in a:
        keys, other = why(root, open(a[a.index("--why") + 1], encoding="utf-8", errors="replace").read())
        print("places of the mods:", ", ".join(keys) or "none")
        for o in other[:10]:
            print("the game's own:", o)
        return 0
    for attempt in range(5):
        rc, out = build(root)
        if rc == 0:
            return 0
        keys, other = why(root, out)
        keys = [k for k in keys if k not in arm.off_list(root)]
        if not keys or attempt == 4:
            if other:
                sys.stdout.flush(); print("\n   The build failed in the game's own code, not in the mods' places:")
                for o in other[:6]:
                    print("     " + o[:200])
            return 1
        print("\n   The build failed in the mods' part: " + ", ".join(keys) + ". Leaving that out and building again...\n", flush=True)
        if put_in(root, keys) == 1:
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
