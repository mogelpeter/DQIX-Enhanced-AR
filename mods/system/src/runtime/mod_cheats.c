/* DQIX Enhanced mods: live cheats inside the game, so they also work while
 * playing with friends.
 *
 * This file belongs to the mods folder. mods/system/tools/apply_runtime_mod.py copies
 * it (and ar_engine.h) into runtime/, where the build picks it up by itself,
 * and adds one call in runtime/input.c.
 *
 * Why it has to be inside the game: in a session every PC runs every player's
 * DS and they must all compute exactly the same (session.h). A cheat written
 * into one PC's memory from outside makes that PC differ, and the session goes
 * out of sync. So here a cheat travels the way the buttons do: the cheat
 * window (mod_cheatwin.c) puts it in a mailbox, this console sends it in
 * its own input stream, 16 bits per frame, and every copy of this console - the
 * player's own and the hidden ones on the friends' PCs - carries it out at the
 * same frame. The friends need this file in their game too (the same mods
 * folder), but not the same cheat files: the codes themselves are sent.
 *
 * An input word (session_pack) uses bits 0-12 for the buttons, 13 for the
 * stylus and 14-29 for where it is. A frame with bit 30 set carries 16 bits of
 * a cheat message in 14-29 instead (the stylus is up for that frame).
 *
 * Message: a header word, type << 12 | number of words that follow, then
 *   1 RUN    ops                 run the code once (as if its keys are held)
 *   2 SET    id, ops             run it every frame from now on, as cheat `id`; a code that
 *                                waits for buttons ("press SELECT") sees this console's own
 *   3 CLEAR  id                  stop cheat `id`
 *   4 CLEAR_ALL
 *   5 SET_UNDO id, ops             as SET, and when the cheat is switched off again, every byte it wrote that still holds what
 *                                it wrote gets its value from before back (big head, hidden party: the game itself would
 *                                only put those back at the next battle or map change)
 * with each op as four words (address low, high, value low, high).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "nds.h"
#include "session.h"
#include "ar_engine.h"
#ifdef _WIN32
#include <windows.h>
#endif

#define MC_MAGIC   0x43584451u         /* "DQXC" */
#define MC_VERSION 4                   /* 2: codes that are on see the buttons; 128 at a time. 3: B reads [address + offset]. 4: SET_UNDO */
#define MC_RING    8192
#define MC_EVENT   (1u << 30)
#define MC_SLOTS   128
#define MC_MAXLEN  0xFFF

/* the mailbox, shared with the cheat window (the same in mod_cheatwin.c) */
typedef struct {
    uint32_t magic, version;
    volatile uint32_t wr;              /* the window: words written */
    volatile uint32_t rd;              /* the game: words sent */
    volatile uint32_t gen;             /* the game: goes up when it has forgotten every cheat (started, reset,
                                          a session began or ended): the window sends them again */
    volatile uint32_t session;         /* playing with friends now */
    volatile uint32_t done;            /* messages carried out */
    volatile uint32_t frame;
    uint16_t ring[MC_RING];
} McBox;

static McBox* g_box;

#ifdef _WIN32
/* Made when the program starts, so the cheat window knows from the first
 * moment that this game takes its cheats here. Only the program itself has
 * one: the other players' consoles (copies of dqixcore.dll in this process)
 * only listen to their own input streams. */
__attribute__((constructor)) static void mc_start(void) {
    HMODULE me = NULL;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)(void*)&mc_start, &me)) return;
    if (me != GetModuleHandleA(NULL)) return;
    char name[64]; snprintf(name, sizeof name, "Local\\dqix-mod-cheats-%lu", (unsigned long)GetCurrentProcessId());
    HANDLE h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(McBox), name);
    if (!h) return;
    McBox* b = (McBox*)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(McBox));
    if (!b) { CloseHandle(h); return; }
    memset(b, 0, sizeof *b);
    b->version = MC_VERSION; b->magic = MC_MAGIC;
    g_box = b;
    {   /* the Cheats window inside the emulator (mod_cheatwin.c): its options for this start, and the thread that sends the cheats that are on */
        void mod_cheatwin_boot(void);
        mod_cheatwin_boot();
    }
}
#endif

/* The in-emulator Cheats window (mod_cheatwin.c, its own thread) puts messages into the same ring the external cheat
 * window used. One producer at a time (mod_cheatwin.c holds a lock); returns 0 when there is no room or no mailbox. */
int mod_cheats_post(const uint16_t* w, int n) {
    if (!g_box || n <= 0) return 0;
    uint32_t wr = g_box->wr;
    if (wr - g_box->rd + (uint32_t)n > MC_RING - 8) return 0;
    for (int i = 0; i < n; i++) g_box->ring[(wr + (uint32_t)i) % MC_RING] = w[i];
#ifdef _WIN32
    MemoryBarrier();
#endif
    g_box->wr = wr + (uint32_t)n;
    return 1;
}

/* Who is really there, for the Cheats window (mod_cheatwin.c): the party members (their record, with the name, is at 0x020F54B4 - i * 0x964; a
 * battle fills the battle copy at +0x58 on) and, in a battle, the enemies (HP at 0x022A4638 + n * 0xA4). Read from this console's own memory,
 * only for display: the cheats themselves still travel through the mailbox. */
