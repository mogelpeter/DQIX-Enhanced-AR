# DQIX Enhanced AR

Cheat menu and mods for [DQIX Enhanced](https://github.com/sackchief/dqix-enhanced) (Dragon Quest IX on PC),
in the style of an R4 cheat menu: black and neon green, JetBrains Mono, a hover info on every cheat.

- 170 live cheats, 50 built-in code mods, all checked against your own ROM before they can run, so they cannot crash the game.
- Works alone and in sessions with friends (cheats travel with the buttons).
- **Save editor** and **Treasure maps** tabs: open the DQIX project's browser editor with your save already loaded (downloaded on first use, needs the internet once; not part of this repo).
- **Languages**: English, Deutsch, Français, Español, Italiano (box at the top right of the menu). Game words come from your own ROM's texts, also the item names in the save editor.
- Cheats that change the game's program say so on their card: *works only after a full rebuild and a restart of the game*.

## Install

1. Build DQIX Enhanced once with its `BUILD.bat` (your own ROM in `rom\`).
2. Double-click **`Install mods.bat`**. It finds your folder itself, installs, and puts a desktop shortcut on your desktop.
3. Start the shortcut "Dragon Quest IX (mods)".
4. Trouble? `mods\system\dev.bat doctor` says what is missing and how to fix it.

The ROM and the game are never part of this repo.

## For development

See [WORKFLOW.md](WORKFLOW.md) (fast loop, which test for which change, moving to another PC) and [NOTES.md](NOTES.md) (change notes).
`mods\README.txt` is the user manual of the menu.
