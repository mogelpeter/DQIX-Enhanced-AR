DQIX ENHANCED - MODS
====================

Cheats and gameplay mods for DQIX Enhanced (github.com/sackchief/dqix-enhanced)
in a menu like the cheat menu of an R4 card, that keep working when the game
updates itself.


INSIDE THE GAME
---------------
The installer also puts a "Cheats" tab into the game's own menu bar (next to Mods and Help).
Cheats > Cheats enabled... closes the game and opens the cheat menu; its Play button starts the
game again with your cheats. "Play with mods.bat" works as before.
When the game updates itself (Help > Check for updates) the tab is put back automatically; if you
ever update by hand (new download), run Install mods.bat or Play with mods.bat once more.


INSTALL
-------
Copy this "mods" folder into your DQIX Enhanced folder, next to BUILD.bat:

    DQIX Enhanced\
        BUILD.bat
        game\
        mods\          <- here

Build the game once the normal way first (if you haven't already).
Then start with "mods\Play with mods.bat" (the installer also puts a shortcut
to it on your desktop).

What is in the mods folder (only these three things are for you):

    Play with mods.bat    start here
    README.txt            this file
    settings.txt          a few switches (yes / no), explained inside
    system\               everything the mods run on: the menu, the cheat
                          lists (system\cheats, with yours too),
                          translations, your saved switches and the save
                          backups (system\save-backups).


THE CHEAT MENU
--------------
"Play with mods.bat" opens the cheat menu. On the left the pages (Speed &
comfort, Experience & gold, Party, Battle, Items...), a search box, and
"Switched on" with everything that is on now. Press Play to start the game;
keep the menu open while you play.
The menu is black with neon green text, set in JetBrains Mono (mods/system/fonts, SIL Open
Font License); without those font files it falls back to Consolas.

Each cheat is one of these:

- A switch. On = it works from now on, every frame, like a code that is ticked
  on an R4. Switch what you like before you press Play, or while you play.
- "Once" / "Do it": carries the code out one time, now (99 of every shield,
  all Zoom places...). Many cheats have both.
- A choice (Experience x2 / x4 / ... / x128, movement speed, a vocation...):
  only one of them can be on.
- A cheat with buttons next to its name (SELECT, L+R...) works as on a DS:
  switch it on, then hold those buttons in the game. "Once" does it right
  away without the buttons.

The labels:

  TRIED OUT    tried in this version of the game.
  UNTESTED     from the R4 list, checked as far as a program can (below), but
               not tried here. Save first.
  BUILT IN     it changes how the game works, so it is built into the game:
               after you switch it, Play rebuilds the parts of the game that
               changed (about half a minute to a few minutes), then starts it.
  NEXT START   takes effect the next time the game starts from the menu
               ("Always fast forward", "Instant loading").

"Everything off" switches all of it off. Each time you press Play a copy of
your save goes to mods\system\save-backups (the last 30).


WHERE THE CHEATS COME FROM, AND WHY THEY CAN'T BREAK THE GAME
-------------------------------------------------------------
mods\system\cheats\r4-YDQP.txt (Europe) and r4-YDQE.txt (USA) hold the whole list for the
game from the community's R4 cheat database (DeadSkullzJr's NDS(i) Cheat
Databases): 216 codes for the European version, 271 for the USA one. To them
come the other files in mods\system\cheats (made and tried by hand; yours go
there too).

An Action Replay code is written for a DS, where it may change anything at any
moment. Here the game's program is compiled PC code. So before the menu shows
a code, mods\system\tools\catalog.py runs it against a copy of your own ROM's program
and sorts it:

- It only changes the game's data: a live cheat. The game carries it out
  itself, at one fixed point of each frame. A code can only write the DS's
  main memory, and a code that would loop forever is cut off, so it can't
  freeze a frame.
- It changes instructions: a "built in" mod. Every instruction it changes was
  found in your ROM where the code says it is; what the menu writes into the
  build is exactly those words and nothing else. Two mods that change the same
  instruction differently can't both be on (the menu makes them one choice).
- It can't work here, or can't be checked: it is listed under "Not available"
  with the reason, and can't be switched on. That is: codes that add a routine
  of their own to the program or send it somewhere outside its own code,
  codes whose new instructions write into the program, codes that change the
  program and data together, codes for DS hardware (backlight), codes that
  don't fit your ROM, and the anti-piracy and Wi-Fi codes (not needed here).

The menu is a program of its own. Whatever happens in it, the game keeps
running: the menu only puts cheats into the game's mailbox.

What a program can't check is what a data cheat does to your save: "Max
everything" codes can make a save odd. That is what UNTESTED warns about, and
what the save copies are for.

A newer usrcheat.dat? "mods\system\tools\r4_to_text.py usrcheat.dat YDQP
mods\system\cheats\r4-YDQP.txt" brings the list up to date; "Reload list" in the menu
reads it.


WHY THEY SURVIVE UPDATES
------------------------
The game's own program comes from your ROM, and your ROM never changes. So the
addresses and instructions these mods use never change either, whatever the
developer changes in the PC side of the game.

