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
void interp_stub(Cpu* c, uint32_t addr);

#define ENC_FUNC   0x02196430u
static const struct { uint32_t at, game, vanish; } k_site[2] = {
    { 0x021965C0u, 0x1A0000F7u, 0xEA0000F7u },        /* bne / b 0x021969a4: past the monster loop */
    { 0x02196ADCu, 0x0A000040u, 0xEA000040u },        /* beq / b 0x02196be4: "nothing happened" */
};

static uint32_t* ram32(uint32_t a) { return (uint32_t*)&g_main_ram[a & (MAIN_RAM_SIZE - 1)]; }

void wrap_enccheck(Cpu* c) {
    if (!g_mod_vanish) { wrap_enccheck_orig(c); return; }
    for (int i = 0; i < 2; i++) if (*ram32(k_site[i].at) != k_site[i].game) { c->r[0] = 0; return; }
    static int logged;
    if (!logged && getenv("DQIX_MODLOG")) { logged = 1; fprintf(stderr, "mod: vanish runs the contact check without touches at frame %llu\n", (unsigned long long)g_frame); }
    for (int i = 0; i < 2; i++) *ram32(k_site[i].at) = k_site[i].vanish;
    interp_stub(c, ENC_FUNC);
    for (int i = 0; i < 2; i++) *ram32(k_site[i].at) = k_site[i].game;
}
