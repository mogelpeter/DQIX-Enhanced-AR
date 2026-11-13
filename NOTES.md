# Change notes

Newest first. One block per working session: what changed, why, how it was checked.

## 2026-11-13 (22)  RE helper, per-cheat effect test 
- Research: no public DQIX RAM map or symbols exist (only AR address lists); Ghidra/NTRGhidra/DeSmuME not needed because the recompiled C already carries the ROM's function names. Playbook added to `WORKFLOW.md`.
- `mods/system/tools/dqre.py`: `func`, `names`, `ar`, `ram`, `diff` over `dispatch_table.c` and `DQIX_RAMDUMP` files. (Not named `re.py`: it shadows Python's `re` and broke dev.py.)
- `mods/system/tests/test_effects.py <root> <work> untested <first> <count>`: fires each live cheat alone, compares RAM with a Python port of the AR engine. All 149 live cheats (UNTESTED + tested): no failure; about 46 PASS with the RAM effect confirmed, the rest NOCHANGE (condition not met at the boot menu, value already set, switch address 02F5A5xx, or bytes the game rewrites itself, e.g. an audio buffer). NOCHANGE is not proof. `test_vanish` PASS. `test_noflee` SKIPs on the real build (built-in "Monsters don't chase" prevents the fight); needs a scratch build without it. Full tier (8 tests) PASS. Labels still unchanged; code mods: `dev scratch --rounds` running.

## 2026-11-13 (21)  Monsters can't flee: fixed at the source
- **Cause found** by watching a headless fight (Guarantomb, `DQIX_MOD_FORCE=3` = every roamer a metal slime, frame dumps + a scratch build that logged function entries and the battle's command list): the monster's turn is built by ov000 `0215767c`, which asks `func_0208a92c` (main, USA `0208a91c`) for the action number; **225 and 917 are the two actions named "Flee"** (action table: 618 records of 60 bytes, id in the low 12 bits of the word at +4, name pointer at +0; found by dumping RAM at the battle). The AI picks them at random from the monster's list. The old code mod (ov024 `021F418C`, the "who can I aim at" query 112) was never on this path: the run with it was frame-identical to the run without it.
- **Fix**: `src/noflee.c` wraps `0208a91c` (wrap.txt line, `WRAP_LINES`): while the cheat is on, a Flee answer is thrown away and the AI asked again (up to 200 times). The cheat is now a *live* cheat (`02F5A5A8` switch in `mod_cheats.c`, like lowexp/vanish), so it works in sessions too (same on every PC) and the code mod in ov024 is gone. 9000 frames of fighting metal slimes: no Flee command any more (before: flees at about frame 4900 and 6000).
- `build_stamp.py` now also hashes `mod_data.c`, `lowexp.c`, `vanish.c`, `noflee.c` and the wrap.txt block (a wrap change did not trigger a rebuild). `test_all.py`: switches `02F5A5A0..AF` are not memory (vanish/noflee made the "plain writes in RAM" check fail). New `tests/test_noflee.py` (3 min, needs a fight: SKIP if none is reached) PASS on the real build (4 re-asks); `test fast`, `all-single`, `all-session` PASS.

## 2026-11-13 (20)  Title text moved into the window title
- `CheatMenu.cs`: the "Dragon Quest IX / cheats" heading inside the window is gone; the window title is now "Dragon Quest IX  /  cheats" (cheats translated with the language box). Checked: `dev menu`, `test static menu-smoke`, shot.

## 2026-11-13 (19)  Dark title bar, no "Not available" page, no TRIED OUT chip, shortcut icon
- `CheatMenu.cs`: dark title bar (DwmSetWindowAttribute 20/19, caption colours 35/36 on Windows 11); the "Not available" nav page, its count in the sub line and the "Not available here" list are gone (blocked codes stay hidden and off); only UNTESTED chips are shown (TRIED OUT removed).
- `Make a desktop shortcut.bat`: the icon path had `..` in it and was ignored; now resolved with GetFullPath, `build\icon\dqix.ico` first, else the exe's own icon.
- Checked: `dev menu` compiles, `dev shot` (Party page: no Not available, no TRIED OUT). The title bar colour can't be seen in the shots; look at it once.

## 2026-11-13 (18)  Cheats tab in the game's own menu bar, installer puts it in
- **Menu bar > Cheats > "Cheats enabled..."** (and "What is this?"): asks, saves, closes the game and opens the cheat menu (`mods\Play with mods.bat`, new window); its Play button builds and starts the game with the cheats. Refused while a session runs. Code: `mods/system/src/mod_menu.c` (copied to `runtime\`), three marked places added to `apply_runtime_mod.py`: `menu_win32.c` (menu items 360/361, before Help), `frontend_sdl.c` (`case 360/361` before `MI_UPDATE`), `update.c`.
- **Survives updates of the game**: an update replaces `runtime\`, but the old game's `updatepply.bat` now also runs `mods\Play with mods.bat apply` before `BUILD.bat` (site in `update.c`, kept alive transitively: each build has it). Hand-made updates: run Install/Play once, `apply` puts every place back. A place that no longer matches an update is skipped with a message, the rest still works.
- `Install mods.bat` now runs `Play with mods.bat apply` after copying (builds the game with the tab; says if the game is running). `build_stamp.py` hashes every marked place plus `mod_menu.c` (one rebuild after this change).
- Checked: new `tests/test_runtime_patch.py` (on / off / on again, idempotent; part of `test static`) PASS; scratch copy built with the tab (string and `mod_menu.o` in the exe), Install mods.bat run end to end against the scratch copy. The tab was not clicked in a running game yet (your `game\` was not rebuilt: run Install mods.bat or Play with mods.bat).

## 2026-11-13 (17)  Custom page, metal slimes tried out, flee investigation
- Page "My cheats" is **Custom** now (catalog, `# also:` lines, README, ui.tsv: Eigene / Perso / Propios / Personali). Custom keeps listing our own cheats while each one also sits on its normal page (they already did: Battle, World, Experience & gold); "Battle any monster you want" is in Custom too (`also` on its entries). **Metal slimes only** is "tried out" (confirmed working by the user); "Battle any monster" stays untested.
- **Monsters can't flee: NOT fixed yet.** Report: works for a few rounds, then metal slimes still flee. Findings (ov024 = base 0x021DE8C0... file `build/extract/arm9_overlays/ov024.bin`, base 35490368): the table at 0x021FF790 is 161 entries of 8 bytes (fn, 0) indexed by the action's *target type*, not the action id; entry 112 = 0x021F418C (the patched "Flee" query) is reached only through the dispatcher at 0x021F66CC, which arm9 0x0208A340 calls to fill a per-monster "usable action" bit mask. Message `actmsg` 45 = " flees." and 138 = " flees...but the enemy blocks the way" (the failed variant), `strbtl` 1/3 are the field versions. So choosing Flee through the usable mask is blocked, and the remaining flee must come from another path (a script/AI rule or an effect that does not ask the mask). Not found yet: the executor of action 45, and which AI data (`battleaction.dat`, `defaultaction.bact`) names it. `actdt_a/b.gp2` use codec 7, which `rom_text.gpc2` can't read yet.
- Checked: `dev test static menu-smoke` PASS, screenshot of the Custom page.
- Flee, second round (no fix, ways that did not work): no code in ov024 or arm9 calls the flee query except through the dispatcher; the immediate 45 (flee action id) shows no useful hits; the only symbols (`config/usa/arm9/symbols.txt`, USA arm9 only) have nothing about battles; `defaultaction.bact` / `battleaction.dat` are AI bytecode (ops like `01000101`, `2f000315`) with no parser yet; `actdt_a/b.gp2` need a codec/entry-table variant `rom_text.gpc2` doesn't know. The next real step is a runtime look: a game built with `-DRECOMP_TRACE` has `DQIX_TRACEFN=addr,count` (call trace when a function is entered) and `DQIX_WATCH=addr`; the released `dqix.exe` has neither. With it: reach a metal slime fight (`DQIX_MOD_FORCE`/`DQIX_MOD_METAL`), watch which function removes the monster when it flees.

## 2026-11-13 (16)  One cheats folder, Play = Rebuild, boxed tags, editor layout in other languages
- **One folder**: `mods/cheats`, `mods/system/code` and `mods/system/database` are all `mods/system/cheats` now. `apply_code_mods.hand_files()` tells live cheats from code mods by their `patch` lines; the R4 lists are `r4-<game>.txt` (skipped as hand-made files). Ids stay (`file:cheats/..`, `file:code/..`), so saved switches and `built.txt` keep working. `dev.py deploy` and `Install mods.bat` move an old layout over (own files kept) and delete the old folders. `mods\` shows only Play with mods.bat, README.txt, settings.txt, system\.
- **Play is the rebuild button**: the banner and "Rebuild now" are gone. While the switched-on built-in cheats differ from what the game has (`Pending()`: set compare, so switching a cheat back off cancels the rebuild), Play reads "Rebuild and play" (hover: how many to put in / take out) and does both (`RunApply(true)`).
- **Cards**: ONE PLAYER / ALL PLAYERS / OWN PC / BUILT IN / NEXT START / TRIED OUT / UNTESTED / key chips are small outlined boxes (ONE PLAYER teal, ALL PLAYERS purple, OWN PC grey). Multiplayer lines in every hover are boxed in the same colour. The yellow "works only after a rebuild" lines are removed (card and hover).
- **Save editor in other languages**: lookup ignores a missing/extra trailing colon (`weapons` and `weapons:`, `equipment:` from the ROM glossary); country codes (ARM, KAM...) are no longer "translated" (ARM became "Sch"); new texts in `editor.tsv` (unallocated skill points, unlock all dlc, canvased guests, everyday/important items in full); the Items tab is the game's own "Gepäck". `FixCss` (injected only when translated): card headings wrap instead of overlapping, misc/dlc cards grow, record tabs wrap, profile labels get room.
- Checked: `dev test static menu-smoke` PASS; menu screenshots (Battle page, "Rebuild and play" with a pending built-in cheat); the editor rendered in headless Chrome through a copy of the host's injection (German party/items/inn/records/dlc/misc). Not run: the live game tests (nothing in the game's code changed). The real host swaps the item names; that harness does not, so they stay English there.

## 2026-11-13 (15)  Claude Code project hooks
- `.claude/hooks/dqix_hook.py` + `.claude/settings.json`: session status, deny edits in the game folder that have a repo twin, deny killing dqix.exe, automatic `dev test static` after edits under `mods/`, NOTES.md reminder at turn end. Checked by feeding each event a sample payload.

## 2026-11-13 (14)  Cheats reworked, new native cheats, hover descriptions, English first
- Language: the menu always starts in English (the box remembers a changed choice).
- "Not available" is empty now: our own versions replace the three R4 codes that could not work (`# replaces: <name>` in a cheat/code file removes the database entry of that name) and the R4 "Lower Level Characters Get More Exp." is gone. `# also: <page>` shows a cheat on a second page ("My cheats" holds our own: lower-level experience, monsters don't chase you, monsters can't flee, vanish, metal slimes only).
- **Unlock All Jobs v1** (`code/unlock-all-jobs.txt`): the R4 code is for the USA ROM; in the EU ROM ov003 0x021560B0 calls the flag test at 0x0206DFC0 (USA 0x0206DFB0, so the BL word differs: EBFC5FC2 not EBFC5FBE) once per vocation to build the vocation list; the call becomes `mov r0, #1`. **Quick Save Never Return To Title** (`code/quick-save-stays-in-game.txt`): ov002 0x0216A1EC stores a 1 at base+0xCC2 when the save is done; state 2 (0x0216B194) reads it and goes to state 3, which ends at the title; the store becomes a nop. Both are untested in the running game (static analysis only) and say so.
- **Monsters can't flee** (`code/monsters-cant-flee.txt`): the monster AI asks per action "who can I aim at?" (table at 0x021FF790); no 112 is Flee (ov024 0x021F418C) and answers 0 = refused unless the party is much stronger. The first two instructions become `mov r0,#0 / bx lr`.
- **Vanish** (`cheats/vanish.txt` + `src/vanish.c` + a switch in `mod_cheats.c`): L+R+SELECT together flip it (once per press); while on, `wrap_enccheck` (ov017 0x02196430, the field's "did a monster touch you" check, called from 0x0218CE38) answers 0 without running. Switching the cheat off ends it. `tests/test_vanish.py` (part of `dev scratch`) checks the toggle headless: on at the first press with the cheat armed, off at the next, once per press, nothing before arming or after clearing.
- **Metal slimes only** and **Battle any monster you want** (`src/mod_data.c`, launch options `DQIX_MOD_METAL=1` / `DQIX_MOD_FORCE=n`): the game reads `encfld.bin`/`encbtl.bin` (zones and their roamers) from the cartridge when it enters the field (one pass in a headless run), so card.c lays a changed copy over those reads (a third site in `apply_runtime_mod.py`). Metal: in the 13 zones that have a metal monster (level -99 in `fld_mondata.bin`) every other roamer/companion number becomes that monster; force: all of them become monster n (288 ordinary monsters, from the ROM's `mon_list`). Counts checked against an independent Python walk (49 and 110 numbers changed). Launch options, "ALL PLAYERS" in a session. The old R4 "Battle Any Monsters You Want" (select in the monster list, hold L/R, a code cave in ov017) was not ported: this is a different, simpler way to get there.
- Hover: `mods/system/lang/about.tsv` (English + German; fr/es/it fall back to English) says exactly what each of the 155 cheats/choices does; the hover shows it first. The menu also uses the ROM glossary as a fallback for any English text (monster names...).
- Found while testing: `DQIX_INPUT` separates presses with `;` (a comma makes it one press); a headless run reaches the field with `700:DOWN:6;800:A:6;` then A every ~90 frames (title debug menu: Start is the second line).

## 2026-11-13 (13)  Tidy mods folder, town names
- `mods\` now shows only `Play with mods.bat`, `README.txt`, `settings.txt`, `cheats\` (your own cheat files) and `system\` (menu, cheat lists, translations, tools, tests, fonts, saved switches, save backups). Everything that was loose moved into `mods\system\`; scripts, menu, installer, tests and docs use the new paths (code mods are `system/code/...` in the catalog). `Install mods.bat` migrates an old layout (keeps menu-state, save backups, code flags, msys2-root) and no longer ships generated files. dev.py `SRC_MODS` is the mods dir; `live` for tools/tests is `mods\system`.
- Town and region names come from the ROM now (`data/map/mapname.gp2`, a tagged table; `rom_text.map_names`): Stornway = Stinsbruck / Ablithia / Pedranía / Stornland, Angel Falls = Engelsfälle / Chérubelle / ...; where the field region has an extra "Région de" the shorter town name wins. The editor's place labels use them; the cheats that mention Stornway use them too.
- Checked: `dev test fast` 5/5, `dev scratch` (all code mods built through the new put_in.sh paths) PASS, installer migration of an old layout.

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