- Live cheats are carried out by the game itself, through a small part of
  the mods that Play builds into it (see "Playing with friends"). An update
  takes that part out; the next Play puts it back. Until then, and with
  "sync_cheats = no", the menu writes into the game from outside: it finds the
  DS's memory in the running game by the cartridge header and the program
  next to it. That works with any build of dqix.exe, but not with friends,
  and there cheats with buttons only work through "Once".

- Built-in mods go into the game's patches.txt (the project's own way to
  change instructions when it rebuilds the game) between two marker lines. An
  update replaces patches.txt and rebuilds without them. The next Play
  notices (mods\system\bin\built.txt remembers what the built game has in it), puts
  them back and rebuilds. After an update the game starts by itself WITHOUT
  them: close it and press Play in the menu once.

- The update never deletes the mods folder (it only copies new files over the
  project), so what you switched on stays (mods\system\menu-state.txt).


USA AND EUROPEAN ROMS
---------------------
Both work. The menu takes the list for your ROM (its game code, YDQP or YDQE).
The files in mods\system\cheats serve both: the European ROM is the
same program with the main code moved by 16 bytes (8 for a little near the
start); the data, where the cheats write, and the overlays, where most code
mods are, are in the same place.

- A code mod file may give its address as in the USA code or as in the
  European code, either is found. It is checked against your ROM either way.
- The database lists a few USA codes under the European game. When such a
  code's instructions are in your ROM 16 bytes further on, it is moved there
  (the menu says so in its note); otherwise it is "Not available".
- "AR-codes-EU.txt" (or -USA) in this folder lists your own files as Action
  Replay codes for your ROM. Play writes it again each time.


PLAYING WITH FRIENDS (WIRELESS)
-------------------------------
Live cheats work while playing with friends, when every player's game has
these mods in it.

Why that is needed: in a session every PC runs every player's DS, and they
must all compute exactly the same. So a cheat can't just be written into your
PC's memory. It travels with your button presses instead: the menu hands it
to your game, your game sends it to the others like a button, and every PC
carries it out for your DS in the same frame. For that, a small part of the
mods is built into the game (mods\system\src\mod_cheats.c).

What to do:
1. Give every player this mods folder. Each presses Play in the menu once.
2. Host and join as usual. The menu says "Playing with friends".
3. Use the cheats as when alone. They only change your own DS (your hero,
   your gold, your bag), on every PC at once. Your friends don't need the same
   cheats on, and can use their own the same way.

Sending takes a moment (a fifth of a second for a short code, a few seconds
for the "99 of every..." ones); the stylus is lifted while it lasts.

If one player's game doesn't have the mods in it (or has an older version of
them: this one is version 2), the first cheat puts the session out of sync
(the title bar says so). Without cheats such a session plays normally.
"sync_cheats = no" in settings.txt leaves that part out for good; then cheats
are written from outside and must not be used with friends.

Built-in mods (BUILT IN: faster text, experience x2...) are part of how the
game computes: every player needs exactly the same ones built into their game,
or the session goes OUT OF SYNC. The menu shows a short name for what is built
in at the top ("built-in set 3F2A"): it has to be the same for everyone. The
simple way: switch the built-in ones off before playing with friends.

"Instant loading" only works while you play alone. In a session the game
keeps the cartridge's real timing by itself (a second small change of the
mods, in runtime\card.c), so it can't put a session out of sync.


MAKE YOUR OWN
-------------
Live cheat (mods\system\cheats\anything.txt): any Action Replay DS code that writes
data.

    # name: What the menu shows
    # mode: always          (a switch; or: once = a "Do it" button)
    # about: optional note
    # category: Party       (the page; without it: "Custom")
    020F6D48 0098967F

Code mod (mods\system\cheats\anything.txt, with "patch" lines):

    # name: What it's called
    # enabled: no           (the menu's switch changes this line)
    patch 0215525C E0832002 E0832082     address, the instruction there now, the new one
    check 021864A4 E3550000              must be there for the mod to apply
    patch 021864A8 E1A00000              (address, new) only together with a check

An Action Replay "5XXXXXXX YYYYYYYY" line is a check; the "0XXXXXXX YYYYYYYY"
lines after it that write instructions are patches. USA or European addresses.
Swapping an instruction for another (nop, mov, a branch to a place inside the
game's code) is safe; a jump to code of your own is not, and isn't possible.

Press "Reload list" in the menu after you add or change a file.


WITHOUT THE MENU
----------------
"cheat_window = no" in settings.txt: "Play with mods.bat" builds the code mods
whose files say "enabled: yes" (and the database codes named in
mods\system\menu-state.txt) into the game and starts it, without the menu. Live
cheats need the menu.


UNDO EVERYTHING
---------------
Press "Everything off" in the menu, set "sync_cheats = no" in settings.txt,
and press Play once (it takes the mods out and rebuilds). Then delete the mods
folder.


Codes: the community's Action Replay codes for DQIX (USA and Europe), from
DeadSkullzJr's NDS(i) Cheat Databases (gbatemp.net) and as collected at
almarsguides.com. The "99 of every..." bag cheats, the whole party's HP / MP
and the battle HP / MP and walk-through-walls mods are from the latter's
European list.