typedef struct { int inbattle; uint8_t party[4], enemy[6]; char name[4][12]; int enemy_hp[6]; int hp[4], mp[4], hpmax[4], mpmax[4], enemy_max_hp[6], enemy_max_mp[6]; } ModRoster;
int mod_in_party(int i);                                       /* nuzlocke.c */
static uint16_t ram16(uint32_t a) { uint16_t v; memcpy(&v, &g_main_ram[a & (MAIN_RAM_SIZE - 1)], 2); return v; }
void mod_roster(ModRoster* r) {
    static int hpseen[4], mpseen[4];                           /* the most HP / MP a member had in this battle (the record has no maximum to read) */
    memset(r, 0, sizeof *r);
    for (int i = 0; i < 4; i++) {
        uint32_t b = (0x020F54B4u - (uint32_t)i * 0x964u) & (MAIN_RAM_SIZE - 1);
        if (!g_main_ram[b] || !mod_in_party(i)) continue;
        r->party[i] = 1;
        int k = 0; for (; k < 10 && g_main_ram[b + (uint32_t)k] >= 32 && g_main_ram[b + (uint32_t)k] < 127; k++) r->name[i][k] = (char)g_main_ram[b + (uint32_t)k];
        r->name[i][k] = 0;
    }
    /* the battle copy of a member's record (found by writing each field in a real fight and looking at the screen): +0x58 = HP now (what the card on the
     * DS screen shows; 0 = fallen), +0x5A = MP now, +0x5C = maximum HP, +0x5E = maximum MP. They are nonzero only during a battle (a fallen hero has +0x58 = 0, so the
     * battle is told by the maximum). Outside a battle +0x30 / +0x32 are HP and MP; the maximum isn't stored there (only what was seen is known). */
    for (int i = 0; i < 4; i++) if (r->party[i] && ram16(0x020F54B4u - (uint32_t)i * 0x964u + 0x5Cu)) r->inbattle = 1;
    for (int i = 0; i < 4; i++) {
        uint32_t b = 0x020F54B4u - (uint32_t)i * 0x964u;
        if (!r->party[i]) { hpseen[i] = mpseen[i] = 0; continue; }
        if (r->inbattle) {
            r->hp[i] = ram16(b + 0x58); r->mp[i] = ram16(b + 0x5A); r->hpmax[i] = ram16(b + 0x5C); r->mpmax[i] = ram16(b + 0x5E);
            hpseen[i] = (int)r->hpmax[i]; mpseen[i] = (int)r->mpmax[i];
            continue;
        }
        r->hp[i] = ram16(b + 0x30); r->mp[i] = ram16(b + 0x32);
        hpseen[i] = r->hp[i]; mpseen[i] = r->mp[i];
        r->hpmax[i] = hpseen[i]; r->mpmax[i] = mpseen[i];
    }
    if (r->inbattle)
        for (int n = 0; n < 6; n++) {
            uint32_t e = 0x022A4638u + (uint32_t)n * 0xA4u;
            uint16_t hp = ram16(e);
            r->enemy_hp[n] = hp; r->enemy[n] = hp > 0;
            r->enemy_max_hp[n] = ram16(e + 4); r->enemy_max_mp[n] = ram16(e + 6);         /* the enemy record: HP +0, MP +2, maximum HP +4, maximum MP +6 (+8 / +10 are the species' field values) */
        }
}

/* goes up whenever this console forgot every cheat (started, reset, a session began or ended): the window sends them again */
uint32_t mod_cheats_gen(void) { return g_box ? g_box->gen : 0; }

/* ---- the DS's memory, for the code interpreter ---- */
static int mc_read(void* u, uint32_t a, void* out, size_t n) {
    (void)u; a &= MAIN_RAM_SIZE - 1;
    if (a + n > MAIN_RAM_SIZE) return 0;
    memcpy(out, &g_main_ram[a], n); return 1;
}
/* A switch, not memory: a code that writes this address (mods/system/cheats/lower-level-more-exp.txt)
 * turns "lower-level characters get more experience" on for this frame (lowexp.c reads it).
 * It is cleared at the start of every frame and set again by the code while that is on, so it
 * is the same on every PC of a session. */
uint8_t g_mod_lowexp;
#define MC_SWITCH_LOWEXP 0x02F5A5A0u
/* More switches of the same kind (mods/system/cheats/vanish.txt, metal-slimes-only.txt):
 *   vanish  on for this frame while the cheat is on (the Cheats window's Vanish button switches the cheat on and off). While it is on,
 *           vanish.c makes the field's "did a monster touch you" check find nothing, so you walk through monsters. */
uint8_t g_mod_vanish;
#define MC_SWITCH_VANISH 0x02F5A5A4u
/* "Monsters can't flee" (mods/system/cheats/monsters-cant-flee.txt): on for this frame while the code is on; noflee.c reads it. */
uint8_t g_mod_noflee;
#define MC_SWITCH_NOFLEE 0x02F5A5A8u
/* "Always strike first" (mods/system/cheats/first-strike.txt): on for this frame while the code is on; firststrike.c reads it. */
uint8_t g_mod_first;
#define MC_SWITCH_FIRST 0x02F5A5ACu
/* "Revive" (mods/system/cheats/revive.txt and the battle window's Revive buttons): a write to 02F5A5B0 carries it out once on this console's party. The
 * value is 0 for every fallen member or 1..4 for that one. A fallen member has HP 0; in a battle his HP now (+0x58) becomes his maximum (+0x5C) and the
 * HP outside (+0x30) too; outside a battle +0x30 becomes the highest HP this member was seen with (g_hpmax, kept every frame), or 1 if he never was. */
