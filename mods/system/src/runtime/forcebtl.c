/* DQIX Enhanced mods: "Battle any monster you want", live (no restart).
 *
 * The choice is a live cheat (catalog.py, one entry per monster): while one is chosen, its code writes the monster's number to the switch
 * 02F5A5B4 every frame (mod_cheats.c g_mod_force; + 0x10000 for a boss). Live cheats travel in the player's input stream, so every PC of a
 * session has the same value on the same frame, and changing the choice takes effect at once.
 *
 * The roaming monsters stay those of the place (the encounter tables are read once, when the game starts, so they can't follow a live
 * choice; a boss can't roam anyway: 23 have no field model and none has roaming settings). What changes is the battle that touching one
 * starts. The field overlay starts it in func_ov017_021b7284: it fills an encounter record (3 species, a fourth value, 3 counts) either
 * from a fixed group (field + 0x28 >= 0: events, set battles) or from encbtl.bin (field + 0x28 < 0: a roaming monster was touched), copies
 * it into a battle start block (species at +4, +6, +8, the fourth value at +0xA, counts at +0xC, +0xD, +0xE) and hands that to
 * func_ov000_0215d414 at 021b7550 (the Action Replay code "Wild Enemy Modifier" changes the same place). That call is wrapped (wrap.txt,
 * "ov000 0215d414 forcebtl"): when it comes from there (return address 021b7554) for a touched roamer, the block becomes the chosen monster,
 * as many as the group had (a boss: one). Every other battle, story bosses and set battles included, is left alone.
 *
 * Legacy bosses at a level (catalog.py: "Dragonlord, legacy Lv 50 (boss)" and Lv 99). In a legacy boss grotto the game makes the boss its map's
 * level like this (DetailedTreasureMapData, main 020a4100..020a5b08):
 *  - the boss is one of three monsters by level: Lv 1..15 the base one (Dragonlord 500), 16..40 a second (600), 41..99 a third (601);
 *    data/tmap/tdata.gp2 lists them, data/tmap/param.pac p_<base>.dat has a 24-byte row per level whose byte 0x0E says which;
 *  - the row's HP, MP, attack, defense, agility, EXP and gold go onto that monster's record as the battle loads its monsters
 *    (ov000 02165c68..02165cec), only in a grotto (main 0201b5d8: the place is one of 0xA08D..0xA221) and for a legacy map;
 *  - the enemy's level (ov000 02159dbc) is the map's, for the same monster in the same grotto; else the monster record's own.
 * A forced fight is in the field, so the game does neither. The entry forces the third monster (catalog.py picks it by the level), writes the
 * row's stats to 02F5A600.. and the level to bits 17..23 of the choice (mod_cheats.c). wrap_forcebtl keeps them for the battle it changes
 * (g_leg_*, cleared by the next battle that isn't one), and two more wraps do what the grotto does:
 *  - "main 0201b5d8 legacystats": at the grotto check in the monster loading loop (return address 02165c78; r6 = the monster's record,
 *    r9 = its slot, sp + 0x44 = the slots' monster numbers) the record of the forced boss gets the stats, and the check answers "not a grotto"
 *    so the game's own legacy copy (from the map you last opened) is skipped for it;
 *  - "ov000 02159dbc legacylevel": the forced boss's level is the chosen one.
 * Moves a legacy boss learns by level (the end of p_<base>.dat; Dragonlord: Disruptive Wave at 57) are only held back in a grotto: in a forced
 * fight the boss may use all of them, as at Lv 99.
 *
 * DQIX_MODLOG=1 prints each battle that is changed.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cpu.h"
#include "nds.h"

void wrap_forcebtl_orig(Cpu* c);
extern uint32_t g_mod_force;                              /* mod_cheats.c: this frame's choice, 0 = none */

#define FIELD_BATTLE_RETURN 0x021B7554u              /* the instruction after "bl func_ov000_0215d414" in func_ov017_021b7284 */
#define FORCE_BOSS 0x10000u
#define FORCE_LEVEL(w) (((w) >> 17) & 0x7Fu)               /* a legacy boss entry's level, 0 for the others */
extern uint32_t g_mod_legstat[4];                          /* mod_cheats.c: its stats this frame */

static uint32_t g_leg_mon, g_leg_level, g_leg_stat[4];     /* the legacy boss of the battle forcebtl changed last, 0 = none */

