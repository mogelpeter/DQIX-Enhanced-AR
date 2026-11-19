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
#define FORCE_SONG(w) ((w) >> 24)                          /* a boss's battle song (catalog.py boss_songs), 0 none */
static uint32_t g_force_song;                              /* the song of the battle forcebtl changed last, until it starts (wrap_forcebgm) */
extern uint32_t g_mod_legstat[4];                          /* mod_cheats.c: its stats this frame */

static uint32_t g_leg_mon, g_leg_level, g_leg_stat[4];     /* the legacy boss of the battle forcebtl changed last, 0 = none */

/* "Fully random encounters" (the Challenges page: mod_cheats.c g_mod_randenc, switch 02F5A618): when no monster is forced, every battle a
 * roaming monster starts is against other monsters: each of its groups (up to three kinds) becomes a kind picked at random from the ordinary
 * monsters of "Battle any monster you want" (the same 288, each of which loads and fights fine: catalog.py), keeping the group's count, never one the battle
 * before had. The pick hashes the frame number and the group, so every PC of a session picks the same. Bosses are never picked. */
extern uint32_t g_mod_randenc;
extern uint64_t g_frame;
static const uint16_t RAND_MONSTERS[] = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
    41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
    61, 62, 63, 64, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90,
    91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
    111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130,
    131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150,
    151, 152, 153, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173,
    174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193,
    194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 212, 213, 214, 215, 217,
    218, 220, 221, 222, 223, 224, 226, 228, 229, 230, 231, 232, 233, 235, 236, 237, 238, 239, 240, 241,
    242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261,
    262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281,
    282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 297, 298, 321, 323, 324,
    325, 327, 328, 329, 330, 331, 333, 334,
};
static uint32_t rand_pick(uint64_t x) {
    x += 0x9E3779B97F4A7C15ull; x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull; x = (x ^ (x >> 27)) * 0x94D049BB133111EBull; x ^= x >> 31;
    return RAND_MONSTERS[x % (sizeof RAND_MONSTERS / sizeof RAND_MONSTERS[0])];
}

/* "Fully random boss encounters" (the Challenges page: g_mod_randboss, switch 02F5A61C): every battle a roaming monster starts is against a boss
 * picked at random, alone, as "Battle any monster you want" makes a boss's battle (its song too: catalog.py boss_songs), never the one of the
 * battle before. The 55 bosses of that list (the story's, the grottos', the legacy bosses at their own level): monster, song. With "Fully random
 * encounters" on too, each battle is either (BOTH_BOSS_WEIGHT below); a monster chosen in "Battle any monster you want" goes before both. */
extern uint32_t g_mod_randboss;
static const uint16_t RAND_BOSSES[][2] = {
    { 216, 24 }, { 219, 24 }, { 225, 24 }, { 227, 24 }, { 234, 24 }, { 300, 24 }, { 301, 24 }, { 302, 24 },
    { 303, 24 }, { 304, 24 }, { 305, 24 }, { 306, 24 }, { 307, 24 }, { 308, 24 }, { 309, 24 }, { 310, 24 },
    { 311, 24 }, { 312, 24 }, { 313, 24 }, { 314, 24 }, { 315, 24 }, { 316, 24 }, { 317, 24 }, { 318, 24 },
    { 319, 24 }, { 320, 26 }, { 322, 24 }, { 326, 24 }, { 332, 24 }, { 335, 24 }, { 336, 24 }, { 337, 24 },
    { 338, 24 }, { 339, 24 }, { 340, 24 }, { 341, 24 }, { 342, 24 }, { 343, 24 }, { 344, 24 }, { 345, 24 },
    { 346, 24 }, { 347, 24 }, { 500, 27 }, { 501, 28 }, { 502, 29 }, { 503, 30 }, { 504, 31 }, { 505, 32 },
    { 506, 33 }, { 507, 34 }, { 508, 35 }, { 511, 36 }, { 512, 37 }, { 513, 38 }, { 514, 35 },
};
/* Both "Fully random" switches on: each battle is one or the other, drawn from the 288 ordinary monsters and the 55 bosses together, the
 * bosses counted twice (BOTH_BOSS_WEIGHT): about one battle in four a boss, the rest ordinary monsters. */
