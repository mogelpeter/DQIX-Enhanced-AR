#!/usr/bin/env python3
"""Builds release.zip (only what a player needs) and publishes it as a GitHub release.

    python release/make_release.py            check, bump the version, build, commit, tag, push, publish
    python release/make_release.py --dry-run  only check and build dist/release.zip (version and repo stay as they are)

The version (file VERSION) is the version of the last release. Every release takes the next one (1.0.0 -> 1.0.1 ...;
--minor / --major count the other places); the very first release takes the number in VERSION as it is.
The zip is always the same asset name, release.zip, so
https://github.com/mogelpeter/DQIX-Enhanced-AR/releases/latest/download/release.zip is always the newest one.

What is in the zip is the list below: the installer, the mods the game needs, the readme. Not the tests, the
developer tools, the notes, .claude, .git.
"""
import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
REPO = "mogelpeter/DQIX-Enhanced-AR"

# (source relative to the repo, path in the zip); a folder takes everything in it
INCLUDE = [
    ("Install cheats.bat", "Install cheats.bat"),
    ("Install cheats.ps1", "Install cheats.ps1"),
    ("LICENSE", "LICENSE"),
    ("VERSION", "VERSION"),
    ("release/README.txt", "README.txt"),
    ("mods/Apply cheats.bat", "mods/Apply cheats.bat"),
    ("mods/README.txt", "mods/README.txt"),
    ("mods/settings.txt", "mods/settings.txt"),
    ("mods/system/about.tsv", "mods/system/about.tsv"),
    ("mods/system/verified.txt", "mods/system/verified.txt"),
    ("mods/system/cheats", "mods/system/cheats"),
    ("mods/system/fonts", "mods/system/fonts"),
    ("mods/system/lang/editor.tsv", "mods/system/lang/editor.tsv"),
    ("mods/system/src", "mods/system/src"),
]
# the tools "Apply cheats.bat" runs (the others are for developing: dev.py, dqre.py, pacdump.py, progress.py)
TOOLS = ["apply_code_mods.py", "apply_runtime_mod.py", "build_stamp.py", "catalog.py", "make_ar_list.py",
         "put_in.sh", "r4_to_text.py", "repatch.py", "rom_text.py"]

CRLF_EXT = (".bat", ".ps1")
LF_EXT = (".sh", ".py", ".c", ".h")