#define MC_SWITCH_REVIVE 0x02F5A5B0u
/* "Battle any monster you want" (catalog.py, one choice per monster): a write of n to 02F5A5B4 says "the battles a roaming monster starts are
 * monster n" for this frame (n | 0x10000: a boss, one of it); forcebtl.c reads it. Live like the switches above: no restart, the same on every PC. */
uint32_t g_mod_force;
#define MC_SWITCH_FORCE 0x02F5A5B4u
/* Its legacy boss entries ("Dragonlord, legacy Lv 99 (boss)") also say the level in bits 17..23 of that value, and write the level's stats
 * (data/tmap/param.pac, the row the game itself uses in a legacy boss grotto) to 02F5A600..02F5A60F: HP | MP << 16, attack | defense << 16,
 * agility | gold << 16, EXP. forcebtl.c puts them on the boss. */
uint32_t g_mod_legstat[4];
#define MC_SWITCH_LEGSTAT 0x02F5A600u
static uint16_t g_hpmax[4];
static void mc_track_hp(void) {                                    /* every frame: the highest HP each member was seen with */
    for (int i = 0; i < 4; i++) {
        uint32_t b = (0x020F54B4u - (uint32_t)i * 0x964u) & (MAIN_RAM_SIZE - 1);
        if (!g_main_ram[b] || !mod_in_party(i)) { g_hpmax[i] = 0; continue; }
        uint16_t bm, f; memcpy(&bm, &g_main_ram[b + 0x5C], 2); memcpy(&f, &g_main_ram[b + 0x30], 2);
        if (bm) g_hpmax[i] = bm; else if (f > g_hpmax[i]) g_hpmax[i] = f;
    }
}
static void mc_revive(uint32_t who) {
    for (int i = 0; i < 4; i++) {
        if (who && who != (uint32_t)i + 1) continue;
        uint32_t b = (0x020F54B4u - (uint32_t)i * 0x964u) & (MAIN_RAM_SIZE - 1);
        if (!g_main_ram[b] || !mod_in_party(i)) continue;
        uint16_t bm, cur, f; memcpy(&bm, &g_main_ram[b + 0x5C], 2); memcpy(&cur, &g_main_ram[b + 0x58], 2); memcpy(&f, &g_main_ram[b + 0x30], 2);
        if (bm) {                                                   /* in a battle */
            if (cur) continue;
            memcpy(&g_main_ram[b + 0x58], &bm, 2); memcpy(&g_main_ram[b + 0x30], &bm, 2);
        } else {
            if (f) continue;
            uint16_t v = g_hpmax[i] ? g_hpmax[i] : 1; memcpy(&g_main_ram[b + 0x30], &v, 2);
        }
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: revive party member %d at frame %llu\n", i + 1, (unsigned long long)g_frame);
    }
}
/* "Always high tension" and "Coup de Grace always ready" (catalog.py: the battle window's cards and the Battle page): a write to 02F5A5B8 (tension) or
 * 02F5A5BC (Coup de Grace) this frame, bit i = party member i + 1. mc_battle_locks does it after the cheats ran, the way the game itself does it, for a
 * member who is in a battle and up. Their battle copy is at record + 0x58 (HP now +0, maximum HP +4):
 *  - tension: the level is at +0x24 (0..4, 4 = 100) and its aura in the word at +0x14 (0x00800000 levels 1..3, 0x01000000 the top). main 0208810c
 *    says whether a member may go to the top (not with 0x1, 0x8, 0x10 or 0x80000 in that word: down, or a status that stops it), main 02088150 puts
 *    them there: 0x00800000 and 0x2 off, bits 0..1 of the halfword at +0x22 off, 0x01000000 on, level 4. The R4 code wrote 1 over the word's top
 *    byte (the other flags in it went too) and left 0x00800000 on;
 *  - Coup de Grace: the byte at +0x3B. 0x08 = ready: the battle menu offers it (ov000 0217ae90) and draws its text lit, not grey, only with it
 *    (ov000 0217653c: grey is main 02041e70); its high four bits are the rounds it stays ready (one off each round, at 0 the game clears 0x08:
 *    ov000 021581fc). Kept at "ready, 9 rounds" (what the R4 codes write, 0x98), with the low three bits (the game's own flags) left as they are.
 *    The old "Can always use Coup de Grace" skipped the menu's check instead (ov000 0217b2c4), so the game never knew: the text stayed grey. */
static uint32_t g_mod_tension, g_mod_coup;
/* "Always 4-hit combo" (catalog.py, Battle page): 02F5A624, the party members (bits 0..3) whose every hit counts as the fourth of a combo
 * (challenges.c wrap_toughdmg). Set again each frame by its code, like the two above. */
