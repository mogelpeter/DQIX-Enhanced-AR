#!/usr/bin/env python3
"""Lists every English text the menu can show (source + cheat list) that mods/system/lang/ui.tsv has no full translation for.
  lang_keys.py [DQIX folder]            -> prints the texts that miss one of de fr es it
  lang_keys.py [DQIX folder] --all      -> prints all of them"""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
mods = os.path.normpath(os.path.join(here, ".."))


def unesc(s):
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def source_keys():
    s = open(os.path.join(mods, "src", "CheatMenu.cs"), encoding="utf-8").read()
    keys = [unesc(m) for m in re.findall(r'Tr\.[TF]\(\s*"((?:[^"\\]|\\.)*)"', s)]
    keys += [unesc(m) for m in re.findall(r"(?:ToolTip|Content|Text)='([^'<{]{3,})'", s)]
    return keys


def catalog_keys(root):
    keys = []
    f = os.path.join(root, "mods", "system", "bin", "catalog.txt")
    if not os.path.isfile(f):
        return keys
    for line in open(f, encoding="utf-8"):
        for part in line.rstrip("\n").split("\t")[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                if k in ("name", "option", "title", "note", "reason", "cat") and v:
                    keys.append(v)
    return keys


def table(path):
    have = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                c = line.rstrip("\n").split("\t")
                have[c[0].replace("\\n", "\n")] = c[1:]
    return have


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = os.path.normpath(args[0]) if args else os.path.normpath(os.path.join(mods, "..", ".."))
    have = table(os.path.join(mods, "lang", "ui.tsv"))
    seen, out = set(), []
    for k in source_keys() + catalog_keys(root):
        if k in seen:
            continue
        seen.add(k)
        c = have.get(k)
        if "--all" in sys.argv or not c or len(c) < 4 or not all(c[:4]):
            out.append(k)
    for k in out:
        print(k.replace("\n", "\\n"))
    print("# %d texts, %d listed" % (len(seen), len(out)), file=sys.stderr)