def run(*args, check=True, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit("failed: %s\n%s%s" % (" ".join(args), r.stdout, r.stderr))
    return r.stdout.strip()


def read_version():
    with open(os.path.join(ROOT, "VERSION"), encoding="ascii") as f:
        v = f.read().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        sys.exit("VERSION must look like 1.2.3, it is %r" % v)
    return v


def bump(v, part):
    a, b, c = (int(x) for x in v.split("."))
    if part == "major":
        return "%d.0.0" % (a + 1)
    if part == "minor":
        return "%d.%d.0" % (a, b + 1)
    return "%d.%d.%d" % (a, b, c + 1)


def remote_tags():
    out = run("git", "ls-remote", "--tags", "origin")
    return set(re.findall(r"refs/tags/(v\d+\.\d+\.\d+)$", out, re.M))


def collect():
    """[(source path, zip path)] of every file that goes in the zip"""
    files = []
    for src, dst in INCLUDE:
        p = os.path.join(ROOT, *src.split("/"))
        if os.path.isdir(p):
            for d, dirs, names in os.walk(p):
                dirs[:] = sorted(x for x in dirs if x != "__pycache__")
                for n in sorted(names):
                    full = os.path.join(d, n)
                    rel = os.path.relpath(full, p).replace(os.sep, "/")
                    files.append((full, dst + "/" + rel))
        elif os.path.isfile(p):
            files.append((p, dst))
        else:
            sys.exit("missing for the release: " + src)
    for t in TOOLS:
        p = os.path.join(ROOT, "mods", "system", "tools", t)
        if not os.path.isfile(p):
            sys.exit("missing tool for the release: " + t)
        files.append((p, "mods/system/tools/" + t))
    return files


def normalized(path, zname):
    """the file's bytes with the line ends its kind needs (a Windows checkout may have changed them)"""
    with open(path, "rb") as f:
        data = f.read()
    low = zname.lower()
    if low.endswith(CRLF_EXT):
        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    elif low.endswith(LF_EXT):
        data = data.replace(b"\r\n", b"\n")
    return data


def lint(contents):
    """syntax and format checks on what goes to other PCs. contents = {zip path: bytes}. Returns the problems."""
    problems = []
    tmp = tempfile.mkdtemp(prefix="dqix-release-")
    try:
        for name, data in contents.items():
            low = name.lower()
            if low.endswith(CRLF_EXT):
                try:
                    data.decode("ascii")
                except UnicodeDecodeError as e:
                    problems.append("%s: not plain ASCII (byte %d): other code pages would change it" % (name, e.start))
                if re.search(rb"(?<!\r)\n", data):
                    problems.append("%s: has a line end without CR (a batch file needs CRLF)" % name)
            if low.endswith(LF_EXT) and b"\r" in data:
                problems.append("%s: has CR characters (shell and Python scripts need LF)" % name)
            if low.endswith(".bat"):
                text = data.decode("ascii", "replace")
                labels = {m.group(1).lower() for m in re.finditer(r"^:([A-Za-z0-9_]+)", text, re.M)}
                for m in re.finditer(r"\bgoto\s+:?([A-Za-z0-9_]+)", text, re.I):
                    g = m.group(1).lower()
                    if g != "eof" and g not in labels:
                        problems.append("%s: goto %s has no label" % (name, m.group(1)))
            if low.endswith(".py"):
                p = os.path.join(tmp, os.path.basename(name))
                with open(p, "wb") as f:
                    f.write(data)
                try:
                    py_compile.compile(p, cfile=p + "c", doraise=True)
                except py_compile.PyCompileError as e:
                    problems.append("%s: %s" % (name, str(e).strip()))
            if low.endswith(".sh"):
                sh = shutil.which("sh") or shutil.which("bash")
                if sh:
                    p = os.path.join(tmp, "x.sh")
                    with open(p, "wb") as f:
                        f.write(data)
                    r = subprocess.run([sh, "-n", p], capture_output=True, text=True)
                    if r.returncode != 0:
                        problems.append("%s: %s" % (name, r.stderr.strip()))
            if low.endswith(".ps1"):
                p = os.path.join(tmp, "x.ps1")
                with open(p, "wb") as f:
                    f.write(data)
                ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
                if os.path.exists(ps):
                    code = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$t,[ref]$e);"
                            "if($e.Count){$e|ForEach-Object{$_.Message+' (line '+$_.Extent.StartLineNumber+')'};exit 1}" % p.replace("'", "''"))
                    r = subprocess.run([ps, "-NoProfile", "-Command", code], capture_output=True, text=True)
                    if r.returncode != 0:
                        problems.append("%s: %s" % (name, (r.stdout + r.stderr).strip()))
                else:
                    print("note: no Windows PowerShell here, the .ps1 was not parsed")
        # the installer's neighbours must be there
        for need in ("Install cheats.bat", "Install cheats.ps1", "VERSION", "mods/Apply cheats.bat", "mods/system/tools/catalog.py",
                     "mods/system/tools/put_in.sh", "mods/system/about.tsv", "mods/system/src/editor/EditorHost.cs"):
            if need not in contents:
                problems.append("missing in the zip: " + need)
        for name in contents:
            if re.search(r"(^|/)(\.claude|\.git|tests|docs|__pycache__)(/|$)|CLAUDE\.md|dev\.(py|bat)", name):
                problems.append("must not be in the player's zip: " + name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return problems


def build_zip(version):
    contents = {}
    for src, zname in collect():
        contents[zname] = normalized(src, zname)
    problems = lint(contents)
    if problems:
        sys.exit("The release has problems:\n  " + "\n  ".join(problems))
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "release.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(contents):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, contents[name])
    with zipfile.ZipFile(out) as z:
        if z.testzip():
            sys.exit("the zip is damaged")
    print("built %s: %d files, %.1f KB, version %s" % (out, len(contents), os.path.getsize(out) / 1024, version))
    return out


def token():
    r = subprocess.run(["git", "credential", "fill"], cwd=ROOT, input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    sys.exit("no GitHub credential found: sign in with git (git push) once, then try again")


def api(method, url, tok, data=None, ctype="application/json"):
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "dqix-enhanced-ar-release", "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        sys.exit("GitHub said %s for %s %s: %s" % (e.code, method, url, e.read().decode("utf-8", "replace")[:500]))


def publish(version, zip_path, notes):
    tag = "v" + version
    tok = token()
    rel = api("POST", "https://api.github.com/repos/%s/releases" % REPO, tok,
              {"tag_name": tag, "target_commitish": "main", "name": "DQIX Enhanced AR " + version,
               "body": notes, "draft": False, "prerelease": False, "make_latest": "true"})
    with open(zip_path, "rb") as f:
        data = f.read()
    up = rel["upload_url"].split("{")[0] + "?name=release.zip"
    asset = api("POST", up, tok, data, "application/zip")
    print("published:", rel["html_url"])
    print("download :", asset["browser_download_url"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="check and build dist/release.zip only")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--minor", action="store_true")
    g.add_argument("--major", action="store_true")
    ap.add_argument("--notes", default="", help="text of the release")
    a = ap.parse_args()

    current = read_version()
    if a.dry_run:
        build_zip(current)
        return

    if run("git", "status", "--porcelain"):
        sys.exit("The working tree has uncommitted changes: commit them first (the release is made from what is committed).")
    if run("git", "rev-parse", "--abbrev-ref", "HEAD") != "main":
        sys.exit("Release from the main branch.")
    run("git", "fetch", "origin", "--tags", "--quiet")
    if run("git", "rev-parse", "HEAD") != run("git", "rev-parse", "origin/main") and run("git", "log", "origin/main..HEAD", "--oneline") == "":
        sys.exit("origin/main has commits this checkout does not: pull first.")

    tags = remote_tags()
    version = current
    if "v" + current in tags or a.minor or a.major:
        version = bump(current, "major" if a.major else "minor" if a.minor else "patch")
    while "v" + version in tags:
        version = bump(version, "patch")
    if version != current:
        with open(os.path.join(ROOT, "VERSION"), "w", encoding="ascii", newline="") as f:
            f.write(version)
    zip_path = build_zip(version)

    # tidy changes before the commit, so a failed publish does not leave a version nobody can download
    run("git", "add", "VERSION")
    if run("git", "status", "--porcelain"):
        run("git", "commit", "-m", "Release v%s\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" % version)
    run("git", "push", "origin", "main")
    notes = a.notes or ("Unzip, then double-click `Install cheats.bat`. It asks where your DQIX Enhanced folder is, "
                        "puts the files in and builds the cheats into the game.")
    publish(version, zip_path, notes)


if __name__ == "__main__":
    main()