uint32_t g_mod_combo;
#define MC_SWITCH_COMBO 0x02F5A624u
#define MC_SWITCH_TENSION 0x02F5A5B8u
#define MC_SWITCH_COUP 0x02F5A5BCu
static void mc_battle_locks(void) {
    for (int i = 0; i < 4; i++) {
        uint32_t bit = 1u << i;
        if (!((g_mod_tension | g_mod_coup) & bit)) continue;
        uint32_t b = (0x020F54B4u - (uint32_t)i * 0x964u) & (MAIN_RAM_SIZE - 1);
        if (!g_main_ram[b] || !mod_in_party(i)) continue;
        uint8_t* s = &g_main_ram[b + 0x58];
        uint16_t hp, hpmax; memcpy(&hp, s, 2); memcpy(&hpmax, s + 4, 2);
        if (!hpmax || !hp) continue;                                  /* not in a battle, or down */
        if (g_mod_tension & bit) {
            uint32_t w; memcpy(&w, s + 0x14, 4);
            if (!(w & 0x00080019u) && (s[0x24] != 4 || !(w & 0x01000000u))) {
                w = (w & ~0x00800002u) | 0x01000000u; memcpy(s + 0x14, &w, 4);
                uint16_t h; memcpy(&h, s + 0x22, 2); h &= (uint16_t)~3u; memcpy(s + 0x22, &h, 2);
                s[0x24] = 4;
            }
        }
        if (g_mod_coup & bit) s[0x3B] = (uint8_t)((s[0x3B] & 0x07) | 0x98);
    }
}
/* The Challenges page (catalog.py CHALLENGE_*): switches written every frame while an entry is on, done after the cheats ran.
 *  02F5A610 tougher monsters: the value is the multiplier in halves (3 = x1.5, 4 = x2, 6 = x3). Here: every monster's HP and maximum HP, once,
 *           when it shows up (the game's fighter list: game object 020F33D8 + 8 + index * 4, a fighter has 0x80 in its first halfword, a
 *           monster also 0x400, +0x138 its battle stats: HP +0, maximum +4; checked in a battle snapshot). HP isn't worked out again from the
 *           monster's data during a battle, so that holds; a monster that changes form (a new maximum) is done again. challenges.c does the
 *           damage they deal.
 *  02F5A614 no spells: every party member in a battle is kept under Fizzle, the way the game casts it (main 020888a4: +0x60 = 6, +0x83 = 0,
 *           0x100 in the word at +0x14 of their battle copy, record + 0x58): the game refuses their spells itself ("...can't cast spells at the
 *           moment"). Abilities, items and attacks still work.
 *  02F5A618 fully random encounters: forcebtl.c gives every battle a roaming monster starts other monsters, picked at random each time.
 *  02F5A61C fully random boss encounters: the same, but a boss, alone, with its own music. */
uint32_t g_mod_tough, g_mod_randenc, g_mod_randboss;
static uint32_t g_mod_nospell;
#define MC_SWITCH_TOUGH 0x02F5A610u
#define MC_SWITCH_NOSPELL 0x02F5A614u
#define MC_SWITCH_RANDENC 0x02F5A618u
#define MC_SWITCH_RANDBOSS 0x02F5A61Cu
static uint32_t g_tough_st[24]; static uint16_t g_tough_max[24], g_tough_mon[24];   /* the monsters done: battle stats, the maximum HP they got, which monster */
static uint32_t mc_r32(uint32_t a) { uint32_t v; memcpy(&v, &g_main_ram[a & (MAIN_RAM_SIZE - 1)], 4); return v; }
static uint16_t mc_r16(uint32_t a) { uint16_t v; memcpy(&v, &g_main_ram[a & (MAIN_RAM_SIZE - 1)], 2); return v; }
static void mc_w16(uint32_t a, uint16_t v) { memcpy(&g_main_ram[a & (MAIN_RAM_SIZE - 1)], &v, 2); }
static int mc_in_ram(uint32_t a) { return a >= 0x02000000u && a < 0x02000000u + MAIN_RAM_SIZE - 0x200u; }
static void mc_challenges(void) {
    if (g_mod_tough >= 3) {
        uint32_t seen[24]; uint16_t seenmax[24], seenmon[24]; int ns = 0;
        for (uint32_t i = 0; i < 0xE9 && ns < 24; i++) {
            uint32_t e = mc_r32(0x020F33D8u + 8 + 4 * i);
            if (!mc_in_ram(e)) continue;
            uint16_t fl = mc_r16(e);
            if ((fl & 0x480) != 0x480) continue;                 /* a fighter and a monster */
            uint32_t st = mc_r32(e + 0x138);
            if (!mc_in_ram(st)) continue;
            uint16_t mx = mc_r16(st + 4), mon = mc_r16(e + 2);
            if (!mx) continue;
            int k = 0; while (k < 24 && g_tough_st[k] != st) k++;
            if (k < 24 && g_tough_max[k] == mx && g_tough_mon[k] == mon) { seen[ns] = st; seenmon[ns] = mon; seenmax[ns++] = mx; continue; }   /* done */
            uint32_t nmx = (uint32_t)mx * g_mod_tough / 2, hp = (uint32_t)mc_r16(st) * g_mod_tough / 2;
            if (nmx > 65535) nmx = 65535;
            if (hp > nmx) hp = nmx;
            mc_w16(st + 4, (uint16_t)nmx); mc_w16(st, (uint16_t)hp);
            seen[ns] = st; seenmon[ns] = mon; seenmax[ns++] = (uint16_t)nmx;
        }
        memset(g_tough_st, 0, sizeof g_tough_st); memcpy(g_tough_st, seen, ns * sizeof seen[0]);
        memcpy(g_tough_max, seenmax, ns * sizeof seenmax[0]); memcpy(g_tough_mon, seenmon, ns * sizeof seenmon[0]);
    } else memset(g_tough_st, 0, sizeof g_tough_st);
    if (g_mod_nospell)
        for (int i = 0; i < 4; i++) {
            uint32_t b = (0x020F54B4u - (uint32_t)i * 0x964u) & (MAIN_RAM_SIZE - 1);
            if (!g_main_ram[b] || !mod_in_party(i)) continue;
            uint8_t* s = &g_main_ram[b + 0x58];
            uint16_t mx; memcpy(&mx, s + 4, 2);
            if (!mx) continue;                                    /* not in a battle */
            uint32_t w; memcpy(&w, s + 0x14, 4);
            w |= 0x100u; memcpy(s + 0x14, &w, 4);
            s[0x60] = 6; s[0x83] = 0;                             /* it never wears off */
        }
}
/* "All buffs" / "All debuffs" (catalog.py buff_entries): their code also writes the fighter's battle stats address to 02F5A620. The game keeps
 * attack, defence, agility and the rest as numbers worked out from the base and the effect levels, and works them out again only when something
 * is cast on a fighter or at the end of its own action, so levels written by a cheat did nothing until then. Kept here (not cleared each frame)
 * until challenges.c has the game work them out again, at the start of the next action. */
