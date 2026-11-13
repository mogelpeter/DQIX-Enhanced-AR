# DQIX Enhanced AR

A cheat menu and mods for [DQIX Enhanced](https://github.com/sackchief/dqix-enhanced) (Dragon Quest IX on PC), in the style of an R4 / Action Replay cheat menu: black and neon green, JetBrains Mono, a hover info on every cheat.

- **170 live cheats and 50 built-in code mods**, all checked against your own ROM before they can run, so they cannot crash the game.
- **A "Cheats" tab inside the game's own menu bar**: one click on *Cheats enabled...* restarts the game into the cheat menu. The tab is put back automatically after the game updates itself.
- **Works alone and in sessions with friends** (cheats travel with the buttons, so every PC stays in sync).
- **Save editor** and **Treasure maps** tabs: opens the DQIX project's browser editor with your save already loaded (downloaded on first use, needs the internet once; not part of this repo).
- **Five languages**: English, Deutsch, Francais, Espanol, Italiano (box at the top right of the cheat menu). Game words come from your own ROM's texts, also the item names in the save editor.
- **Your save is protected**: every time you press Play, a copy of your save goes to `mods\system\save-backups` (the last 30 are kept).

The ROM and the game itself are never part of this repo.

---

## Contents

1. [Quick install (if you already have DQIX Enhanced)](#quick-install)
2. [Step by step for complete beginners](#step-by-step-for-complete-beginners)
3. [Using the cheats](#using-the-cheats)
4. [How the Cheats tab works, and why it survives updates](#how-the-cheats-tab-works)
5. [Playing with friends](#playing-with-friends)
6. [Why the cheats can't break your game](#why-the-cheats-cant-break-your-game)
7. [Settings](#settings)
8. [Troubleshooting](#troubleshooting)
9. [Uninstall](#uninstall)
10. [For development](#for-development)

---

## Quick install

1. Build DQIX Enhanced once (its installer, or its `BUILD.bat`, with your own ROM).
2. Double-click **`Install mods.bat`** from this repo. It finds your DQIX Enhanced folder itself (it asks only if it can't), copies the mods in, puts a shortcut on your desktop, and builds the **Cheats** tab into the game (a few minutes the first time).
3. Start the game with `game\dqix.exe` and open **Cheats > Cheats enabled...** in the menu bar, or start the desktop shortcut **"Dragon Quest IX (mods)"**, which opens the cheat menu first.

Trouble? `mods\system\dev.bat doctor` says what is missing and how to fix it.

---

## Step by step for complete beginners

This guide assumes nothing. You need a Windows 10 or 11 PC (64-bit), about 4 GB of free space and an internet connection. Everything below is done by double-clicking files; you never have to type anything.

> **About the ROM.** The game is *not* included, and neither this project nor DQIX Enhanced can give it to you. You need a ROM file (ending in `.nds`) that you made yourself from **your own Dragon Quest IX cartridge**. The USA and European versions work. Your ROM stays on your PC; nothing is uploaded.

### Step 1: Get DQIX Enhanced (the game itself)

1. Open <https://github.com/sackchief/dqix-enhanced> in your browser.
2. Click the green **Code** button, then **Download ZIP**.
3. Open your **Downloads** folder, right-click the ZIP file and choose **Extract All...**, then **Extract**. Move the extracted folder to your **Documents** folder and rename it to something short, for example `DQIX-Enhanced`. (Avoid putting it on the Desktop or in OneDrive: syncing can disturb the build.)

### Step 2: Build the game from your ROM

1. Open the folder and double-click **`Install Dragon Quest IX.bat`**.
2. Windows may show a blue box **"Windows protected your PC"**. This is normal for files from the internet. Click **More info**, then **Run anyway**.
3. A window walks you through it: it asks for your ROM file, where to put the game (Documents is fine) and whether you want shortcuts. Just follow it.
4. The first time it installs free build tools (called MSYS2) and builds the game. **This takes 10 to 20 minutes.** Black windows with scrolling text are normal: leave them alone until they close on their own.
5. At the end press **Play now** to check that the game starts. Close the game again (Esc, or the X of the window).

If it says it can't find your ROM, copy the `.nds` file (or a `.zip` that has it inside) into the **`rom`** folder inside the DQIX Enhanced folder and double-click **`BUILD.bat`** instead.

### Step 3: Get this cheat menu

1. Open <https://github.com/mogelpeter/DQIX-Enhanced-AR>.
2. Click the green **Code** button, then **Download ZIP**.
3. Right-click the ZIP in Downloads, **Extract All...**, **Extract**. You can leave the extracted folder where it is.

### Step 4: Install the mods

1. In the extracted folder double-click **`Install mods.bat`**.
2. Again, if Windows says **"Windows protected your PC"**: **More info**, then **Run anyway**.
3. It looks for your DQIX Enhanced folder on its own. If it can't find it, a window opens: pick the folder from Step 1 (the one with `BUILD.bat` in it).
4. Wait. It copies the files, makes a desktop shortcut and builds the **Cheats** tab into your game. **A few minutes the first time.** Do not close the window; it says *"The Cheats tab is in the game."* when it's done.
5. It asks *"Start the menu now?"*. Type `Y` and press Enter if you like, or `N`.

Make sure the game is **closed** while installing. If it is still running the installer tells you so; close the game and run **`Install mods.bat`** again.

### Step 5: Play with cheats

There are two ways, both do the same:

- **From the game:** start the game (`game\dqix.exe`, or the usual shortcut). In the menu bar at the top of the window open **Cheats**, then click **Cheats enabled...**. Confirm. The game closes and the cheat menu opens.
- **From the desktop:** double-click **"Dragon Quest IX (mods)"**. The cheat menu opens right away.

In the cheat menu tick the cheats you want (see below), then press **Play**. The game starts with them.

The first time you tick a cheat marked *BUILT IN*, Play needs a few minutes to rebuild the game. That is normal.

### If something goes wrong

- A black window shows an error: take a photo or copy the text, and see [Troubleshooting](#troubleshooting).
- The game does something odd: press **F10** in the game. It saves a bug report and can open GitHub for you.
- Your save: don't worry, copies are in `mods\system\save-backups`.

---

## Using the cheats

The cheat menu has pages on the left (Speed & comfort, Experience & gold, Party, Battle, Items, Custom...), a **search box**, and **Switched on**, which lists everything that is on right now. Press **Play** to start the game; you can keep the menu open while you play and switch cheats on the fly. Hover a cheat to read what it does.

Each cheat is one of these:

| Kind | What it does |
|---|---|
| **Switch** | On = it works from now on, every frame, like a ticked code on an R4. |
| **Once / Do it** | Carries the code out one time, now (99 of every shield, all Zoom places...). |
| **Choice** | Experience x2 / x4 / ... / x128, movement speed, a vocation: only one can be on. |
| **With buttons** (SELECT, L+R...) | Works like on a DS: switch it on, then hold those buttons in the game. *Once* does it right away without the buttons. |

The labels on the cards:

| Label | Meaning |
|---|---|
| `TRIED OUT` | Tried in this version of the game. |
| `UNTESTED` | From the R4 list and checked as far as a program can, but not tried here. **Save first.** |
| `BUILT IN` | Changes how the game works, so it is built into the game: Play rebuilds the changed parts (half a minute to a few minutes). |
| `NEXT START` | Takes effect the next time the game starts from the menu ("Always fast forward", "Instant loading"). |
| `ONE PLAYER` / `ALL PLAYERS` / `OWN PC` | How it behaves in a session with friends. |

**Everything off** switches all of it off. You can also add your own cheats: put a text file in `mods\system\cheats` (see `mods\README.txt`, section "Make your own").

---

## How the Cheats tab works

The game's menu bar (Game, Graphics, Screen, View, Wireless, Modern, Mods, **Cheats**, Help) gets one more entry. **Cheats > Cheats enabled...** asks, saves, closes the game and opens the cheat menu (`mods\Play with mods.bat`). Its Play button builds the cheats in if needed and starts the game again. It is refused while a session with friends is running.

### Why it survives updates of the game

The tab is not a copy of the game's files: it is a handful of small, clearly marked changes (`>>> mods ... <<< mods`) that `mods\system\tools\apply_runtime_mod.py` puts into the game's source before it is built. An update of the game replaces those files, so:

- **Update from inside the game (Help > Check for updates):** the updater also runs `Play with mods.bat apply` before it rebuilds, so the new game comes out with the tab, the cheats and your switches again. Nothing to do.
- **Update by hand (a new download):** run **`Install mods.bat`** or **`Play with mods.bat`** once; every change is put back and the game is rebuilt.
- **A place the new version wrote differently:** it is skipped with a message and the rest still works. The cheat menu through `Play with mods.bat` always works.
- The update never deletes the `mods` folder, so what you switched on stays (`mods\system\menu-state.txt`).

To take everything out of the game again set `sync_cheats = no` in `mods\settings.txt` and run `Play with mods.bat` once.

---

## Playing with friends

Live cheats work in sessions as long as every player's game has these mods built in.

In a session every PC runs every player's DS, and they must all compute exactly the same. So a cheat can't just be written into your PC's memory. It travels with your button presses instead: your game sends it to the others like a button, and every PC carries it out for your DS in the same frame.

1. Give every player this mods folder; each installs it (or presses Play once).
2. Host and join as usual (Wireless > Play with friends).
3. Use the cheats as when alone. They only change your own DS (hero, gold, bag), on every PC at once. Friends don't need the same cheats on.

Notes:

- **Built-in mods** (faster text, experience x2...) change how the game computes. Every player needs *exactly the same ones*, or the session goes OUT OF SYNC. Simplest: switch them off before playing with friends. The menu shows a short name for what is built in ("built-in set 3F2A"): it must match for everyone.
- **Instant loading** only works alone; in a session the game keeps the cartridge's real timing by itself.
- If one player's game doesn't have the mods in it, the first cheat puts the session out of sync (the title bar says so). Without cheats such a session plays normally.

---

## Why the cheats can't break your game

An Action Replay code is written for a real DS, where it may change anything at any moment. Here the game's program is compiled PC code. So before the menu shows a code, `mods\system\tools\catalog.py` runs it against a copy of **your own ROM's** program and sorts it:

- **Live cheat:** it only changes data. The game carries it out itself at one fixed point of each frame. A code can only write the DS's main memory, and a code that would loop forever is cut off.
- **Built-in mod:** it changes instructions. Every instruction was found in your ROM where the code says it is; exactly those words and nothing else are written into the build.
- **Not available:** it can't work here or can't be checked (adds its own routine, jumps out of the program, writes into the program, mixes program and data, DS hardware, doesn't fit your ROM, anti-piracy and Wi-Fi codes). It is listed with the reason and can't be switched on.

The cheat menu is a program of its own: whatever happens in it, the game keeps running. What a program can't check is what a data cheat does to your *save* ("Max everything" codes can make a save odd): that is what `UNTESTED` warns about and what the save backups are for.

The cheat list comes from the community's R4 database (DeadSkullzJr's NDS(i) Cheat Databases): 216 codes for the European version, 271 for the USA one, plus hand-made ones. Both ROM versions work; the menu takes the list for your ROM's game code (YDQP or YDQE).

---

## Settings

`mods\settings.txt` (yes / no):

| Setting | Default | Meaning |
|---|---|---|
| `cheat_window` | `yes` | Open the cheat menu when starting `Play with mods.bat`. `no`: the game starts at once with the code mods that are switched on. |
| `sync_cheats` | `yes` | Build the part that makes cheats work with friends (and the **Cheats** tab) into the game. `no`: leave it all out; cheats then only work alone and are written from outside. |

---

## Troubleshooting

| Problem | What to do |
|---|---|
| *"Windows protected your PC"* | Click **More info**, then **Run anyway**. The files are plain batch scripts you can open in Notepad. |
| The installer can't find the game folder | Choose the folder with `BUILD.bat` in the window that opens. It must be built first (`game\dqix.exe` exists). |
| *"The game is still running"* | Close the game (and the cheat menu), run `Install mods.bat` again. |
| The **Cheats** tab is missing in the game | The game was built without it (for example after a hand-made update). Run `Install mods.bat` or `Play with mods.bat` once, wait for the build. |
| *"cmp: command not found"* at the end of a build | Harmless. To silence it: open the MSYS2 UCRT64 terminal and run `pacman -S diffutils`. |
| The build fails | Read the last lines of the black window; run `mods\system\dev.bat doctor`; check that you have ~4 GB free and the internet on. |
| The cheat menu doesn't open | It needs the C# compiler that comes with Windows 10/11 (.NET Framework 4). Then switch cheats on in `mods\system\cheats` by hand (see `mods\README.txt`). |
| A friend's session says OUT OF SYNC | Everyone needs the same built-in mods (or none), and the same version of these mods. See [Playing with friends](#playing-with-friends). |
| Something else | Press **F10** in the game: it saves a bug report and can open GitHub for you. |

---

## Uninstall

1. Set `sync_cheats = no` in `mods\settings.txt` and run `mods\Play with mods.bat apply` (double-click `Play with mods.bat`, then close the menu): this takes the Cheats tab and the cheats' part out of the game's source and rebuilds it. Switch all code mods off first (**Everything off**) so the build is clean.
2. Delete the `mods` folder and the desktop shortcut.

Your save (`game\dqix.sav`) is never touched.

---

## For development

See [WORKFLOW.md](WORKFLOW.md) (fast loop, which test for which change, moving to another PC) and [NOTES.md](NOTES.md) (change notes). `mods\README.txt` is the user manual of the menu.

Layout:

```
Install mods.bat            one-click installer (copies mods\, shortcut, builds the Cheats tab in)
mods\Play with mods.bat     start here: cheat menu, "apply" = put the mods into the game and build
mods\settings.txt           cheat_window, sync_cheats
mods\system\src\            CheatMenu.cs (WPF menu), mod_cheats.c, ar_engine.h, mod_menu.c, ...
mods\system\tools\          catalog.py, apply_runtime_mod.py, apply_code_mods.py, build_stamp.py, dev.py
mods\system\tests\          headless regression tests (run with dev.py test ...)
mods\system\cheats\         the cheat lists (R4 database + hand-made, yours too)
```

The marked places in the game's source are listed in `SITES` in `apply_runtime_mod.py`; `mods\system\tests\test_runtime_patch.py` checks that they go in, out and in again identically.
