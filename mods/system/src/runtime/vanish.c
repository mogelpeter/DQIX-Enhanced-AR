/* DQIX Enhanced mods: "Vanish" (walk through monsters until you vanish again).
 *
 * The field overlay (ov017) asks func_ov017_02196430 once a frame whether a monster on the field has touched the
 * party and a battle has to start. It returns 1 when it opened a battle, 2 when the field is busy with something
 * else and 0 when nothing happened; its only caller is at 0x0218ce38.
 *
 * Inside, a loop goes over the field monsters (0x021965d4..0x02196998). For a monster that touches the party it
 * pushes the hero out of the monster's reach (0x021966dc) or, for a real touch, puts the monster into the state
 * "a battle starts with me" (fn_main_02076cdc(monster, 8) at 0x02196914) and sets r6 = 1; after the loop, r6 = 1
 * opens the battle (0x02196adc).
 *
 * The first version of this skipped the whole function while vanished: nothing reset that state, so a monster that
 * had touched you stood frozen next to you (canniboxes most visibly). Skipping only the battle start (what the Action
 * Replay code "Run Through Enemies" does at 0x02196adc) leaves the same frozen monster (tests/test_vanish_walk.py
 * pictures). Now the function runs as always, in the runtime's ARM interpreter, with two instructions changed for
 * the call:
 *   0x021965c0  bne 0x021969a4 -> b 0x021969a4   the monster loop is not run: no monster touches you, none is pushed
 *                                                 against, none waits for a battle; they walk on
 *   0x02196adc  beq 0x02196be4 -> b 0x02196be4   whatever else asks for a battle here (r6) starts none
 * Story battles are started by the game's events, not by this check, and still happen. If either instruction isn't
 * the expected one (another game version), the old way (answer 0 without running) is used.
 *
 * While vanish is on (mods/system/src/runtime/mod_cheats.c: the cheat "Vanish" is switched on and the buttons
 * L+R+SELECT flipped it). The wrap line is in wrap.txt (added by mods/system/tools/apply_runtime_mod.py, USA = EUR
 * address for overlays). g_mod_vanish is set from this console's own input stream, so it is the same on every PC.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "cpu.h"
#include "nds.h"

extern uint8_t g_mod_vanish;
extern uint64_t g_frame;
void wrap_enccheck_orig(Cpu* c);
void fn_main_0200f398(Cpu* c);       /* GameState::GetInstance */
void fn_main_0200fddc(Cpu* c);       /* GameState::GetProtagonist(this): the hero's field object */
/* GameState::GetPartyMemberByIndex (0x0200fe00) and Object3D::TransitionInheritedAlpha(obj, alpha 0..31, frames) (0x020372c8, the game's own fade) are
 * called by address: the recompiler doesn't always make a function of its own there, dispatch_call works either way */
#define GET_PARTY_MEMBER   0x0200fe00u
#define TRANSITION_ALPHA   0x020372c8u
void interp_stub(Cpu* c, uint32_t addr);

#define ENC_FUNC   0x02196430u
static const struct { uint32_t at, game, vanish; } k_site[2] = {
    { 0x021965C0u, 0x1A0000F7u, 0xEA0000F7u },        /* bne / b 0x021969a4: past the monster loop */
    { 0x02196ADCu, 0x0A000040u, 0xEA000040u },        /* beq / b 0x02196be4: "nothing happened" */
};

static uint32_t* ram32(uint32_t a) { return (uint32_t*)&g_main_ram[a & (MAIN_RAM_SIZE - 1)]; }

/* A vanished party looks like a ghost: the party members' field objects are faded to about a third (the game's own fade, 10 frames), and back
 * to solid when the vanish ends. The contact check runs once a frame in the field, so the fade is started from it; while vanished it is repeated
 * once a second (an object made new, e.g. after a map change, starts solid). The registers of the check are kept. */
#define GHOST_ALPHA 10
static void ghost(Cpu* c, int on) {
    Cpu save = *c;
    uint32_t done[5]; int nd = 0;
    for (int i = -1; i < 4; i++) {                      /* -1: the protagonist, then the party members */
        fn_main_0200f398(c);
        if (i < 0) fn_main_0200fddc(c); else { c->r[1] = (uint32_t)i; dispatch_call(c, GET_PARTY_MEMBER, 0); }
        uint32_t obj = c->r[0]; int dup = 0;
        for (int k = 0; k < nd; k++) if (done[k] == obj) dup = 1;
        if (!obj || dup) continue;
        done[nd++] = obj;
        c->r[0] = obj; c->r[1] = on ? GHOST_ALPHA : 31; c->r[2] = 10;
        dispatch_call(c, TRANSITION_ALPHA, 0);
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: ghost %d object %08x (%d)\n", on, obj, i);
    }
    *c = save;
}

void wrap_enccheck(Cpu* c) {
    static int ghosted; static uint64_t last;
    if (g_mod_vanish != ghosted || (g_mod_vanish && g_frame - last >= 30)) { ghost(c, g_mod_vanish); ghosted = g_mod_vanish; last = g_frame; }
    if (!g_mod_vanish) { wrap_enccheck_orig(c); return; }
    for (int i = 0; i < 2; i++) if (*ram32(k_site[i].at) != k_site[i].game) { c->r[0] = 0; return; }
    static int logged;
    if (!logged && getenv("DQIX_MODLOG")) { logged = 1; fprintf(stderr, "mod: vanish runs the contact check without touches at frame %llu\n", (unsigned long long)g_frame); }
    for (int i = 0; i < 2; i++) *ram32(k_site[i].at) = k_site[i].vanish;
    interp_stub(c, ENC_FUNC);
    for (int i = 0; i < 2; i++) *ram32(k_site[i].at) = k_site[i].game;
}