uint32_t g_mod_recalc[16]; int g_mod_nrecalc;
#define MC_SWITCH_RECALC 0x02F5A620u
/* The Nuzlocke rules (nuzlocke.c): a write to 02F5A5C0 + 4n switches rule n on for this frame (bit n of g_mod_nz); the write to 02F5A5FC is the
 * one-off command "start a new run". */
uint32_t g_mod_nz;
void nz_frame(uint32_t flags, int session);
void nz_command(int cmd);
void nz_reset(void);
#define MC_SWITCH_NZ 0x02F5A5C0u
#define MC_SWITCH_NZ_NEW 0x02F5A5FCu
/* Code mods that run live (livepatch.c): a write to 02F60000 + 4n says "instruction site n is patched with this word" this frame. */
int lp_set(uint32_t addr, uint32_t word);
void lp_clear(void);
#define MC_LP_BASE 0x02F60000u
static uint8_t g_vanish_armed, g_vanish_prev;

/* the undo journal of the cheat running now (SET_UNDO): each byte it wrote, what was there before and what it wrote last */
typedef struct { uint32_t a; uint8_t orig, last; } McUndo;
typedef struct { McUndo* u; int n, cap; } McJournal;
#define MC_UNDO_MAX 8192
static McJournal* g_journal;

static void mc_note(uint32_t a, const uint8_t* in, size_t n) {
    McJournal* j = g_journal;
    for (size_t i = 0; i < n; i++) {
        uint32_t x = (a + (uint32_t)i) & (MAIN_RAM_SIZE - 1); int k;
        for (k = j->n - 1; k >= 0; k--) if (j->u[k].a == x) break;
        if (k >= 0) { j->u[k].last = in[i]; continue; }
        if (j->n >= MC_UNDO_MAX) continue;
        if (j->n == j->cap) {
            int cap = j->cap ? j->cap * 2 : 64; McUndo* nu = (McUndo*)realloc(j->u, (size_t)cap * sizeof *nu);
            if (!nu) continue;
            j->u = nu; j->cap = cap;
        }
        j->u[j->n].a = x; j->u[j->n].orig = g_main_ram[x]; j->u[j->n].last = in[i]; j->n++;
    }
}

/* the cheat is switched off: a byte that still holds what the cheat wrote gets its old value back; one the game has changed
 * since (or that now belongs to something else) is left alone */
static void mc_undo(McJournal* j) {
    for (int k = j->n - 1; k >= 0; k--) if (g_main_ram[j->u[k].a] == j->u[k].last) g_main_ram[j->u[k].a] = j->u[k].orig;
    free(j->u); memset(j, 0, sizeof *j);
}

