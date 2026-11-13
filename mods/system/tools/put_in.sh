#!/bin/sh
# The mods into the game's build (run by "Play with mods.bat", from the DQIX
# Enhanced folder). Leaves 0 = the game that is built has them, 10 = the game
# has to be rebuilt, 1 = something is wrong (nothing was changed).
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
echo "Code mods:"
$PY mods/system/tools/apply_code_mods.py .
[ $? -eq 1 ] && exit 1
# the mods' own part of the game: live cheats that also work with friends (mods/system/src/runtime/mod_cheats.c)
$PY mods/system/tools/apply_runtime_mod.py .
[ $? -eq 1 ] && exit 1
# your own codes as Action Replay codes for this ROM (mods/system/AR-codes-*.txt), for reference
$PY mods/system/tools/make_ar_list.py . >/dev/null 2>&1
# is the game that is built the one with exactly these in it? (mods/system/bin/built.txt)
$PY mods/system/tools/build_stamp.py . check
exit $?