#define BOTH_BOSS_WEIGHT 2u
static uint32_t rand_hash(uint64_t x) {
    x += 0x9E3779B97F4A7C15ull; x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ull; x = (x ^ (x >> 27)) * 0x94D049BB133111EBull; x ^= x >> 31;
    return (uint32_t)(x ^ (x >> 32));
}

/* Bosses the game never fights alone (data/event/eventbattle.bin, the story's and the legacy grottos' boss battles with more than one group):
 * Mortamor with his two hands at each of his three levels (the hands of the band: 510/509, 778/776, 779/777), Hootingham-Gore with two bad
 * karmours. A forced or random battle against one of them is set up as the game's: {boss, group 1, group 3}, the boss in the middle group,
 * one of each. Only the boss gets a legacy level's stats (wrap_legacystats); the others are the game's own monsters for that band. */
static const uint16_t BOSS_PARTY[][3] = { { 508, 510, 509 }, { 639, 778, 776 }, { 641, 779, 777 }, { 314, 280, 280 } };
static int boss_party(uint32_t s, uint32_t mon) {
    for (unsigned k = 0; k < sizeof BOSS_PARTY / sizeof BOSS_PARTY[0]; k++) {
        if (BOSS_PARTY[k][0] != mon) continue;
        mem_write16(s + 4, BOSS_PARTY[k][1]); mem_write16(s + 6, (uint16_t)mon); mem_write16(s + 8, BOSS_PARTY[k][2]); mem_write16(s + 0xA, 0);
        mem_write8(s + 0xC, 1); mem_write8(s + 0xD, 1); mem_write8(s + 0xE, 1);
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: boss %u comes with %u and %u, as in the game\n", mon, BOSS_PARTY[k][1], BOSS_PARTY[k][2]);
        return 1;
    }
    return 0;
}

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
        if (want & FORCE_BOSS) boss_party(s, mon);
        g_force_song = (want & FORCE_BOSS) ? FORCE_SONG(want) : 0;
        g_leg_level = FORCE_LEVEL(want);
        g_leg_mon = g_leg_level && g_mod_legstat[0] ? mon : 0;
        memcpy(g_leg_stat, g_mod_legstat, sizeof g_leg_stat);
        if (g_leg_mon && getenv("DQIX_MODLOG"))
            fprintf(stderr, "mod: legacy boss %u at Lv %u: HP %u MP %u atk %u def %u agi %u gold %u exp %u\n", mon, g_leg_level,
                    g_leg_stat[0] & 0xFFFF, g_leg_stat[0] >> 16, g_leg_stat[1] & 0xFFFF, g_leg_stat[1] >> 16, g_leg_stat[2] & 0xFFFF,
                    g_leg_stat[2] >> 16, g_leg_stat[3]);
    } else {
        g_leg_mon = g_force_song = 0;                     /* another battle: not a forced legacy boss, its own music */
        int roam = !mon && c->r[14] == FIELD_BATTLE_RETURN && (int32_t)mem_read32(c->r[10] + 0x28) < 0;
        int boss = roam && g_mod_randboss;
        if (boss && g_mod_randenc) {                      /* both on: a boss or ordinary monsters, as the draw from all of them comes out */
            uint32_t nb = sizeof RAND_BOSSES / sizeof RAND_BOSSES[0], nm = sizeof RAND_MONSTERS / sizeof RAND_MONSTERS[0];
            boss = rand_hash(g_frame * 64 + 48) % (nb * BOTH_BOSS_WEIGHT + nm) < nb * BOTH_BOSS_WEIGHT;
        }
        if (boss) {
            static uint16_t last_boss;
            uint32_t s = c->r[1], nb = sizeof RAND_BOSSES / sizeof RAND_BOSSES[0], k = 0;
            for (unsigned t = 0; t < 8; t++) {
                k = rand_hash(g_frame * 64 + 32 + t) % nb;
                if (RAND_BOSSES[k][0] != last_boss) break;
            }
            if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: random boss encounter: %u becomes boss %u\n", mem_read16(s + 4), RAND_BOSSES[k][0]);
            mem_write16(s + 4, RAND_BOSSES[k][0]);
            mem_write16(s + 6, 0); mem_write16(s + 8, 0); mem_write16(s + 0xA, 0);
            mem_write8(s + 0xC, 1); mem_write8(s + 0xD, 0); mem_write8(s + 0xE, 0);
            boss_party(s, RAND_BOSSES[k][0]);
            g_force_song = RAND_BOSSES[k][1];
            last_boss = RAND_BOSSES[k][0];
        } else if (roam && g_mod_randenc) {
            uint32_t s = c->r[1];
            static uint16_t last[3];                          /* the previous random battle's: not again right away */
            uint16_t picked[3] = { 0, 0, 0 };
            for (unsigned j = 0; j < 3; j++) {
                uint16_t old = mem_read16(s + 4 + 2 * j);
                if (!old || !mem_read8(s + 0xC + j)) continue;
                uint16_t pick = 0;
                for (unsigned t = 0; t < 8; t++) {               /* three different kinds, as the game's own groups are */
                    pick = (uint16_t)rand_pick(g_frame * 64 + j * 8 + t);
                    if (pick != picked[0] && pick != picked[1] && pick != picked[2] && pick != last[0] && pick != last[1] && pick != last[2]) break;
                }
                picked[j] = pick;
                if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: random encounter: group %u, %u x%u becomes %u\n", j, old, mem_read8(s + 0xC + j), pick);
                mem_write16(s + 4 + 2 * j, pick);
            }
            mem_write16(s + 0xA, 0);
            memcpy(last, picked, sizeof last);
        }
    }
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
/* A main-module address in USA numbers -> this ROM's: the European ROM has 16 bytes more near the start of the main code (tools/region.py's EUR_SHIFTS).
 * Overlay and data addresses are the same in both. */
