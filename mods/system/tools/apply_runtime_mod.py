#!/usr/bin/env python3
"""Put the mods' part of the game itself in place.

  apply_runtime_mod.py [project folder]

1. Live cheats that also work while playing with friends: it copies
   mod_cheats.c and ar_engine.h into runtime/ (the build compiles every .c file
   there) and changes one place in runtime/input.c so each frame's input goes
   through them.
2. "Instant loading" (a launch option) only when you play alone: one place in
   runtime/card.c. In a session every PC has to take the same time for the
   cartridge, or the PCs stop agreeing within two seconds ("OUT OF SYNC at
   frame 120"). With this the game keeps the cartridge's real timing whenever
   a session runs, whatever the window says.

Each change sits between two marker lines. An update of the game brings fresh
files without them; running this again (Apply cheats.bat does, every time)
puts them back. How a place is found when an update changed the game's code:

  - each patched file is made from an untouched copy of the game's own file
    (mods/system/bin/pristine/, taken whenever the file comes without markers,
    e.g. right after an update) plus the changes that are on, so one change
    can also be taken out again exactly;
  - a place is found by its exact lines, else by another known form of it
    (newer games build the menu bar from a table), else by the same code with
    other spaces, line breaks or comments (only if that fits exactly once);
  - a change that a build failed on (repatch.py reads the compiler's errors)
    is left out (mods/system/bin/sites-off.txt) until the game's file changes
    again, so an update can never leave a game that doesn't build.

If a place isn't found, that change is left out and said so: nothing is
half-changed. mods/system/bin/repatch.txt says how each place was found.

"sync_cheats = no" in mods/settings.txt takes all of it out again.

Exit code: 0 = nothing changed, 10 = the game has to be rebuilt, 1 = something
is wrong (the game wasn't changed).
"""
import os
import re
import sys

END = "    /* <<< mods */\n"

INPUT_BEGIN = "    /* >>> mods: live cheats (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
INPUT_ORIGINAL = """\
    if (session_running()) {                            /* lockstep: what was pressed `delay` frames ago, on every PC */
        uint32_t v = session_frame_input(g_frame, session_pack(g_keys_down, g_touch_down, g_touch_x, g_touch_y));
        session_unpack(v, &g_keys_down, &g_touch_down, &g_touch_x, &g_touch_y);
    }
"""
INPUT_PATCHED = INPUT_BEGIN + """\
    {   /* cheats travel in this console's input stream, so every PC of a session carries them out alike */
        uint32_t mod_cheats_out(uint32_t), mod_cheats_in(uint32_t);
        uint32_t pressed = session_pack(g_keys_down, g_touch_down, g_touch_x, g_touch_y);
        uint32_t v = mod_cheats_out(pressed);
        if (session_running()) v = session_frame_input(g_frame, v);   /* lockstep: what was pressed `delay` frames ago, on every PC */
        v = mod_cheats_in(v);
        if (session_running() || v != pressed) session_unpack(v, &g_keys_down, &g_touch_down, &g_touch_x, &g_touch_y);
    }
""" + END

CARD_BEGIN = "    /* >>> mods: instant loading only alone (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
CARD_ORIGINAL = """\
    if (g_card_timing < 0) g_card_timing = getenv("DQIX_CARD_INSTANT") == NULL;
"""
CARD_PATCHED = CARD_BEGIN + """\
    {   /* in a session every PC must take the same time for the cartridge: the real one */
        int session_running(void);
        static int instant = -1;
        if (instant < 0) instant = getenv("DQIX_CARD_INSTANT") != NULL;
        g_card_timing = !instant || session_running();
    }
""" + END

DATA_BEGIN = "    /* >>> mods: encounter tables for metal slimes only (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
DATA_ORIGINAL = """\
        int dmas = 0;
"""
DATA_PATCHED = DATA_BEGIN + """\
        {   /* the cheat "Metal slimes only" hands the game changed encounter tables (mod_data.c) */
            void mod_card_overlay(uint32_t, uint32_t, uint8_t*);
            mod_card_overlay(addr, len, g_card_buf);
        }
        int dmas = 0;
""" + END

