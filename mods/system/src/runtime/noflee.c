/* DQIX Enhanced mods: "Monsters can't flee".
 *
 * A monster that flees does it as its action of the round: the battle's command builder (ov000 0215767c)
 * asks the AI "what does this combatant do?" through func_0208a92c (USA 0208a91c), which hands back the action
 * number; 225 (0xE1) and 917 are the two actions called Flee. Those numbers are chosen at random from the monster's list, with the party's strength
 * and the monster's own rules in play, so refusing "Flee" in one question (what the first version of this cheat did) is
 * not enough: the monster simply decides again later. Here the answer itself is wrapped (wrap.txt line, added by
 * mods/system/tools/apply_runtime_mod.py): while the cheat is on and the AI says Flee, it is asked again, up to 200 times,
 * and the first other answer is taken. Only the AI's random numbers are used up by that, the same on every PC of a session
 * (the cheat travels in the input stream like every live cheat, so all PCs switch it on in the same frame).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "cpu.h"

extern uint64_t g_frame;

extern uint8_t g_mod_noflee;           /* mod_cheats.c: set each frame by the cheat while it is on */
void wrap_noflee_orig(Cpu* c);

/* the action table (618 records, ids 1..945) names two actions "Flee": 225 and 917 */
#define IS_FLEE(id) ((id) == 225u || (id) == 917u)

void wrap_noflee(Cpu* c) {
    if (!g_mod_noflee) { wrap_noflee_orig(c); return; }
    Cpu saved = *c;
    for (int i = 0; i < 200; i++) {
        wrap_noflee_orig(c);
        if (!IS_FLEE(c->r[0] & 0xFFFFu)) return;
        *c = saved;                    /* it said Flee: ask again */
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: noflee asked again at frame %llu (try %d)\n", (unsigned long long)g_frame, i + 1);
    }
    wrap_noflee_orig(c);
}
