# Change notes

Newest first. One block per working session: what changed, why, how it was checked.

## 2026-11-13 (12)  Save editor in German/French/Spanish/Italian
- Editor texts are translated in the browser: `rom-glossary.tsv` (made by `rom_text.py` from every message table the ROM has in five languages, plus the 345 monster names: vocations, accolades, records, monsters, menu words...) and `mods/lang/editor.tsv` (the editor's own labels, buttons, hints, place and building words; hand-written) become one dictionary that a small script injected into the served page applies to text and placeholder/title attributes (also to text that appears later). Keys ignore case/punctuation except a trailing colon. Item names are swapped in the bundle as before. Tab jumping uses the tab index now (the tab labels are translated).
- Not translated: places that are not in the ROM text (most town names), "canvased guests: (n/30)"-style composed labels, user data (names, messages).
- Host self-test also checks that the German page carries the dictionary.

## 2026-11-13 (11)  Translations: German, French, Spanish, Italian, in the game's own words
- `mods/tools/rom_text.py` reads the ROM's text: NitroFS, GPC2 archives, DS compression and the name/string tables (formats from the DQIX wiki, own implementation; the ROM is only read). `catalog.py` runs it and writes `mods/lang/rom-itemname-<lang>.tsv` (git-ignored, ROM text) for all five ROM languages.
- Menu: language box in the header (default = Windows language, saved in `mods/menu-lang.txt`). `mods/lang/ui.tsv` has the German/French/Spanish/Italian text for every menu text and every cheat name/note (406). Game terms are the ROM's: Talentpunkte / points de compétence / puntos de destreza / punti abilità, Schatzkarte / carte au trésor, Grotte / antre / gruta / antro, Alchemirakel / alchimiracle / alquimilagro / alchemiracolo, Todesstoß / coup de grâce, Gästebuch, vocation names (str_dam/str_sli), Garderobe / armoire / armario / Guardaroba... `tools/lang_keys.py` lists texts without a full translation.
- Save editor: its item names are swapped for the ROM's names in the chosen language when the page is served (only where the ROM's English name for that item id matches the editor's name). The host self-test checks it (German copper sword).
- Not translated: the cheat codes' key names ([A], START...), error texts of the build scripts (batch/py), the editor's own UI (party, items... tab names, buttons) which is not part of the ROM. "Zoom" is kept: the ROM text tables don't hold the spell's name in an aligned table.
- Static guard: the regex `$"` also hits a regex ending; the cache path regex uses `\A...\z`.

## 2026-11-13 (10)  One button per editor page, cache path hardening
- Save editor / Treasure maps pages have no subtabs now: one button opens the editor (treasure maps: also the Grotto Searcher website).
- Security review finding fixed: editor cache paths are limited to `[A-Za-z0-9_-./]`, resolved and confined to `modsin\editor-cache` (a `C:/...` path could have left the folder). The host self-test sends five attack paths and expects 404. menu-smoke PASS.

## 2026-11-13 (9)  Save editor + treasure map tabs
- Research: the working save editor is the DQIX project's browser editor (github.com/dqix/editor, JS, Sep 2026; parties, items, inn, records, DLC, misc, hex, grottos). It has **no license**, so its code is **not copied into this repo**: the menu downloads the built site from dqix.github.io on first use into `modsin\editor-cache` (git-ignored) and serves it on `127.0.0.1` (`EditorHost` in `CheatMenu.cs`). Its grotto editing is unfinished upstream (adding/removing, map preview). Treasure map search = their Grotto-Searcher (CC BY-NC-SA), opened as a website.
- New menu pages **Save editor** (subtabs Party, Items, Inn, Records, DLC, Misc, Hex) and **Treasure maps** (Your maps, Find a map). A subtab opens the editor in the browser with `game\dqix.sav` loaded and the right tab selected (a small script is injected when serving the page).
- Export in the editor writes back to `dqix.sav` through the menu: refused while `dqix.exe` runs, wrong size refused, old save copied to `mods\save-backups` first, requests need a per-run token.
- `dqix-cheat-menu.exe --editor-selftest <file>` tests the host; part of `menu-smoke`, which also draws both new pages. Checked in headless Chrome: real save loads and the `items` tab opens. Not tested: the export click in a real browser, only the HTTP side.

## 2026-11-13 (8)  System page removed
- `catalog.py` skips the System folder (anti-piracy, WFC, backlight: all blocked anyway) and the page is gone; "not available" went from 8 to 4. static + menu-smoke PASS.

## 2026-11-13 (7)  Multiplayer tags, hover without repeats
- Every card carries ONE PLAYER (live: one player is enough, sent to all PCs), ALL PLAYERS (built in: same set on every PC) or OWN PC (launch options). Hover now only says how to use it + the multiplayer rule; note, status, rebuild warning and code-line count are on the card, not repeated. menu-smoke PASS.

## 2026-11-13 (6)  Plainer menu
- Dropped the decorative bits: sparkle/star/play/warning/lock glyphs, outlined pill chips (now plain small tags), gradient button, round switch knob, boxed nav selection (now a red edge bar), status pill box. Corners 2 px, switch smaller. `CheatMenu.cs` only; menu-smoke PASS.

## 2026-11-13 (5)  Cleanup
- Removed the unused standalone `test_engine.c` and `__pycache__` folders.

## 2026-11-13 (4)  Status line removed, one-click installer
- Header status line (counts, built-in set) hidden. `Install mods.bat` now finds the DQIX Enhanced folder itself (folder picker only as fallback), copies the mods, makes the desktop shortcut and offers to start the menu. Checked: auto-find, explicit path, menu-smoke PASS.

## 2026-11-13 (3)  Menu restyle: dark glass + red accent
- Menu colours moved from black/neon green to neutral dark grey with a red accent (switches, primary button, selection, heading underline); UI font is Segoe UI (JetBrains Mono stays for the log). `CheatMenu.cs` only.
- Checked: `dev test fast` 5/5 (33 s), `dev shot`; no compile errors found (menu compiles, static guards pass).

## 2026-11-13 (2)  Hover info, rebuild warnings, dev tooling, repo
- **Hover info** on every cheat card (switches, "Once" buttons, choices and each option of a choice, locked cheats):
  what it does, how to use it (switch / hold keys / Once), whether it works with friends, tried-out or untested, how many
  code lines. Black/green tooltip in JetBrains Mono. (`CheatMenu.cs`: `MakeTip`, `TipOf`, `Hover`)
- **Rebuild warning** on every cheat that is built into the game ("BUILT IN"): a visible amber line
  "Works only after a full rebuild and a restart of the game" and the same in the tooltip. Choices that are built in
  carry it too. Cheats for the next start say "Works after the next start of the game from this menu."
  A built-in cheat that is switched on and already built shows a green "Built into your game" line instead;
  switched on but not built: the tooltip says press Rebuild, then restart.
- **`mods\tools\dev.py` + `mods\dev.bat`**: `doctor`, `deploy [--pull]`, `menu`, `shot`, `test fast|full|NAME`, `scratch [--rounds]`.
  Tiered, cached, parallel tests (see `WORKFLOW.md`).
- `test_session.py` now prints `RESULT:` and sets the exit code; `test_all.py` takes `TEST_LIMIT` and empty frame/port arguments.
- **`Install mods.bat`**: puts `mods\` into any DQIX Enhanced folder (asks, or takes the folder as argument), keeps the user's own files.
- Checked: `dev test fast` 5/5 (about 1 min on a warm cache, 5 s unchanged); full tier: static, live, session, all-single, all-session, menu-smoke, menu-inside, menu-outside all PASS.
- Found while testing: `tasklist` output is not UTF-8 on every PC (German console) and crashed `dev.py` when run hidden: all subprocess output is now decoded with `errors=replace`.

## 2026-11-13 (1)  Matrix look, fixed tests, all-cheats test
- Menu: black + neon green, JetBrains Mono (`mods\fonts`, OFL), about 20 % smaller window and type.
- `test_live.py`: test address moved to unused RAM (the "before SELECT" check failed because of text data there).
- `test_menu.py`: own state file through `DQIX_MENU_STATE`, no dependence on what the user switched on.
- New `test_all.py`: all 170 live cheats alone and in a two-player session, plain-write cheats checked in RAM.
- All 50 code mods built together in a scratch copy plus six rounds for the clashing alternatives: all start, all stay in sync.