MENU_BEGIN = "    /* >>> mods: Cheats tab in the menu bar (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
MENU_ORIGINAL = """\
    HMENU help = sub(g_bar, L"&Help");
"""
MENU_PATCHED = MENU_BEGIN + """\
    HMENU cheats = sub(g_bar, L"&Cheats");
    item(cheats, 360, L"&Cheats...");                       /* 360-363, 367: handled in frontend_sdl.c, mod_menu.c, mod_cheatwin.c */
    item(cheats, 367, L"&Battle cheats...");
    item(cheats, 362, L"&Save editor...");
    item(cheats, 363, L"&Treasure maps...");
    sep(cheats);
    item(cheats, 361, L"&What is this?");
    HMENU nuzlocke = sub(g_bar, L"&Nuzlocke");
    item(nuzlocke, 365, L"&Settings...");                   /* 365, 366: handled in frontend_sdl.c, mod_cheatwin.c */
    sep(nuzlocke);
    item(nuzlocke, 366, L"&What is this?");
""" + MENU_ORIGINAL + END

# Newer versions of the game (v34 on) build the menu bar from a table (runtime/menu_items.c): there is no "Help" line to put
# the tab in front of. There the tab goes in after the table is built, in front of Help.
MENU2_BEGIN = "    /* >>> mods: Cheats tab in the menu bar, table menus (mods/system/tools/apply_runtime_mod.py; an update removes this, Apply cheats.bat puts it back) */\n"
MENU2_ORIGINAL = """\
    SetMenu(g_hwnd, g_bar);
    SDL_EventState(SDL_SYSWMEVENT, SDL_ENABLE);
"""
MENU2_PATCHED = MENU2_BEGIN + """\
    {
        HMENU cheats = CreatePopupMenu();
        item(cheats, 360, L"&Cheats...");                   /* 360-363, 367: handled in frontend_sdl.c, mod_menu.c, mod_cheatwin.c */
        item(cheats, 367, L"&Battle cheats...");
        item(cheats, 362, L"&Save editor...");
        item(cheats, 363, L"&Treasure maps...");
        sep(cheats);
        item(cheats, 361, L"&What is this?");
        int n = GetMenuItemCount(g_bar), at = n; wchar_t t[32];
        if (n > 0 && GetMenuStringW(g_bar, (UINT)(n - 1), t, 32, MF_BYPOSITION) && !lstrcmpW(t, L"&Help")) at = n - 1;
        InsertMenuW(g_bar, (UINT)at, MF_BYPOSITION | MF_POPUP | MF_STRING, (UINT_PTR)cheats, L"&Cheats");
        HMENU nuzlocke = CreatePopupMenu();
        item(nuzlocke, 365, L"&Settings...");               /* 365, 366: handled in frontend_sdl.c, mod_cheatwin.c */
        sep(nuzlocke);
        item(nuzlocke, 366, L"&What is this?");
        InsertMenuW(g_bar, (UINT)at + 1, MF_BYPOSITION | MF_POPUP | MF_STRING, (UINT_PTR)nuzlocke, L"&Nuzlocke");
    }
""" + MENU2_ORIGINAL + END

