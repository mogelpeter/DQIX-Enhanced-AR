DQIX ENHANCED - CHEATS
======================

Cheats and code mods for DQIX Enhanced (github.com/sackchief/dqix-enhanced),
in a cheat list like the one of an R4 / Action Replay card, built right into
the game: a "Cheats" tab in the game's own menu bar. They keep working when
the game updates itself.


INSIDE THE GAME
---------------
Start the game as always (game\dqix.exe). In its menu bar (next to Mods and Help):

- Cheats > Cheats...  opens the cheat list in a window of the game itself. The game keeps
  running. Tick a cheat and it is on at once: no restart, and no rebuild for almost all code
  mods too. What you tick is saved in mods\system\menu-state.txt and sent again by itself
  when the game starts. Nothing is on until you switch it on.
- Cheats > Save editor...  opens your save in the editor website (the language box is in the
  page, at the bottom right). Export puts the edited save into the game, which starts again
  with it (the old save is kept in save-backups next to the game).
- Cheats > Treasure maps...  opens the treasure map search website.

When the game updates itself (Help > Check for updates) the tab is put back automatically.
If an update changed the game's code where the mods go in, Apply cheats.bat finds the places
anyway (other spacing or line breaks, the newer menu bar made from a table). If the game then
doesn't build with one of them, that one is left out and the game is built without it (the
window says which; mods\system\bin\build.log has the build's output, repatch.txt how each
place was found). It is tried again with the next update of the game or of the mods.
If you update by hand (a new download), run Install cheats.bat once more.


INSTALL
-------
Build the game once the normal way first (if you haven't already). Then double-click
"Install cheats.bat" in the folder you downloaded. It finds your DQIX Enhanced folder,
copies this "mods" folder next to BUILD.bat and builds the Cheats tab into the game
(a few minutes the first time):

    DQIX Enhanced\
        BUILD.bat
        game\
        mods\          <- here

What is in the mods folder:

    Apply cheats.bat      puts the cheats into the game and rebuilds what changed. The
                          installer, the game's updater and the Cheats window run it
                          for you; run it yourself after an update by hand or after you
                          changed a cheat file.
    README.txt            this file
    settings.txt          one switch (yes / no), explained inside
    system\               everything the cheats run on: the cheat lists (system\cheats,
                          yours go there too), the save editor's translations, your
                          saved switches and the save backups (system\save-backups).


THE CHEATS WINDOW
-----------------
On the left the pages (Speed & comfort, Camera, Experience & gold, Party, Battle, Items,
Treasure maps, ...),
first "Enabled": everything that is on now, from every page. The search box above them
finds a cheat by the words of its name, option, note, page or keys (all words must fit;
inside a choice only the fitting options are offered; the first 60 hits are shown). Under each cheat a grey line
says who needs it in a session, the buttons to hold (in blue) and its labels; hover a row
for a longer explanation of what it does. You can keep the window open while you play.
Big pages are folded into sections (Party: Whole party, Hero, Player 2-4; Battle: Party buffs,
Enemy debuffs, Monster AI, Encounters): click a section's bar to open or close it.

Each cheat is one of these:

- A switch (check box). On = it works from now on, every frame, like a code that is
  ticked on an R4.
- "Do it now": carries the code out one time, now (99 of every shield, all Zoom
  places...). Many cheats have both.
- A choice (Experience x2 / x4 / ... / x128, movement speed, a vocation...): a drop-down
  with "Off" and the options; only one of them can be on.
- A cheat with buttons ("hold SELECT", "hold L+R"...) works as on a DS: switch it on,
  then hold those buttons in the game. "Do it now" does it right away without them.

The labels in the grey line:

  untested         from the R4 list, checked as far as a program can (below), but not
                   tried here. Save first.
  needs a rebuild  a code mod that can't switch while the game runs. None of the shipped
                   cheats needs it (a code of your own or from a newer R4 list might).
                   The window offers to rebuild the game (a few minutes) and start it again.
  next start       takes effect the next time the game starts ("Battle any monster
                   you want", "Metal slimes only", "Instant loading"...). The window
                   offers to restart the game.

"Everything off" switches all of it off. The Fun cheats (big head, size, hidden party) put
the game back the moment they are switched off.

"Share" copies what you have on as one line of text to the clipboard: paste it in a chat.
A friend copies that line and presses "Import": the same cheats are on for them (what they
had on before is switched off).

Before the save editor writes your save, a copy
goes to mods\system\save-backups (the last 30).


WHERE THE CHEATS COME FROM, AND WHY THEY CAN'T BREAK THE GAME
-------------------------------------------------------------
mods\system\cheats\r4-YDQP.txt (Europe) and r4-YDQE.txt (USA) hold the whole list for the
game from the community's R4 cheat database (DeadSkullzJr's NDS(i) Cheat Databases):
216 codes for the European version, 271 for the USA one. To them come the other files in
mods\system\cheats (made and tried by hand; yours go there too).

An Action Replay code is written for a DS, where it may change anything at any moment.
Here the game's program is compiled PC code. So before the window shows a code,
mods\system\tools\catalog.py runs it against a copy of your own ROM's program and sorts it:

- It only changes the game's data: a live cheat. The window puts it into the game's
  mailbox, and the game carries it out itself at one fixed point of each frame. A code
  can only write the DS's main memory, and a code that would loop forever is cut off,
  so it can't freeze a frame.
- It changes instructions: a code mod. Every instruction it changes was found in your
  ROM where the code says it is, and only those words are ever used. The game is built
  once with a wrapper around every function a code mod touches; while a mod is on, that
  function runs in the game's own ARM interpreter with the mod's instruction in it. Two
  mods that change the same instruction differently can't both be on (the window makes
  them one choice).
