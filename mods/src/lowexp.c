/* DQIX Enhanced mods: "Lower-level characters get more experience".
 *
 * The Action Replay cheat for this writes a routine of its own into RAM, which a
 * recompiled game can't run. Here the same thing is done around the game's own code
 * (wrap.txt lines, added by mods/tools/apply_runtime_mod.py):
 *
 *   ov023 021f4098  the experience share of one party member (r1 = member). It asks
 *                   func_0202053c (the member's level) for every member present, turns
 *                   the levels into floats and works the share out from them.
 *
 * Wrapped: the share is worked out twice. The first time only watches the levels asked
 * for (lowest and highest of the party). The second time every level comes back as
 * (lowest + highest - level), which is what the cheat does: the lowest-level member gets
 * what the highest would have, and the other way round. The first run's result is thrown
 * away; the routine only reads game data, so running it twice changes nothing else.
 *
 * Only while the cheat "Lower-level characters get more experience" (mods/cheats) is on. It
 * travels in the input stream like every live cheat, so in a session every PC switches it
 * on and off on the same frame and they all work out the same experience.
 */
#include <stdint.h>
#include "cpu.h"

extern uint8_t g_mod_lowexp;           /* mod_cheats.c: set each frame by the cheat while it is on */
void wrap_lowexp_orig(Cpu* c);
void wrap_lowlvl_orig(Cpu* c);

static int g_phase;                    /* 0: not inside the share, 1: watching, 2: changing */
static uint32_t g_lo, g_hi;

static int lowexp_on(void) { return g_mod_lowexp != 0; }

void wrap_lowlvl(Cpu* c) {
    wrap_lowlvl_orig(c);
    if (!g_phase) return;
    uint32_t lv = c->r[0] & 0xFFFF;
    if (g_phase == 1) {
        if (lv < g_lo) g_lo = lv;
        if (lv > g_hi) g_hi = lv;
    } else if (g_hi >= g_lo) {
        c->r[0] = (g_lo + g_hi - lv) & 0xFFFF;
    }
}

void wrap_lowexp(Cpu* c) {
    if (g_phase || !lowexp_on()) { wrap_lowexp_orig(c); return; }
    Cpu saved = *c;
    g_phase = 1; g_lo = 0xFFFFFFFFu; g_hi = 0;
    wrap_lowexp_orig(c);                                  /* result thrown away */
    *c = saved;
    g_phase = 2;
    wrap_lowexp_orig(c);
    g_phase = 0;
}