static int mc_write(void* u, uint32_t a, const void* in, size_t n) {
    (void)u;
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_LOWEXP) { g_mod_lowexp = 1; return 1; }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_VANISH) { g_vanish_armed = 1; return 1; }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_NOFLEE) { g_mod_noflee = 1; return 1; }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_FIRST) { g_mod_first = 1; return 1; }
    if ((a & 0x0FFFFFFFu) >= MC_SWITCH_LEGSTAT && (a & 0x0FFFFFFFu) < MC_SWITCH_LEGSTAT + 16) {
        uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); g_mod_legstat[((a & 0x0FFFFFFFu) - MC_SWITCH_LEGSTAT) >> 2] = w; return 1;
    }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_FORCE) { uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); else if (n == 2) { uint16_t h; memcpy(&h, in, 2); w = h; } g_mod_force = w; return 1; }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_RECALC) {
        uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4);
        int k = 0; while (k < g_mod_nrecalc && g_mod_recalc[k] != w) k++;
        if (w && k == g_mod_nrecalc && g_mod_nrecalc < 16) g_mod_recalc[g_mod_nrecalc++] = w;
        return 1;
    }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_TOUGH || (a & 0x0FFFFFFFu) == MC_SWITCH_NOSPELL || (a & 0x0FFFFFFFu) == MC_SWITCH_RANDENC
        || (a & 0x0FFFFFFFu) == MC_SWITCH_RANDBOSS) {
        uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); else if (n == 2) { uint16_t h; memcpy(&h, in, 2); w = h; } else if (n == 1) w = *(const uint8_t*)in;
        if ((a & 0x0FFFFFFFu) == MC_SWITCH_TOUGH) g_mod_tough = w; else if ((a & 0x0FFFFFFFu) == MC_SWITCH_NOSPELL) g_mod_nospell = w;
        else if ((a & 0x0FFFFFFFu) == MC_SWITCH_RANDENC) g_mod_randenc = w; else g_mod_randboss = w;
        return 1;
    }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_COMBO) {
        uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); else if (n == 2) { uint16_t h; memcpy(&h, in, 2); w = h; } else if (n == 1) w = *(const uint8_t*)in;
        g_mod_combo |= w & 0xF;
        return 1;
    }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_TENSION || (a & 0x0FFFFFFFu) == MC_SWITCH_COUP) {
        uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); else if (n == 2) { uint16_t h; memcpy(&h, in, 2); w = h; } else if (n == 1) w = *(const uint8_t*)in;
        if ((a & 0x0FFFFFFFu) == MC_SWITCH_TENSION) g_mod_tension |= w & 0xF; else g_mod_coup |= w & 0xF;
        return 1;
    }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_REVIVE) { uint32_t w = 0; if (n >= 4) memcpy(&w, in, 4); mc_revive(w); return 1; }
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_NZ_NEW) { nz_command(1); return 1; }
    if ((a & 0x0FFFFFFFu) >= MC_SWITCH_NZ && (a & 0x0FFFFFFFu) < MC_SWITCH_NZ + 0x3C) { g_mod_nz |= 1u << (((a & 0x0FFFFFFFu) - MC_SWITCH_NZ) >> 2); return 1; }
    if (n == 4 && (a & 0x0FFFFFFFu) >= MC_LP_BASE && (a & 0x0FFFFFFFu) < MC_LP_BASE + 0x10000u) { uint32_t w; memcpy(&w, in, 4);
        if (w == 0xE3A00FFFu) w = (g_frame & 1) ? 0xE3A00003u : 0xE3A00002u;     /* movement speed x1.25: the game's speed is a whole number of half steps (x1 = 2, x1.5 = 3), so it alternates 2 and 3 every frame: 2.5 on average = x1.25 */
        return lp_set(a & 0x0FFFFFFFu, w); }
    a &= MAIN_RAM_SIZE - 1;
    if (a + n > MAIN_RAM_SIZE) return 0;
    if (g_journal) mc_note(a, (const uint8_t*)in, n);
    memcpy(&g_main_ram[a], in, n); return 1;
}
static ArMem g_mem = { NULL, mc_read, mc_write };

/* ---- this console's cheats: the same on every PC, because they only ever
 * change through its input stream ---- */
typedef struct { int used; uint16_t id; int nops; ArOp* ops; int undo; McJournal j; } McSlot;
static McSlot g_slot[MC_SLOTS];
static uint16_t g_msg[MC_MAXLEN];
static int g_type, g_len, g_got;       /* the message being received */
static uint32_t g_done;

static void mc_drop(McSlot* s, int undo) {
    if (undo) mc_undo(&s->j);
    free(s->j.u); free(s->ops); memset(s, 0, sizeof *s);
}

/* undo: the cheats' changes are put back (CLEAR_ALL); not when the game started again or a session began (RAM is new) */
static void mc_forget_undo(int undo) {
    for (int i = 0; i < MC_SLOTS; i++) mc_drop(&g_slot[i], undo && g_slot[i].used);
    g_type = g_len = g_got = 0;
    g_mod_lowexp = 0;
    g_mod_noflee = 0;
    g_mod_first = 0;
    g_mod_force = 0;
    memset(g_mod_legstat, 0, sizeof g_mod_legstat);
    g_mod_vanish = 0;
    g_mod_tension = g_mod_coup = g_mod_combo = 0;
    g_mod_tough = g_mod_nospell = g_mod_randenc = g_mod_randboss = 0;
    g_mod_nz = 0;
    lp_clear();
    g_vanish_armed = g_vanish_prev = 0;
}
static void mc_forget(void) { mc_forget_undo(0); }

static ArOp* mc_ops(const uint16_t* w, int nops) {
    ArOp* ops = (ArOp*)calloc((size_t)(nops ? nops : 1), sizeof *ops);
    if (!ops) return NULL;
    for (int i = 0; i < nops; i++, w += 4) {
        ops[i].a = (uint32_t)w[0] | (uint32_t)w[1] << 16;
        ops[i].b = (uint32_t)w[2] | (uint32_t)w[3] << 16;
    }
    return ops;
}

/* ---- the host's cheats, for a guest's window ("Take the host's cheats"): in a session every PC runs a hidden copy of the host's console, and that
 * copy receives the host's cheats through the host's input stream like any other. After every change it writes them (id, undo, ops) into a
 * named memory block of this process; the guest's own copy of this file reads it (mod_hostcheats_copy) and the window sends the same cheats in the
 * guest's own stream. Only the host's console (number 0, hidden) writes. */
