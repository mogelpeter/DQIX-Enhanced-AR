# Working faster on the mods

One rule: **do the cheapest check that can catch the mistake, and never repeat a check whose inputs did not change.**
`mods\system\dev.bat` (or `python mods\system\tools\dev.py`) does all of it.

## The loop

1. Edit in this repo (`mods\...`). The repo is the source of truth; the game folder only receives copies.
2. `dev test fast` (about 1.5 min, 5 s when nothing changed). It deploys the changed files to the game folder first.
3. Pick the extra check from the table below for what you touched.
4. `dev test full` before you push (about 8 min, only the tests whose inputs changed are run).
5. Add a line to `NOTES.md`, commit, push. `dev deploy` already put the working files in the game folder.

## Which check for which change

| You changed | Run | Why this and not more |
|---|---|---|
| `CheatMenu.cs` (look, texts, tooltips) | `dev shot "<page>"`, then `dev test menu-smoke` | pictures in 5 s; the smoke test builds every card (all tooltips) on 4 pages and fails if `menu-error.log` appears |
| `catalog.py`, `cheats\`, `code\`, `database\` | `dev test static` then `dev test all-quick` | static reads every catalog line in 0.1 s; all-quick sends 12 cheats to a headless game |
| `mod_cheats.c`, `ar_engine.h` | `dev test live session all-single all-session` after a build | the only code that runs inside the game and inside friends' sessions |
| a code mod (patch) | `dev scratch` (add `--rounds` for the x4/x8/Always Fail alternatives) | builds in a scratch copy in about a minute, your `game\` is not touched |
| only tests / docs | `dev test static` | nothing in the game changed |

## Why it is fast

- **Tiers**: `fast` = static + short live + short session + 12-cheat run + menu smoke. `full` adds the long runs and the two menu tests.
- **Cache**: `mods\system\bin\test-cache.json` keeps a hash of every input (sources, catalog, cheats, `dqix.exe`, `dqixcore.dll`). A test that passed with the same hash is skipped; failures always rerun. `--force` ignores it.
- **Parallel**: tests that only need a headless game run together on their own ports and work folders (`--jobs`, default 3).
- **Alone at the end**: the menu tests. The menu attaches to *any* running `dqix.exe`, so it must never overlap a game test (or your own game: `dev` refuses to run while `dqix.exe` runs).
- **Sized by message length**: cheat messages travel 16 bits per frame, so `test_all.py` computes its frame budget from the data instead of a fixed guess.
- **Scratch builds** instead of touching `game\`: all 50 code mods build in about a minute.
- **Static guards** catch what the compiler would catch later: C# 5 only (`$"..."`, `?.`, `nameof`), unreadable catalog lines, a blocked cheat switched on.

## Habits that save time

- Never start the menu while a test game runs (extra messages, false failures).
- Test addresses must be unused RAM (`0x02340000` region is zero); text areas change under you.
- In a session only `sync ... same` lines count; each PC dumps its own DS.
- PowerShell `>` writes UTF-16: set `PYTHONIOENCODING=utf-8` and use `Out-File -Encoding utf8` (dev.py already does).
- Long runs go in the background; poll the result file, do not sleep in the foreground.
- Do not edit big files with here-docs through a shell: use the editor tool or a small script file.

## Moving to another PC

1. Install Python 3.8+ (or just build the game once: the MSYS2 tools bring their own).
2. Build the game once with the project's `BUILD.bat` (needs your own ROM in `rom\`).
3. Run `Install mods.bat` from this repo (it asks for the folder, or takes it as an argument).
4. `mods\system\dev.bat doctor` lists anything still missing and how to fix it.
5. Working from the repo on that PC: `mods\system\dev-root.txt` (one line, the game folder) or `set DQIX_ROOT=...`.

Nothing in the tools is tied to one PC: the game folder is found, the temp folder is the system's, MSYS2 is looked up
from `mods\system\msys2-root.txt`, the fonts travel in `mods\system\fonts`.
