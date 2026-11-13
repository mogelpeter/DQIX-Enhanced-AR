/* DQIX Enhanced mods: "Vanish" (walk through monsters until you vanish again).
 *
 * The field overlay (ov017) asks func_ov017_02196430 once a frame whether a monster on the field has touched the
 * party and a battle has to start. It returns 1 when it opened a battle, 2 when the field is busy with something
 * else and 0 when nothing happened; its only caller is at 0x0218ce38.
 *
 * While vanish is on (mods/system/src/mod_cheats.c: the cheat "Vanish" is switched on and the buttons
 * L+R+SELECT flipped it) the check is not run at all and answers 0: nothing touches you. Monsters still
 * walk around and still look for you, they just can't start a fight by touching. Story battles are
 * started by the game's events, not by this check, and still happen.
 *
 * The wrap line is in wrap.txt (added by mods/system/tools/apply_runtime_mod.py, USA = EUR address for overlays).
 * g_mod_vanish is set from this console's own input stream, so it is the same on every PC of a session.
 */
#include <stdint.h>
#include "cpu.h"

extern uint8_t g_mod_vanish;
void wrap_enccheck_orig(Cpu* c);

void wrap_enccheck(Cpu* c) {
    if (!g_mod_vanish) { wrap_enccheck_orig(c); return; }
    c->r[0] = 0;
}