static uint32_t usa_main(uint32_t a) { return rom_is_eur() ? (a >= 0x0200FB20u && a < 0x020EEBD0u ? a + 0x10u : a >= 0x0200F3B8u && a < 0x0200FB20u ? a + 8u : a) : a; }
void wrap_legacylevel_orig(Cpu* c);
void wrap_legacylevel(Cpu* c) {
    uint32_t who = c->r[1], from = c->r[14];
    wrap_legacylevel_orig(c);
    if (!leg_active()) return;
    Cpu save = *c;
    dispatch_call(c, usa_main(GAME_GET_INSTANCE), from);
    c->r[1] = who;
    dispatch_call(c, usa_main(GAME_ENEMY_ENTRY), from);
    uint32_t e = c->r[0];
    *c = save;
    if (e && mem_read16(e + 2) == g_leg_mon) c->r[0] = g_leg_level;
}

/* The battle music. The field starts it after the battle is set up (ov017 021b6290, the field's way into a battle: main 0209c480 with the sound
 * manager 02109BF4 and the song, a sequence number of the sound archive, BG_<n>): 23, the usual battle song, or, for a story battle (the field's
 * battle number at +0xFE of that function's object, -1 for none), the song data/event/eventbattle.bin gives it: 24 a boss, 27..38 a legacy boss.
 * A field battle forcebtl made a boss's (above, before this: checked in a snapshot) plays that boss's song instead of the 23. Only that call, only
 * a field battle with the usual song, once. */
#define FIELD_SONG_RETURN 0x021B6444u                    /* the instruction after "bl func_0209c480" in func_ov017_021b6290 */
#define USUAL_BATTLE_SONG 23u
void wrap_forcebgm_orig(Cpu* c);
void wrap_forcebgm(Cpu* c) {
    if (g_force_song && c->r[14] == FIELD_SONG_RETURN && c->r[1] == USUAL_BATTLE_SONG && (int16_t)mem_read16(c->r[9] + 0xFE) < 0) {
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: battle song %u becomes %u (a forced boss)\n", c->r[1], g_force_song);
        c->r[1] = g_force_song;
    }
    if (c->r[14] == FIELD_SONG_RETURN) g_force_song = 0;
    wrap_forcebgm_orig(c);
}
