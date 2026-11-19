/* DQIX Enhanced mods: hooks in the battle's action routine: the Challenges page ("Tougher monsters": the damage monsters deal) and the
 * "All buffs" / "All debuffs" buttons (their effect on the stats at once).
 *
 * The damage of an action is worked out per target by func_ov024_021e6a90 (the battle's action routine, ov024 021eb5d0, calls it at
 * 021ec7a4; arguments: r0 the battle, r1 who acts, r2 the target, both fighter numbers: 0..3 the party, a monster above, r3 the action's
 * record, the first stack word the damage before it; it returns the damage that is dealt). Attacks, spells and breath all go through it.
 * While "Tougher monsters" is on (mod_cheats.c g_mod_tough, the multiplier in halves), damage a monster deals to a party member is
 * multiplied the same way (at most 9999). Monsters' HP is mod_cheats.c's. Buffs, defence and resistances still count, they come before.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cpu.h"
#include "nds.h"

void dispatch_call(Cpu* c, uint32_t target, uint32_t from);

extern uint32_t g_mod_tough;
void wrap_toughdmg_orig(Cpu* c);

/* "Always 4-hit combo" (mod_cheats.c g_mod_combo: party members, bits 0..3). This same function applies the combo: when the action can combo
 * (its record's word at +0x2C, bit 27) the damage is multiplied by {1, 1.2, 1.5, 2}[count], the count being the byte at +0x8E83 of the battle
 * (r0+0x10; ov024 021ea584 counts the hits on one target in a row, ov000 0215d090 clears it), at most 3, and the count goes into the hit's result,
 * which shows "n-hit combo!". So for those members the count is 3 (the fourth hit, x2) just before each of their hits. */
extern uint32_t g_mod_combo;
static void force_combo(Cpu* c) {
    uint32_t who = c->r[1], battle, act = c->r[3];
    if (!g_mod_combo || who > 3 || !(g_mod_combo & (1u << who))) return;
    memcpy(&battle, &g_main_ram[(c->r[0] + 0x10) & (MAIN_RAM_SIZE - 1)], 4);
    uint32_t flags; memcpy(&flags, &g_main_ram[(act + 0x2C) & (MAIN_RAM_SIZE - 1)], 4);
    if (battle < 0x02000000u || battle >= 0x02000000u + MAIN_RAM_SIZE || !((flags >> 27) & 1)) return;
    g_main_ram[(battle + 0x8E83u) & (MAIN_RAM_SIZE - 1)] = 3;
}

void wrap_toughdmg(Cpu* c) {
    uint32_t who = c->r[1], target = c->r[2], k = g_mod_tough;
    force_combo(c);
    wrap_toughdmg_orig(c);
    if (k >= 3 && who > 3 && who < 0xE9 && target <= 3 && (int32_t)c->r[0] > 0) {
        uint32_t d = c->r[0] * k / 2; if (d > 9999) d = 9999; c->r[0] = d; }
}

/* "All buffs" / "All debuffs": the battle works with each fighter's attack (+8 of its battle stats), defence (+0xA), agility (+0xC) and three more
 * as numbers made from its base stats and its effect levels (ov000 02155a50 .. 02155d90; 02155e44(battle, fighter) does all six). The game does
 * that when something is cast on the fighter, and for the one who acted at the end of each action (ov024 021ed880). The buttons write the levels,
 * so the stats followed only after that fighter's own next action: the boost seemed to do nothing. Now, at the start of every action (the action
 * routine ov024 021eb5d0, arguments: r0 the action's context, whose +0x10 is the battle), each fighter whose button was used (mod_cheats.c
 * g_mod_recalc: battle stats addresses) is worked out again by the game's own 02155e44 first. The fighters: the game object 020F33D8 + 8 +
 * index * 4, 0x80 in the first halfword, battle stats at +0x138. Registers are kept. */
extern uint32_t g_mod_recalc[16]; extern int g_mod_nrecalc;
void wrap_actrecalc_orig(Cpu* c);
static uint32_t r32(uint32_t a) { uint32_t v; memcpy(&v, &g_main_ram[a & (MAIN_RAM_SIZE - 1)], 4); return v; }
static uint16_t r16(uint32_t a) { uint16_t v; memcpy(&v, &g_main_ram[a & (MAIN_RAM_SIZE - 1)], 2); return v; }
static int in_ram(uint32_t a) { return a >= 0x02000000u && a < 0x02000000u + MAIN_RAM_SIZE - 0x200u; }

void wrap_actrecalc(Cpu* c) {
    if (g_mod_nrecalc) {
        Cpu save = *c;
        uint32_t battle = r32(save.r[0] + 0x10);
        for (uint32_t i = 0; i < 0xE9; i++) {
            uint32_t e = r32(0x020F33D8u + 8 + 4 * i);
            if (!in_ram(e) || !(r16(e) & 0x80)) continue;
            uint32_t st = r32(e + 0x138);
            for (int k = 0; k < g_mod_nrecalc; k++) {
                if (g_mod_recalc[k] != st) continue;
                *c = save; c->r[0] = battle; c->r[1] = i;
                dispatch_call(c, 0x02155E44u, 0x021EB5D0u);
                if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: buffs: fighter %u's stats worked out again (attack %u, defence %u, agility %u)\n",
                                                   i, r16(st + 8), r16(st + 0xA), r16(st + 0xC));
            }
        }
        g_mod_nrecalc = 0;
        *c = save;
    }
    wrap_actrecalc_orig(c);
}