ACT_BEGIN = "    /* >>> mods: what the Cheats tab does (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
ACT_ORIGINAL = """\
    case MI_UPDATE: update_menu(); break;
"""
ACT_PATCHED = ACT_BEGIN + r"""
    case 360: case 361: case 362: case 363: case 365: case 366: case 367: {
        void mod_cheatwin_show(void);
        void mod_nuzlocke_show(void);
        void mod_battle_show(void);
        if (id == 367) { mod_battle_show(); break; }
        if (id == 366) {
            info_box(SDL_MESSAGEBOX_INFORMATION, "Nuzlocke",
                "A Nuzlocke is a challenge run: whoever falls stays fallen, and the game is shuffled so you can't know it by heart.\n\n"
                "Settings... opens the rules (permadeath, the hero's death ends the run, soul link), the punishments and the randomizers "
                "(monsters, skill trees, spells, stat growth, drops, shops). The rules work at once; the randomizers take effect when the game starts again, "
                "and every player of a session must use the same ones.", g_win);
            break;
        }
        if (id == 365) { mod_nuzlocke_show(); break; }
        int mod_editor_launch(const char* tab), mod_open_url(const char* url);
        if (id == 361) {
            info_box(SDL_MESSAGEBOX_INFORMATION, "Cheats",
                "Cheats... opens the cheat list in a window of its own: every cheat is a switch, and it works at once while you play "
                "(no restart, no rebuild). Pick one of several (experience x2, x4...) where the list says so.\n\n"
                "Save editor opens your save in the editor website; Export there puts the edited save into the game, which starts again with it. Treasure maps opens the map search website.\n\n"
                "Your save is not touched by the cheats (copies go to mods\system\save-backups). Updating the game from the Help menu keeps this tab.", g_win);
            break;
        }
        if (id == 362) { if (!mod_editor_launch("party")) info_box(SDL_MESSAGEBOX_ERROR, "Save editor", "The editor couldn't be started: the editor helper is missing. Run Install cheats.bat again.", g_win); break; }
        if (id == 363) { if (!mod_open_url("https://dqix.github.io/Grotto-Searcher/")) info_box(SDL_MESSAGEBOX_ERROR, "Treasure maps", "The browser couldn't be opened. The page is https://dqix.github.io/Grotto-Searcher/", g_win); break; }
        mod_cheatwin_show();
        break;
    }
    case 364: {   /* the save editor pressed Export while the game runs (dqix-editor.exe, mod_menu.c): take the save, start again with it */
        static uint8_t ed[0x10000], base[0x10000];
        uint32_t en = 0, bn = 0, cn = 0;
        int mod_editor_take(uint8_t*, uint32_t*, uint8_t*, uint32_t*);
        void mod_editor_result(const char*);
        if (!mod_editor_take(ed, &en, base, &bn)) break;
        if (session_requested()) {
            mod_editor_result("session");
            info_box(SDL_MESSAGEBOX_INFORMATION, "Save editor", "Leave the session first (Wireless menu), then press Export in the editor again.", g_win);
            break;
        }
        if (backup_check_image(ed, en) == 0) { mod_editor_result("bad"); break; }
        const uint8_t* cur = backup_image(&cn);
        if (bn != cn || memcmp(base, cur, cn)) {   /* the game saved after the editor read the save */
            if (!ask_yes("Save editor", "You saved in the game after the editor opened your save.\n\nUse the editor's save anyway? "
                         "What you saved since then is lost (your current save is kept as a copy in the save-backups folder, next to the game).", "Use the editor's save")) {
                mod_editor_result("cancel");
                break;
            }
        }
        char kept[300];
        save_backup_copy(kept, sizeof kept);
        if (!kept[0]) { mod_editor_result("nobackup"); break; }
        mod_editor_result("ok");
        backup_replace(ed, en);
        restart_with(NULL);
        break;
    }
""" + ACT_ORIGINAL + END
ACT_PATCHED = ACT_PATCHED.replace(ACT_BEGIN + "\n", ACT_BEGIN, 1)

UPD_BEGIN = "    /* >>> mods: put the mods back after an update (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
UPD_ORIGINAL = r"""    "echo == Building the game again from your ROM (this can take a while)\r\n"
"""
UPD_PATCHED = UPD_BEGIN + UPD_ORIGINAL + r"""    "if exist \"mods\\Apply cheats.bat\" call \"mods\\Apply cheats.bat\" apply\r\n"
""" + END