#define HC_CAP (1u << 19)
typedef struct { volatile uint32_t seq; uint32_t used, n, pad; uint8_t data[HC_CAP]; } HostCheats;
static HostCheats* hc_open(void) {
#ifdef _WIN32
    static HostCheats* m; static int tried;
    if (m || tried) return m;
    tried = 1;
    char name[64]; snprintf(name, sizeof name, "Local\\dqix-mod-hostcheats-%lu", (unsigned long)GetCurrentProcessId());
    HANDLE h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, (DWORD)sizeof(HostCheats), name);
    if (!h) return NULL;
    m = (HostCheats*)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(HostCheats));
    return m;
#else
    return NULL;
#endif
}
static void hc_publish(void) {
    if (!session_hidden() || session_console() != 0) return;
    HostCheats* m = hc_open(); if (!m) return;
    m->seq++;                                                    /* odd while it is being written */
    uint32_t o = 0, n = 0;
    for (int i = 0; i < MC_SLOTS; i++) if (g_slot[i].used) {
        uint32_t need = 8 + 8 * (uint32_t)g_slot[i].nops;
        if (o + need > HC_CAP) continue;
        uint16_t id = g_slot[i].id, un = (uint16_t)g_slot[i].undo; uint32_t no = (uint32_t)g_slot[i].nops;
        memcpy(m->data + o, &id, 2); memcpy(m->data + o + 2, &un, 2); memcpy(m->data + o + 4, &no, 4);
        memcpy(m->data + o + 8, g_slot[i].ops, 8 * (size_t)no);
        o += need; n++;
    }
    m->used = o; m->n = n;
#ifdef _WIN32
    MemoryBarrier();
#endif
    m->seq++;
}
/* the window: a copy of what the host's console has on. Returns the version (even, never 0), or 0 when there is none. */
uint32_t mod_hostcheats_copy(uint8_t* out, uint32_t* used, uint32_t* n) {
    HostCheats* m = hc_open(); if (!m) return 0;
    for (int tries = 0; tries < 50; tries++) {
        uint32_t a = m->seq;
        if (a & 1) continue;
        uint32_t u = m->used; if (u > HC_CAP) return 0;
        memcpy(out, m->data, u); *used = u; *n = m->n;
        if (m->seq == a) return a ? a : 2;
    }
    return 0;
}

static void mc_message(void) {
    switch (g_type) {
    case 1: {
        int n = g_len / 4; ArOp* ops = mc_ops(g_msg, n);
        if (ops) ar_run(&g_mem, ops, n, AR_KEYS_ALL);
        free(ops);
        break;
    }
    case 2: case 5: {
        if (g_len < 1) break;
        uint16_t id = g_msg[0]; int at = -1;
        for (int i = 0; i < MC_SLOTS; i++) if (g_slot[i].used && g_slot[i].id == id) { at = i; break; }
        for (int i = 0; i < MC_SLOTS && at < 0; i++) if (!g_slot[i].used) at = i;
        if (at < 0) break;
        free(g_slot[at].ops);                            /* the same cheat again: its journal is kept (the first values stay the old ones) */
        if (!g_slot[at].used || g_type != 5) { if (g_slot[at].used) mc_undo(&g_slot[at].j); free(g_slot[at].j.u); memset(&g_slot[at].j, 0, sizeof g_slot[at].j); }
        g_slot[at].used = 1; g_slot[at].id = id; g_slot[at].nops = (g_len - 1) / 4; g_slot[at].undo = g_type == 5;
        g_slot[at].ops = mc_ops(g_msg + 1, g_slot[at].nops);
        if (!g_slot[at].ops) mc_drop(&g_slot[at], 1);
        break;
    }
    case 3:
        for (int i = 0; i < MC_SLOTS; i++) if (g_len >= 1 && g_slot[i].used && g_slot[i].id == g_msg[0]) mc_drop(&g_slot[i], 1);
        break;
    case 4: mc_forget_undo(1); break;
    }
    if (g_type >= 2) hc_publish();
    g_done++;
    g_type = g_len = g_got = 0;
}

static void mc_word(uint16_t w) {
    if (!g_type) {
        int t = w >> 12;
        if (t < 1 || t > 5) return;                      /* not a header: skip it */
        g_type = t; g_len = w & 0xFFF; g_got = 0;
        if (!g_len) mc_message();
        return;
    }
    g_msg[g_got++] = w;
    if (g_got == g_len) mc_message();
}

/* The game started again, or a session began or ended: nothing that was on
 * before counts any more (in a session every copy of this console starts
 * with no cheats). The window notices `gen` and sends its cheats again. */
static void mc_sync(void) {
    static uint64_t last_frame; static int last_ses = -1;
    int ses = session_running();
    if (ses != last_ses || g_frame < last_frame) {
        mc_forget();
        hc_publish();
        nz_reset();
        if (g_box) { g_box->rd = g_box->wr; g_box->gen++; }
        last_ses = ses;
    }
    last_frame = g_frame;
    if (g_box) { g_box->session = (uint32_t)ses; g_box->frame = (uint32_t)g_frame; }
}

