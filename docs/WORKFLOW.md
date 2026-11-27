# Working faster on the cheats

One rule: **do the cheapest check that can catch the mistake, and never repeat a check whose inputs did not change.**
`mods\system\dev.bat` (or `python mods\system\tools\dev.py`) does all of it.

## The loop

1. Edit in this repo (`mods\...`). The repo is the source of truth; the game folder only receives copies.
2. `dev test fast` (about 1.5 min, 5 s when nothing changed). It deploys the changed files to the game folder first.
3. Pick the extra check from the table below for what you touched.
4. `dev test full` before you push (about 8 min, only the tests whose inputs changed are run).
5. Add a line to `docs/NOTES.md`, commit, push. `dev deploy` already put the working files in the game folder.

## Which check for which change

| You changed | Run | Why this and not more |
|---|---|---|
| `mod_cheatwin.c` (the Cheats window) | `dev test cheatwin` after `mods\Apply.bat apply` (the test uses the built game) | opens the window, switches a cheat on like a click, checks RAM + state file |
| `EditorHost.cs` (save editor helper) | `dev test editor` | starts the helper on a scratch save: token checks, export + backup, language box |
| `catalog.py`, `cheats\` | `dev test static` then `dev test all-quick` | static reads every catalog line in 0.1 s; all-quick sends 12 cheats to a headless game |
| `mod_cheats.c`, `ar_engine.h` | `dev test live session all-single all-session` after a build | the only code that runs inside the game and inside friends' sessions |
| `firststrike.c`, `noflee.c`, `vanish.c` (switches that wrap a game function) | `dev test firststrike` / `test_noflee.py` / `test_vanish.py` / `dev test vanish-walk vanish-ghost` (both also in `test full`) (`TEST_SAVE` = a save in a dungeon) | the wrapped function is reached in a real battle start |
| Fun cheats, undo (`mod_cheats.c` SET_UNDO, `catalog.py` UNDO) | `dev test live-fast undo-fun` (`TEST_SAVE` as above) | the cheat's bytes are back after switching off, in RAM and in the pictures |
| `nuzlocke.c`, the Nuzlocke page (OFF: `NUZLOCKE_ENABLED` in `apply_code_mods.py`, `NZ_ENABLED` in nuzlocke.c; both on to test) (`mod_data.c` encounters too) | `dev test nuzlocke` (`TEST_SAVE` = a party in a dungeon; `nz-data` alone needs no save) | `nz-data` = every randomizer on the ROM's tables on the host; the rest = every rule in a real game, headless (permadeath, persist, link, hero, gold, new run, a whole battle, a KO in battle). Run it on the EU and the USA game folder |
| `challenges.c`, the Challenges page (`mod_cheats.c` switches 02F5A610..628) | `dev test noabil battle-live` (`tests/dqix_dungeon.sav`, picked automatically: the party in a dungeon, a church save has no battle) | "No abilities": the hero's Dragon Slash becomes Defend with the switch on, not with it off; the battle cheats in a real forced battle |
| `ar_engine.h`, a cheat with buttons | `dev test keys keys-bag zoom-grotto` (`TEST_SAVE`) | the buttons really pressed in the field / bag / during Zoom, RAM against `tests/ar_port.py` |
| `livepatch.c`, a live code mod | `dev test livepatch` (needs `TEST_SAVE` = a save in a dungeon) | runs patched functions in the interpreter, compares with the compiled code |
| a code mod (patch) | `dev scratch` (add `--rounds` for the x4/x8/Always Fail alternatives) | builds in a scratch copy in about a minute, your `game\` is not touched |
| `forcebtl.c`, the monster choices (`catalog.py` "Battle any monster") | `python mods\system\tests\test_launchers.py <game folder> <work dir> 0 999 10` after a build (about 5 min; `... 12` as last argument = every 12th) | every choice switched on in a dungeon must start its battle |
| only tests / docs | `dev test static` | nothing in the game changed |
| `mod_control.c`, `tools/drive.py` (remote control) | `dev test control` after a build | a headless game waits, takes input, shows the screen, takes a cheat, ends |

## Trying a mod by hand: the game one command at a time

`python mods\system\tools\drive.py` plays a headless game that stands still between commands (no window, no sound,
always on a copy of the save). For looking at what a change does, without writing a test first.

```
drive.py start --field                        load the test save, stand in the field
drive.py do "X .:60"                          press X, let 60 frames pass
drive.py do "touch=128,100:6 .:30"            stylus on the bottom screen (256 x 192)
drive.py cheat file:cheats/max-gold.txt on    a live cheat, arrives while the next frames run
drive.py read 020F6D48 4                      DS main RAM
drive.py log                                  what the mods printed
drive.py stop
```

`start` and `do` print the frame and the path of a PNG of both screens. Always `stop` at the end: `dev test` refuses to
run while a `dqix.exe` runs (a forgotten game ends itself after 30 minutes without a command).

## Why it is fast

- **Tiers**: `fast` = static + short live + short session + 12-cheat run + editor. `full` = static + the long live, session and all-cheat runs + the Cheats window test + editor. `livepatch` runs only by name.
- **Cache**: `mods\system\bin\test-cache.json` keeps a hash of every input (sources, catalog, cheats, `dqix.exe`, `dqixcore.dll`). A test that passed with the same hash is skipped; failures always rerun. `--force` ignores it.
- **Parallel**: tests that only need a headless game run together on their own ports and work folders (`--jobs`, default 3).
- **Alone at the end**: the editor test. `dev` refuses to run while any `dqix.exe` runs (your own game would collide with the test games).
- **Sized by message length**: cheat messages travel 16 bits per frame, so `test_all.py` computes its frame budget from the data instead of a fixed guess.
- **Scratch builds** instead of touching `game\`: all code mods build in about a minute.
- **Static guards** catch what the compiler would catch later: C# 5 only (`$"..."`, `?.`, `nameof`), unreadable catalog lines, a blocked cheat switched on.

## Habits that save time

- Never play the game while tests run; every test except `cheatwin` sets `DQIX_CHEATWIN_OFF=1` so the Cheats window sends nothing by itself.
- Test addresses must be unused RAM (`0x02340000` region is zero); text areas change under you.
- In a session only `sync ... same` lines count; each PC dumps its own DS.
- PowerShell `>` writes UTF-16: set `PYTHONIOENCODING=utf-8` and use `Out-File -Encoding utf8` (dev.py already does).
- Long runs go in the background; poll the result file, do not sleep in the foreground.
- Do not edit big files with here-docs through a shell: use the editor tool or a small script file.

## Moving to another PC

1. Install Python 3.8+ (or just build the game once: the MSYS2 tools bring their own).
2. Build the game once with the project's `BUILD.bat` (needs your own ROM in `rom\`).
3. Run `Install.bat` from a clone of this repo (or from the release zip): it asks for the game folder, copies `mods\` and runs `Apply.bat`.
4. `mods\system\dev.bat doctor` lists anything still missing and how to fix it.
5. Working from the repo on that PC: `mods\system\dev-root.txt` (one line, the game folder) or `set DQIX_ROOT=...`.

Nothing in the tools is tied to one PC: the game folder is found, the temp folder is the system's, MSYS2 is looked up
from `mods\system\msys2-root.txt`.

## Reverse engineering playbook (finding what the game does)

Research result (2026-11): public DQIX material is only AR address lists (almarsguides, R4 database) - no RAM map or symbols exist. The DS-wide
tools (Ghidra + NTRGhidra loader, DeSmuME debugger) are not needed here: the game is already recompiled to C with the ROM's own function
names, and the runtime has the hooks a debugger would give. So the way to "extend RE" is to use these, and write every finding down.

`python mods\system\tools\dqre.py [--root GAME] <cmd>`:

| Question | Command / switch |
|---|---|
| Which function holds this address? | `dqre.py func 02096e20` |
| Which functions have a name like ...? | `dqre.py names flee` |
| What does this AR code touch (data or code, which function)? | `dqre.py ar "02345678 0000FFFF"` |
| What changed in RAM between two moments? | `DQIX_RAMDUMP=dir,300,900` then `dqre.py diff dir\ram000300.bin dir\ram000900.bin --names` |
| Value at an address in a dump | `dqre.py ram dir\ram000300.bin 02345678 8` |
| Who writes this word? | `DQIX_WATCH=02345678 DQIX_WATCHREGS=1` (log has the writer's registers; map with `func`) |
| Where does the game screen show it? | `DQIX_DUMP=dir,30` frames -> contact sheet |
| Change the AI / a decision | wrap the function in `wrap.txt` (see `noflee.c`), never patch instructions |

Method: (1) hypothesis from the R4 name/`ar` output, (2) two RAM dumps around the action (before/after), `diff` narrows to a few ranges,
(3) `DQIX_WATCH` on one of them names the writer, (4) `func` names it, (5) write the result (address, meaning, how found) in `docs/NOTES.md`
and, if it is a lesson, in the memory `dqix-lessons.md`. Headless runs are deterministic for the same exe + `DQIX_INPUT`, so every
experiment can be repeated and compared.

Tests run without the 60 fps pacing (`DQIX_FAST=1`, set by `dev.py` for every test except `cheatwin`): `test full` takes about 3 minutes instead of 8 (`all-single` 420 s -> 65 s, `all-session` 455 s -> 75 s). `tests/dqix_dungeon.sav` (gitignored, from `save-backups/dqix-20261113-170934.sav`) is the default `TEST_SAVE`; `dqix_test.sav` stands in a church.

## Releasing

`python release/make_release.py` checks the files that go to players (ASCII and CRLF in .bat/.ps1, PowerShell parse, batch labels, Python/sh syntax, no dev files), builds `dist/release.zip` and prints the release notes; it publishes nothing. Only when the user asks for a release: `python release/make_release.py --publish` (commit first; `--minor`/`--major` change the number): takes the next version (VERSION = the last release), commits it, pushes, tags `vX.Y.Z` and publishes release-X.Y.Z.zip with the token git already has. The notes are made from the commit messages and the new NOTES.md blocks since the last release, so write them for players. The zip holds only what a player needs (list in the script). Every update of the release gets a new version number.