# (file in runtime/, the lines as the game has them, with the mods, first marker line, what it is)
# The marker lines (*_BEGIN, WRAP_BEGIN) are found by their exact text in games that already have them: never reword
# them (they still name "Play with mods.bat", the patcher's old name), or those games keep an orphaned block.
SITES = [
    ("input.c", INPUT_ORIGINAL, INPUT_PATCHED, INPUT_BEGIN, "Cheats with friends"),
    ("card.c", CARD_ORIGINAL, CARD_PATCHED, CARD_BEGIN, "Instant loading only alone"),
    ("card.c", DATA_ORIGINAL, DATA_PATCHED, DATA_BEGIN, "Metal slimes only"),
    ("menu_win32.c", MENU_ORIGINAL, MENU_PATCHED, MENU_BEGIN, "Cheats tab in the menu bar"),
    ("frontend_sdl.c", ACT_ORIGINAL, ACT_PATCHED, ACT_BEGIN, "Cheats tab: what it does"),
    ("update.c", UPD_ORIGINAL, UPD_PATCHED, UPD_BEGIN, "Cheats stay after an update of the game"),
]
NEEDS_INPUT = {"data", "act"}                                       # they call the mods' own files, which come with "input"
SITE_KEYS = ["input", "card", "data", "menu", "act", "update"]   # SITES in order; "wrap" is the lines in wrap.txt (live code mods)
VARIANTS = {"menu": [(MENU2_ORIGINAL, MENU2_PATCHED, MENU2_BEGIN)]}    # other forms of a place: tried after the first one
FILES = ["mod_cheats.c", "ar_engine.h", "mod_data.c", "livepatch.c", "mod_cheatwin.c", "nuzlocke.c"]       # belong to the first site
MENU_FILES = ["mod_menu.c"]                                  # belong to the "what it does" site (frontend_sdl.c)
GONE = ["mod_plugins.c", "dqix_plugin.h"]                   # files of earlier versions of the mods: taken out of runtime/ again


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def wanted(root):
    try:
        for line in open(os.path.join(root, "mods", "settings.txt"), encoding="utf-8-sig"):
            m = re.match(r"\s*sync_cheats\s*=\s*(\w+)", line)
            if m:
                return m.group(1).lower() not in ("no", "n", "off", "false", "0")
    except OSError:
        pass
    return True


WRAP_BEGIN = "# >>> mods: lower-level characters get more experience (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back)"
WRAP_END = "# <<< mods"
WRAP_LINES = """main 0202053c lowlvl
ov023 021f4098 lowexp
ov017 02196430 enccheck
main 0208a91c noflee
ov017 021970a0 firststrike
"""
WRAP_FILES = ["lowexp.c", "vanish.c", "noflee.c", "firststrike.c"]


def wrap_site(root, on, extra=""):
    """lowexp.c and its two lines in wrap.txt (USA addresses; region.py moves them). -> changed"""
    changed = False
    path = os.path.join(root, "wrap.txt")
    if not os.path.isfile(path):
        return False
    text = read(path)
    cr, lf = chr(13), chr(10)
    nl = cr + lf if cr + lf in text else lf
    pat = r"\r?\n?" + re.escape(WRAP_BEGIN) + r".*?" + re.escape(WRAP_END) + r"\r?\n?"
    stripped = re.sub(pat, lambda m: nl, text, flags=re.S)
    stripped = stripped.rstrip(cr + lf) + nl
    new = stripped + (nl + WRAP_BEGIN + nl + (WRAP_LINES + extra).replace(lf, nl) + WRAP_END + nl if on else "")
    if new != text:
        write(path, new)
        changed = True
    for f in WRAP_FILES:
        dst = os.path.join(root, "runtime", f)
        if on:
            src = read(os.path.join(root, "mods", "system", "src", "runtime", f))
            if not os.path.isfile(dst) or read(dst) != src:
                write(dst, src)
                changed = True
        elif os.path.isfile(dst):
            os.remove(dst)
            changed = True
    return changed