/* input.c, every frame: `local` is what the player presses now. If the cheat
 * window has something to send, this frame carries 16 bits of it. */
/* "Walk in any direction" (input.c stick_walk): with the left stick, the hero walks by a stylus the game sees touching and dragging (the mouse is
 * g_fe_touch). A frame that carries a cheat word has no stylus, and while cheats were being sent (all of them again after the game starts or a save
 * is loaded, a cheat switched on, a button in the battle window) that was every frame: the walk was put down again and again (input.c lifts and
 * retouches when the game loses the touch) and the hero barely moved, a step every few frames. Such a frame now has the stick's own direction on the
 * D-pad instead (the nearest of its eight directions), so the hero keeps walking, in the D-pad's eight directions, until the cheats are
 * through; then the stick walks as before. A real stroke (the mouse, the touch screen) still gets a short wait first, as before. */
extern int g_fe_touch, g_fe_stick_x, g_fe_stick_y;
static uint32_t mc_stick_dpad(void) {                    /* the stick's direction as one of the D-pad's eight (as far as it walks: input.c WALK_DEAD) */
    double x = g_fe_stick_x, y = g_fe_stick_y, m = sqrt(x * x + y * y), k = m * 0.3827;   /* sin 22.5 degrees */
    if (m < 9000) return 0;
    return (x > k ? 1u << 4 : 0) | (x < -k ? 1u << 5 : 0) | (y < -k ? 1u << 6 : 0) | (y > k ? 1u << 7 : 0);   /* right, left, up, down */
}
uint32_t mod_cheats_out(uint32_t local) {
    static int sending, waited;
    mc_sync();
    if (!g_box || session_hidden() || rt_hosted()) return local;
    uint32_t rd = g_box->rd;
    if (rd == g_box->wr) { sending = 0; waited = 0; return local; }
    int stick = (local & (1u << 13)) && !g_fe_touch;     /* the stylus is the stick walking, not the mouse */
    if (stick) local |= mc_stick_dpad();                 /* its direction on the D-pad for this frame */
    /* don't lift the stylus in the middle of a stroke if a short wait avoids it */
    if (!sending && !stick && (local & (1u << 13)) && waited < 30) { waited++; return local; }
    sending = 1; waited = 0;
    uint16_t w = g_box->ring[rd % MC_RING];
    g_box->rd = rd + 1;
    return (local & 0x1FFF) | MC_EVENT | (uint32_t)w << 14;
}

/* input.c, every frame, on every copy of this console: `v` is the input this
 * console uses this frame. Takes a cheat word out of it, then runs the cheats
 * that are on. */
uint32_t mod_cheats_in(uint32_t v) {
    mc_sync();
    if ((v & MC_EVENT) && v != 0xFFFFFFFFu) {
        mc_word((uint16_t)(v >> 14));
        v &= 0x1FFF;
    }
    g_mod_lowexp = 0;                                    /* the codes below set it again while they are on */
    g_mod_noflee = 0;
    g_mod_first = 0;
    g_mod_force = 0;                                     /* "Battle any monster you want" sets it again below while a monster is chosen */
    memset(g_mod_legstat, 0, sizeof g_mod_legstat);      /* and its legacy boss levels these */
    g_mod_tension = g_mod_coup = g_mod_combo = 0;        /* "Always high tension", "Always 4-hit combo" / "Coup de Grace always ready" set their members again below */
    g_mod_tough = g_mod_nospell = g_mod_randenc = g_mod_randboss = 0;     /* the Challenges page's switches too */
    g_mod_nz = 0;                                        /* the Nuzlocke rules that are on set their bits again below */
    lp_clear();                                          /* the live code mods below set their sites again while they are on */
    g_vanish_armed = 0;
    int keys = (int)(v & 0xFFF);                         /* this console's buttons this frame: the same on every PC */
    for (int i = 0; i < MC_SLOTS; i++) if (g_slot[i].used) {
        g_journal = g_slot[i].undo ? &g_slot[i].j : NULL;
        ar_run(&g_mem, g_slot[i].ops, g_slot[i].nops, keys);
        g_journal = NULL;
    }
    {   /* test hook DQIX_TEST_DESYNC=frame: this PC's own console changes a byte of its RAM outside the input stream at that frame, so the PCs drift apart
         * (tests/test_session_break.py checks that the break is noticed, logged and offered a Reconnect) */
        static long at = -2;
        if (at == -2) { const char* e = getenv("DQIX_TEST_DESYNC"); at = e ? atol(e) : -1; }
        if (at >= 0 && (long)g_frame == at && !session_hidden() && session_running()) g_main_ram[0x00340000u & (MAIN_RAM_SIZE - 1)] ^= 0x55;
    }
    mc_track_hp();
    mc_battle_locks();
    mc_challenges();
    g_mod_vanish = g_vanish_armed;                       /* the cheat is on: vanished (the window's button switches it) */
    if (g_mod_vanish != g_vanish_prev) {
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod: vanish %s at frame %llu\n", g_mod_vanish ? "on" : "off", (unsigned long long)g_frame);
        g_vanish_prev = g_mod_vanish;
    }
    nz_frame(g_mod_nz, session_running());               /* the Nuzlocke rules (nuzlocke.c) */
    if (g_box) g_box->done = g_done;
    return v;
}