- It can't work here, or can't be checked: it is left out of the window. That is: codes
  that add a routine of their own to the program or jump somewhere outside its own code,
  codes whose new instructions write into the program, codes that change program and
  data together, codes for DS hardware (backlight), codes that don't fit your ROM, and
  the anti-piracy and Wi-Fi codes (not needed here).

What a program can't check is what a data cheat does to your save: "Max everything"
codes can make a save odd. That is what "untested" warns about, and what the save copies
are for.

A newer usrcheat.dat? "mods\system\tools\r4_to_text.py usrcheat.dat YDQP
mods\system\cheats\r4-YDQP.txt" brings the list up to date; "Apply cheats.bat catalog"
reads it (then restart the game).


WHY THEY SURVIVE UPDATES
------------------------
The game's own program comes from your ROM, and your ROM never changes. So the addresses
and instructions these cheats use never change either, whatever the developer changes in
the PC side of the game.

- The Cheats tab, its window and the part that carries the cheats out are a handful of
  small, marked changes in the game's source that Apply cheats.bat makes before the game
  is built. An update replaces those files; the game's updater runs Apply cheats.bat
  before it rebuilds, so they are back at once.
- A code mod that needs a rebuild goes into the game's patches.txt between two marker
  lines. An update replaces patches.txt; Apply cheats.bat notices
  (mods\system\bin\built.txt remembers what the built game has in it), puts it back and
  rebuilds.
- The update never deletes the mods folder (it only copies new files over the project),
  so what you switched on stays (mods\system\menu-state.txt).


USA AND EUROPEAN ROMS
---------------------
Both work. The cheat list is the one for your ROM (its game code, YDQP or YDQE). The
files in mods\system\cheats serve both: the European ROM is the same program with the
main code moved by 16 bytes (8 for a little near the start); the data, where the cheats
write, and the overlays, where most code mods are, are in the same place.

- A code mod file may give its address as in the USA code or as in the European code;
  either is found. It is checked against your ROM either way.
- The database lists a few USA codes under the European game. When such a code's
  instructions are in your ROM 16 bytes further on, it is moved there (its note says
  so); otherwise it is left out.
- "system\AR-codes-EU.txt" (or -USA) lists your own files as Action Replay codes for
  your ROM. Apply cheats.bat writes it again each time.


PLAYING WITH FRIENDS (WIRELESS)
-------------------------------
The cheats work while playing with friends, when every player's game has them built in.

Why that is needed: in a session every PC runs every player's DS, and they must all
compute exactly the same. So a cheat can't just be written into your PC's memory. It
travels with your button presses instead: the window hands it to your game, your game
sends it to the others like a button, and every PC carries it out for your DS in the same
frame. Code mods switched in the window travel the same way.

What to do:
1. Give every player this download. Each runs Install cheats.bat once.
2. Host and join as usual.
3. Use the cheats as when alone. They only change your own DS (your hero, your gold,
   your bag), on every PC at once. Your friends don't need the same cheats on, and can
   use their own the same way. The grey line says which cheats one player is enough
   for and which every player needs ("next start", "needs a rebuild").

Sending takes a moment (a fifth of a second for a short code, a few seconds for the
"99 of every..." ones); the stylus is lifted while it lasts.

If one player's game doesn't have the cheats in it (or an older version of them: this one
is version 3), the first cheat puts the session out of sync (the title bar says so).
Without cheats such a session plays normally.

A code mod that needs a rebuild (none of the shipped ones) would change how the game
computes: every player would need it the same, or the session goes OUT OF SYNC.

"Instant loading" only works while you play alone. In a session the game keeps the
cartridge's real timing by itself, so it can't put a session out of sync.


MAKE YOUR OWN
-------------
Live cheat (mods\system\cheats\anything.txt): any Action Replay DS code that writes data.

    # name: What the window shows
    # mode: always          (a switch; or: once = a "Do it now" button)
    # about: optional note
    # category: Party       (the page; without it: "Miscellaneous")
    020F6D48 0098967F

Code mod (mods\system\cheats\anything.txt, with "patch" lines):

    # name: What it's called
    # enabled: no
    patch 0215525C E0832002 E0832082     address, the instruction there now, the new one
    check 021864A4 E3550000              must be there for the mod to apply
    patch 021864A8 E1A00000              (address, new) only together with a check

Most code mods become a switch in the window that works while you play. The few the game
can't switch live say so in the window; for those, set "# enabled: yes" in the file and
run Apply cheats.bat.

An Action Replay "5XXXXXXX YYYYYYYY" line is a check; the "0XXXXXXX YYYYYYYY" lines after
it that write instructions are patches. USA or European addresses. Swapping an
instruction for another (nop, mov, a branch to a place inside the game's code) is safe;
a jump to code of your own is not, and isn't possible.

Run "Apply cheats.bat catalog" after you add or change a file, then restart the game.


UNDO EVERYTHING
---------------
Press "Everything off" in the Cheats window and close the game. Set "sync_cheats = no" in
settings.txt and run "Apply cheats.bat" once: it takes the Cheats tab and everything else
out of the game's source and rebuilds it. Then delete the mods folder. Your save
(game\dqix.sav) is never touched.


Codes: the community's Action Replay codes for DQIX (USA and Europe), from DeadSkullzJr's
NDS(i) Cheat Databases (gbatemp.net) and as collected at almarsguides.com. The
"99 of every..." bag cheats, the whole party's HP / MP and the battle HP / MP and
walk-through-walls mods are from the latter's European list.
