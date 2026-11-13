#!/usr/bin/env python3
"""Put the mods' part of the game itself in place.

  apply_runtime_mod.py [project folder]

1. Live cheats that also work while playing with friends: it copies
   mod_cheats.c and ar_engine.h into runtime/ (the build compiles every .c file
   there) and changes one place in runtime/input.c so each frame's input goes
   through them.
2. "Instant loading" (the cheat menu) only when you play alone: one place in
   runtime/card.c. In a session every PC has to take the same time for the
   cartridge, or the PCs stop agreeing within two seconds ("OUT OF SYNC at
   frame 120"). With this the game keeps the cartridge's real timing whenever
   a session runs, whatever the menu says.

Each change sits between two marker lines. An update of the game brings fresh
files without them; running this again (Play with mods.bat does, every time)
puts them back. If a file ever looks different from what this expects, that
change is left out and said so: nothing is half-changed.

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
    item(cheats, 360, L"Cheats &enabled...");              /* 360, 361: handled in frontend_sdl.c, mod_menu.c */
    sep(cheats);
    item(cheats, 361, L"&What is this?");
""" + MENU_ORIGINAL + END

ACT_BEGIN = "    /* >>> mods: what the Cheats tab does (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
ACT_ORIGINAL = """\
    case MI_UPDATE: update_menu(); break;
"""
ACT_PATCHED = ACT_BEGIN + r"""
    case 360: case 361: {
        int mod_menu_available(void), mod_menu_launch(void);
        if (id == 361) {
            info_box(SDL_MESSAGEBOX_INFORMATION, "Cheats",
                "Cheats enabled closes the game and opens the cheat menu: every cheat is a switch there, and its Play button "
                "starts the game again with them (the first time it builds them in: a few minutes).\n\n"
                "Your save is not touched (copies go to mods\\system\\save-backups). Updating the game from the Help menu keeps this tab.", g_win);
            break;
        }
        if (session_requested()) { info_box(SDL_MESSAGEBOX_INFORMATION, "Cheats", "Not while playing with friends: leave the session first.", g_win); break; }
        if (!mod_menu_available()) { info_box(SDL_MESSAGEBOX_ERROR, "Cheats", "The mods folder isn't next to the game. Run Install mods.bat first.", g_win); break; }
        if (!ask_yes("Cheats", "The game closes and the cheat menu opens. Its Play button starts the game again with your cheats.\n\nSave your adventure first (in the game) if you haven't.", "Enable cheats")) break;
        backup_flush(); settings_save();
        if (mod_menu_launch()) exit(0);
        info_box(SDL_MESSAGEBOX_ERROR, "Cheats", "The cheat menu couldn't be started. Use mods\\Play with mods.bat.", g_win);
        break;
    }
""" + ACT_ORIGINAL + END
ACT_PATCHED = ACT_PATCHED.replace(ACT_BEGIN + "\n", ACT_BEGIN, 1)

UPD_BEGIN = "    /* >>> mods: put the mods back after an update (mods/tools/apply_runtime_mod.py; an update removes this, Play with mods.bat puts it back) */\n"
UPD_ORIGINAL = r"""    "echo == Building the game again from your ROM (this can take a while)\r\n"
"""
UPD_PATCHED = UPD_BEGIN + UPD_ORIGINAL + r"""    "if exist \"mods\\Play with mods.bat\" call \"mods\\Play with mods.bat\" apply\r\n"
""" + END

# (file in runtime/, the lines as the game has them, with the mods, first marker line, what it is)
SITES = [
    ("input.c", INPUT_ORIGINAL, INPUT_PATCHED, INPUT_BEGIN, "Cheats with friends"),
    ("card.c", CARD_ORIGINAL, CARD_PATCHED, CARD_BEGIN, "Instant loading only alone"),
    ("card.c", DATA_ORIGINAL, DATA_PATCHED, DATA_BEGIN, "Metal slimes only"),
    ("menu_win32.c", MENU_ORIGINAL, MENU_PATCHED, MENU_BEGIN, "Cheats tab in the menu bar"),
    ("frontend_sdl.c", ACT_ORIGINAL, ACT_PATCHED, ACT_BEGIN, "Cheats tab: what it does"),
    ("update.c", UPD_ORIGINAL, UPD_PATCHED, UPD_BEGIN, "Cheats stay after an update of the game"),
]
FILES = ["mod_cheats.c", "ar_engine.h", "mod_data.c"]       # belong to the first site
MENU_FILES = ["mod_menu.c"]                                  # belong to the "what it does" site (frontend_sdl.c)


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
"""
WRAP_FILES = ["lowexp.c", "vanish.c", "noflee.c"]


def wrap_site(root, on):
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
    new = stripped + (nl + WRAP_BEGIN + nl + WRAP_LINES.replace(lf, nl) + WRAP_END + nl if on else "")
    if new != text:
        write(path, new)
        changed = True
    for f in WRAP_FILES:
        dst = os.path.join(root, "runtime", f)
        if on:
            src = read(os.path.join(root, "mods", "system", "src", f))
            if not os.path.isfile(dst) or read(dst) != src:
                write(dst, src)
                changed = True
        elif os.path.isfile(dst):
            os.remove(dst)
            changed = True
    return changed


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
    for i, (name, original, patched, begin, what) in enumerate(SITES):
        did, state = site(root, name, original, patched, begin, on)
        changed |= did
        files = FILES if i == 0 else MENU_FILES if name == "frontend_sdl.c" else []
        for f in files:          # the mods' own files go with their call in the game: without it they would be dead weight
            dst = os.path.join(root, "runtime", f)
            if state == "on":
                src = read(os.path.join(root, "mods", "system", "src", f))
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
                  + ("  Cheats still work when you play alone." if i == 0 else "  The cheat menu still starts with Play with mods.bat."
                     if name in ("menu_win32.c", "frontend_sdl.c", "update.c") else "  \"Instant loading\" stays off."))
    if wrap_site(root, on):
        changed = True
    if on:
        print("   [on] Lower-level characters get more experience (when switched on in the menu)")
    if not on:
        print("   The mods' part of the game: off (sync_cheats = no).")
    if changed:
        print("   The game will be rebuilt.")
    return 10 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