def livepatch_plan(root):
    """The functions the build wraps so that code mods can be switched while the game runs, and the instruction sites in them.
    -> (functions [(module, start, usa_start)], sites [(module, address, function number, allowed words)]) or None if the game isn't built yet.
    A function another mod already wraps, a Thumb function and anything that is not in a known function is left out: the code
    mods that touch those stay "built in" (rebuild)."""
    if not os.path.isfile(os.path.join(root, "build", "recomp", "dispatch_table.c")):
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import catalog
    rom = catalog.Rom(root)
    _, entries, _ = catalog.build(root)
    fixed = set()
    for line in WRAP_LINES.splitlines():
        w = line.split()
        if len(w) >= 2:
            fixed.add((w[0], int(w[1], 16)))
    found, words = {}, {}
    for e in entries:
        if e["id"].startswith("launch:") or not (e["kind"] == "code" or e.get("lp")):
            continue
        for n, a, w in e["patch"]:
            m = rom.by_name.get(n)
            if m is None or a & 3:
                continue
            f = rom.func_at(m, a)
            if f is None or f[2]:
                continue
            usa = rom.from_rom(f[0]) if n == "main" else f[0]
            if (n, usa) not in fixed:
                found[(n, a)] = (f[0], usa)
                words.setdefault((n, a), set()).add(w)
    sites = sorted(found)
    fns = sorted({(n, found[(n, a)][0], found[(n, a)][1]) for n, a in sites})
    num = {(n, st): i for i, (n, st, usa) in enumerate(fns)}
    return fns, [(n, a, num[(n, found[(n, a)][0])], sorted(words[(n, a)])) for n, a in sites]


