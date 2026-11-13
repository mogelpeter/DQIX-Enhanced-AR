# Change notes

Newest first. One block per working session: what changed, why, how it was checked.

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
