/* DQIX Enhanced mods: "Always strike first".
 *
 * When a battle starts on the field, func_ov017_02196430 (the field's "did a monster touch you" check) asks
 * func_ov017_021970a0 who gets the first move: `bl 021970a0` at 0x02196b40, its answer is stored right after.
 * The Action Replay code replaces that call with `mov r0, #1` (the party strikes first). That instruction sits in a
 * function vanish.c already wraps, so it can't be patched live; instead the called function is wrapped
 * (wrap.txt line, added by mods/system/tools/apply_runtime_mod.py): while the cheat is on and the call comes from
 * that one place (lr = 0x02196b44), it is not run and answers 1, exactly what the code does. Calls from anywhere
 * else run as always. Overlay addresses are the same in the USA and European ROM.
 *
 * g_mod_first is set each frame from this console's own input stream (mod_cheats.c), so it is the same on every PC
 * of a session. DQIX_MODLOG=1 logs each answer at that place (tests/test_firststrike.py).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "cpu.h"

extern uint8_t g_mod_first;            /* mod_cheats.c: set each frame by the cheat while it is on */
extern uint64_t g_frame;
void wrap_firststrike_orig(Cpu* c);

#define FIRST_STRIKE_RET 0x02196B44u   /* the instruction after the `bl` at 0x02196b40 */

void wrap_firststrike(Cpu* c) {
    int here = c->r[14] == FIRST_STRIKE_RET;
    if (!g_mod_first || !here) {
        wrap_firststrike_orig(c);
        if (here && getenv("DQIX_MODLOG")) fprintf(stderr, "mod: firststrike game says %u at frame %llu\n", (unsigned)c->r[0], (unsigned long long)g_frame);
        return;
    }
    c->r[0] = 1;
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: firststrike party first at frame %llu\n", (unsigned long long)g_frame);
}