void wrap_forcebtl(Cpu* c) {
    uint32_t want = g_mod_force, mon = want & 0xFFFu;
    if (mon && c->r[14] == FIELD_BATTLE_RETURN && (int32_t)mem_read32(c->r[10] + 0x28) < 0) {
        uint32_t s = c->r[1];                             /* the battle start block */
        unsigned n = (want & FORCE_BOSS) ? 1u : (unsigned)mem_read8(s + 0xC) + mem_read8(s + 0xD) + mem_read8(s + 0xE);
        if (n < 1) n = 1;
        if (getenv("DQIX_MODLOG"))
            fprintf(stderr, "mod: field battle %u x%u, %u x%u, %u x%u becomes %u x%u\n", mem_read16(s + 4), mem_read8(s + 0xC),
                    mem_read16(s + 6), mem_read8(s + 0xD), mem_read16(s + 8), mem_read8(s + 0xE), mon, n);
        mem_write16(s + 4, (uint16_t)mon);
        mem_write16(s + 6, 0);
        mem_write16(s + 8, 0);
        mem_write16(s + 0xA, 0);
        mem_write8(s + 0xC, (uint8_t)n);
        mem_write8(s + 0xD, 0);
        mem_write8(s + 0xE, 0);
        g_leg_level = FORCE_LEVEL(want);
        g_leg_mon = g_leg_level && g_mod_legstat[0] ? mon : 0;
        memcpy(g_leg_stat, g_mod_legstat, sizeof g_leg_stat);
        if (g_leg_mon && getenv("DQIX_MODLOG"))
            fprintf(stderr, "mod: legacy boss %u at Lv %u: HP %u MP %u atk %u def %u agi %u gold %u exp %u\n", mon, g_leg_level,
                    g_leg_stat[0] & 0xFFFF, g_leg_stat[0] >> 16, g_leg_stat[1] & 0xFFFF, g_leg_stat[1] >> 16, g_leg_stat[2] & 0xFFFF,
                    g_leg_stat[2] >> 16, g_leg_stat[3]);
    } else g_leg_mon = 0;                                 /* another battle: not a forced legacy boss */
    wrap_forcebtl_orig(c);
}

/* the latch counts only while that entry is still the choice: a battle that didn't go through wrap_forcebtl can't pick it up later */
static int leg_active(void) { return g_leg_mon && (g_mod_force & 0xFFFu) == g_leg_mon && FORCE_LEVEL(g_mod_force) == g_leg_level; }

/* fn_main_0201b5d8 "is location r0 a grotto", wrapped (wrap.txt "main 0201b5d8 legacystats") */
#define LOAD_MONSTERS_GROTTO_CHECK 0x02165C78u            /* ov000: the return address of that call in the monster loading loop */
void wrap_legacystats_orig(Cpu* c);
void wrap_legacystats(Cpu* c) {
    if (leg_active() && c->r[14] == LOAD_MONSTERS_GROTTO_CHECK
        && mem_read16(c->r[13] + 0x44 + 2 * c->r[9]) == g_leg_mon && c->r[6]) {
        uint32_t r = c->r[6];                             /* the monster's record: what ov000 02165cb4..02165cec writes */
        mem_write16(r + 0x5C, (uint16_t)g_leg_stat[0]);           /* HP */
        mem_write16(r + 0x5E, (uint16_t)(g_leg_stat[0] >> 16));   /* MP */
        mem_write16(r + 0x64, (uint16_t)g_leg_stat[1]);           /* attack */
        mem_write16(r + 0x60, (uint16_t)(g_leg_stat[1] >> 16));   /* defense */
        mem_write16(r + 0x62, (uint16_t)g_leg_stat[2]);           /* agility */
        mem_write32(r + 0x08, g_leg_stat[3]);                     /* EXP */
        mem_write16(r + 0x0C, (uint16_t)(g_leg_stat[2] >> 16));   /* gold */
        c->r[0] = 0;                                      /* "not a grotto": the game's own copy is skipped for this one */
        return;
    }
    wrap_legacystats_orig(c);
}

/* func_ov000_02159dbc "the level of enemy r1", wrapped (wrap.txt "ov000 02159dbc legacylevel") */
#define GAME_GET_INSTANCE 0x0200F398u                      /* GameState::GetInstance */
#define GAME_ENEMY_ENTRY  0x0200FEA4u                      /* (instance, r1) -> the entry whose +2 is the monster number, as 02159dbc does */
void wrap_legacylevel_orig(Cpu* c);
void wrap_legacylevel(Cpu* c) {
    uint32_t who = c->r[1], from = c->r[14];
    wrap_legacylevel_orig(c);
    if (!leg_active()) return;
    Cpu save = *c;
    dispatch_call(c, GAME_GET_INSTANCE, from);
    c->r[1] = who;
    dispatch_call(c, GAME_ENEMY_ENTRY, from);
    uint32_t e = c->r[0];
    *c = save;
    if (e && mem_read16(e + 2) == g_leg_mon) c->r[0] = g_leg_level;
}