def livepatch_files(root, on):
    """runtime/mod_livepatch_tab.c, mods/system/bin/livepatch.txt and the extra wrap.txt lines. -> (changed, wrap lines, functions, sites)"""
    plan = livepatch_plan(root) if on else None
    fns, sites = plan if plan else ([], [])
    tab = ["/* written by mods/system/tools/apply_runtime_mod.py: the functions that live code mods can patch (see livepatch.c) */",
           "#include <stdint.h>", '#include "cpu.h"',
           "void lp_call(unsigned, Cpu*, void (*)(Cpu*));"]
    tab.append("const unsigned g_lp_nfn = %d, g_lp_nsite = %d;" % (len(fns), len(sites)))
    first, count = {}, {}
    for k, (n, a, fi, ws) in enumerate(sites):
        first.setdefault(fi, k)
        count[fi] = count.get(fi, 0) + 1

    def arr(t, name, vals):
        return "const %s %s[%d] = { %s };" % (t, name, max(1, len(vals)), ", ".join(vals) if vals else "0")
    tab.append(arr("uint32_t", "g_lp_entry", ["0x%08xu" % st for n, st, usa in fns]))
    tab.append(arr("uint16_t", "g_lp_first", [str(first.get(i, 0)) for i in range(len(fns))]))
    tab.append(arr("uint16_t", "g_lp_count", [str(count.get(i, 0)) for i in range(len(fns))]))
    tab.append(arr("uint16_t", "g_lp_site_fn", [str(fi) for n, a, fi, ws in sites]))
    tab.append(arr("uint32_t", "g_lp_site_addr", ["0x%08xu" % a for n, a, fi, ws in sites]))
    # the only instruction words a site may be patched with: the ones the catalog's code mods use (a peer in a session
    # can't make the interpreter run anything else)
    allw, wfirst = [], []
    for n, a, fi, ws in sites:
        wfirst.append(len(allw)); allw += ["0x%08xu" % x for x in ws]
    tab.append(arr("uint32_t", "g_lp_words", allw))
    tab.append(arr("uint16_t", "g_lp_wfirst", [str(x) for x in wfirst]))
    tab.append(arr("uint8_t", "g_lp_wcount", [str(len(ws)) for n, a, fi, ws in sites]))
    for i in range(len(fns)):
        tab.append("void wrap_lp%d_orig(Cpu* c); void wrap_lp%d(Cpu* c) { lp_call(%d, c, wrap_lp%d_orig); }" % (i, i, i, i))
    text = "\n".join(tab) + "\n"
    changed = False
    dst = os.path.join(root, "runtime", "mod_livepatch_tab.c")
    if on:
        if not os.path.isfile(dst) or read(dst).replace("\r\n", "\n") != text:
            write(dst, text)
            changed = True
    elif os.path.isfile(dst):
        os.remove(dst)
        changed = True
    lp = ["# The instruction sites the built game can patch while it runs (apply_runtime_mod.py): number, module, address, function"]
    lp += ["%d %s %08x %08x" % (k, n, a, fns[fi][1]) for k, (n, a, fi, ws) in enumerate(sites)]
    out = os.path.join(root, "mods", "system", "bin", "livepatch.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    old = read(out) if os.path.isfile(out) else ""
    if old.replace("\r\n", "\n") != "\n".join(lp) + "\n":
        write(out, "\n".join(lp) + "\n")
    wrap = "".join("%s %08x lp%d\n" % (n, usa, i) for i, (n, st, usa) in enumerate(fns))
    return changed, wrap, len(fns), len(sites)


MARK_RE = re.compile(r"[ \t]*/\* >>> mods:.*?/\* <<< mods \*/\r?\n", re.S)


def fingerprint(text):
    import hashlib
    text = re.sub(r"\r?\n?" + re.escape(WRAP_BEGIN) + r".*?" + re.escape(WRAP_END) + r"\r?\n?", "\n", MARK_RE.sub("", text), flags=re.S)
    return hashlib.sha1(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:16]


def mods_print(root):
    """the mods' own part (their files and this patcher): a newer version of the mods tries a left-out place again too"""
    import hashlib
    h = hashlib.sha1()
    src = os.path.join(root, "mods", "system", "src", "runtime")
    for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        h.update(f.encode() + open(os.path.join(src, f), "rb").read().replace(b"\r\n", b"\n"))
    h.update(open(os.path.abspath(__file__), "rb").read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:8]


def off_list(root):
    """mods/system/bin/sites-off.txt: places a build failed on: {key: fingerprint of the game's file then}"""
    out = {}
    try:
        for line in open(os.path.join(root, "mods", "system", "bin", "sites-off.txt"), encoding="utf-8"):
            p = line.split()
            if len(p) >= 2 and not line.startswith("#"):
                out[p[0]] = p[1]
    except OSError:
        pass
    return out


def write_off_list(root, off):
    path = os.path.join(root, "mods", "system", "bin", "sites-off.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not off:
        if os.path.isfile(path):
            os.remove(path)
        return
    write(path, "# places of the mods a build of the game failed on (repatch.py): left out until the game's file changes\n"
          + "".join(f"{k} {v}\n" for k, v in sorted(off.items())))


def pristine_of(root, name):
    """the game's own file without the mods: the current one when it has no markers (it is kept), else the kept copy,
    else (a game patched by an older version of this) the current one with each known place put back."""
    path = os.path.join(root, "runtime", name)
    keep = os.path.join(root, "mods", "system", "bin", "pristine", name)
    text = read(path)
    if ">>> mods:" not in text:
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        if not os.path.isfile(keep) or read(keep) != text:
            write(keep, text)
        return text
    if os.path.isfile(keep):                            # (an update always brings the file without markers: then it is kept anew)
        return read(keep)
    nl = "\r\n" if "\r\n" in text else "\n"
    for i, (n, original, patched, begin, what) in enumerate(SITES):
        if n != name:
            continue
        for orig, pat, beg in [(original, patched, begin)] + VARIANTS.get(SITE_KEYS[i], []):
            b, e = beg.replace("\n", nl), END.replace("\n", nl)
            if b in text:
                text = re.sub(re.escape(b) + r".*?" + re.escape(e), lambda m: orig.replace("\n", nl), text, count=1, flags=re.S)
    if ">>> mods:" in text:
        return None
    os.makedirs(os.path.dirname(keep), exist_ok=True)
    write(keep, text)
    return text


TOKEN = re.compile(r'"(?:\\.|[^"\\\n])*"|\w+|\S')


def loose_find(text, original):
    """where the original lines are when an update changed only spaces, line breaks or comments: (start, end), or None
    when they aren't there or are there more than once"""
    lines = []
    for line in original.strip("\n").split("\n"):
        code = re.sub(r"/\*.*?\*/\s*$|//.*$", "", line).strip()
        if code:
            lines.append(TOKEN.findall(code))
    if not lines:
        return None
    gap = r"(?:\s|/\*.*?\*/|//[^\n]*\n)*"
    body = gap.join(gap.join(re.escape(t) for t in toks) for toks in lines)
    pat = re.compile(r"^[ \t]*" + body + r"[ \t]*(?:/\*.*?\*/|//[^\n]*)?[ \t]*\r?\n", re.M | re.S)
    found = list(pat.finditer(text))
    return (found[0].start(), found[0].end()) if len(found) == 1 else None


def put_site(text, original, patched):
    """one place into the text: (new text, how) or (None, "") when it isn't there"""
    nl = "\r\n" if "\r\n" in text else "\n"
    o, p = original.replace("\n", nl), patched.replace("\n", nl)
    if o in text:
        return text.replace(o, p, 1), "exact"
    span = loose_find(text, o)
    if span:
        actual = text[span[0]:span[1]]
        if not actual.endswith(nl):
            actual = actual.rstrip("\r\n") + nl
        return text[:span[0]] + (p.replace(o, actual) if o in p else p) + text[span[1]:], "relaxed"
    return None, ""


def patch_file(root, name, on_keys, report):
    """the game's file = its own copy + the places that are on. -> (changed, {key: state}) with state on / off / unknown"""
    path = os.path.join(root, "runtime", name)
    states = {}
    if not os.path.isfile(path):
        return False, {SITE_KEYS[i]: "unknown" for i, site_ in enumerate(SITES) if site_[0] == name}
    cur = read(path)
    base = pristine_of(root, name)
    if base is None:                                    # can't tell the game's own lines apart: as before, place by place
        changed = False
        for i, (n, original, patched, begin, what) in enumerate(SITES):
            if n == name:
                did, st = site(root, name, original, patched, begin, SITE_KEYS[i] in on_keys)
                changed |= did; states[SITE_KEYS[i]] = st; report.append(f"{SITE_KEYS[i]} {st} (in place)")
        return changed, states
    text = base
    for i, (n, original, patched, begin, what) in enumerate(SITES):
        if n != name:
            continue
        key = SITE_KEYS[i]
        if key not in on_keys:
            states[key] = "off"; report.append(f"{key} off"); continue
        for k, (orig, pat, beg) in enumerate([(original, patched, begin)] + VARIANTS.get(key, [])):
            new, how = put_site(text, orig, pat)
            if new is not None:
                text = new; states[key] = "on"
                report.append(f"{key} on ({how}{', form ' + str(k + 1) if k else ''})")
                break
        else:
            states[key] = "unknown"; report.append(f"{key} not found")
    if text != cur:
        write(path, text)
    return text != cur, states


def site(root, name, original, patched, begin, on):
    """-> (changed, state) with state "on", "off" or "unknown" (the file isn't what this expects)."""
    path = os.path.join(root, "runtime", name)
    if not os.path.isfile(path):
        return False, "unknown"
    text = read(path)
    nl = "\r\n" if "\r\n" in text else "\n"
    original, patched = original.replace("\n", nl), patched.replace("\n", nl)
    begin, end = begin.replace("\n", nl), END.replace("\n", nl)
    block = re.escape(begin) + r".*?" + re.escape(end)
    if begin in text:
        new = re.sub(block, lambda m: patched if on else original, text, count=1, flags=re.S)
    elif original in text:
        new = text.replace(original, patched, 1) if on else text
    else:
        return False, "unknown"
    if new != text:
        write(path, new)
    return new != text, "on" if on else "off"


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if not os.path.isfile(os.path.join(root, "runtime", "input.c")):
        print("   No runtime\\input.c here: is this the DQIX Enhanced folder?", root)
        return 1
    on = wanted(root)
    changed = False
    if len(sys.argv) > 3 and sys.argv[2] == "--off":     # repatch.py: a build failed on these places
        off = off_list(root)
        for key in sys.argv[3].split(","):
            name = SITES[SITE_KEYS.index(key)][0] if key in SITE_KEYS else "wrap.txt"
            pp = os.path.join(root, "runtime" if key in SITE_KEYS else "", name)
            base = pristine_of(root, name) if key in SITE_KEYS and os.path.isfile(pp) else (read(pp) if os.path.isfile(pp) else "")
            off[key] = fingerprint(base or "") + mods_print(root)
        write_off_list(root, off)
    off = off_list(root)
    fresh = {}
    for key, fp in off.items():                          # a place stays out only while the game's file is the one the build failed with
        name = SITES[SITE_KEYS.index(key)][0] if key in SITE_KEYS else "wrap.txt"
        pp = os.path.join(root, "runtime", name) if key in SITE_KEYS else os.path.join(root, name)
        now = (pristine_of(root, name) if key in SITE_KEYS else read(pp)) if os.path.isfile(pp) else None
        if now is not None and fingerprint(now) + mods_print(root) == fp:
            fresh[key] = fp
        else:
            print(f"   The game or the mods changed since the build failed with \"{key}\": trying it again.")
    if fresh != off:
        write_off_list(root, fresh)
    off = fresh
    on_keys = {k for k in SITE_KEYS if on and k not in off}
    report, states = [], {}
    for name in dict.fromkeys(n for n, *_ in SITES):     # (input.c first: the places below call into its files)
        did, st = patch_file(root, name, on_keys, report)
        changed |= did
        states.update(st)
        if states.get("input") != "on":
            on_keys -= NEEDS_INPUT
    for i, (name, original, patched, begin, what) in enumerate(SITES):
        state = states.get(SITE_KEYS[i], "unknown")
        if state == "off" and on and SITE_KEYS[i] in off:
            print(f"   [off] {what}: the game didn't build with it (mods\\system\\bin\\build.log); it is tried again after the next update.")
        files = FILES if i == 0 else MENU_FILES if name == "frontend_sdl.c" else []
        for f in files:          # the mods' own files go with their call in the game: without it they would be dead weight
            dst = os.path.join(root, "runtime", f)
            if state == "on":
                src = read(os.path.join(root, "mods", "system", "src", "runtime", f))
                if not os.path.isfile(dst) or read(dst) != src:
                    write(dst, src)
                    changed = True
            elif os.path.isfile(dst):
                os.remove(dst)
                changed = True
        if state == "on":
            print(f"   [on] {what}")
        elif state == "unknown":
            print(f"   [skipped] {what}: this version of the game has runtime\\{name} written differently."
                  + ("  Cheats still work when you play alone." if i == 0 else "  Cheats can still be switched in the files (see mods\\README.txt)."
                     if name in ("menu_win32.c", "frontend_sdl.c", "update.c") else "  \"Instant loading\" stays off."))
    for f in GONE:
        dst = os.path.join(root, "runtime", f)
        if os.path.isfile(dst):
            os.remove(dst)
            changed = True
    wrap_on = on and states.get("input") == "on" and "wrap" not in off      # live code mods need the mods' own files (input)
    lp_changed, lp_wrap, nfn, nsite = livepatch_files(root, wrap_on)
    changed |= lp_changed
    if wrap_site(root, wrap_on, lp_wrap):
        changed = True
    report.append("wrap " + ("on" if wrap_on else "off"))
    rp = os.path.join(root, "mods", "system", "bin", "repatch.txt")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    write(rp, "# how each place of the mods was found in the game's code (apply_runtime_mod.py)\n" + "\n".join(report) + "\n")
    if wrap_on and nfn:
        print(f"   [on] Code mods switch while the game runs: {nsite} instruction sites in {nfn} functions")
    if wrap_on:
        print("   [on] Lower-level characters get more experience (when switched on in the Cheats window)")
    elif on and "wrap" in off:
        print("   [off] Code mods that switch while the game runs: the game didn't build with them; tried again after the next update.")
    if not on:
        print("   The mods' part of the game: off (sync_cheats = no).")
    if changed:
        print("   The game will be rebuilt.")
    return 10 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
