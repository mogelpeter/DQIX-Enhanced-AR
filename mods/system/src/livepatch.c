/* DQIX Enhanced mods: code mods that switch on and off while the game runs (no rebuild).
 *
 * A code mod changes instructions of the game. The game's program is compiled C, so that used to mean building the
 * game again. Now the build wraps (wrap.txt: tools/apply_runtime_mod.py writes the lines) every function that any code
 * mod touches, once. Such a function runs natively as before; while a mod that touches it is on, it runs in the
 * runtime's ARM interpreter (interp.c) instead, over the code in RAM with that mod's instructions put in for the duration
 * of the call and taken out again after it. The code in RAM is what the ROM has, so the interpreter does exactly what
 * the compiled version does, plus the changes.
 *
 * How a mod is switched: it is an ordinary live cheat ("always") whose lines write the new instruction word to the
 * address LP_BASE + 4 * n, n = the instruction site's number in mods/system/bin/livepatch.txt. Like the other switches
 * (lowexp, vanish) it is cleared at the start of each frame and set again by the cheat while it is on, so it is the same
 * on every PC of a session (the cheat travels in the input stream).
 *
 * DQIX_LP_FORCE=1 runs every wrapped function in the interpreter even without a mod (a test: the game must behave the same).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cpu.h"
#include "nds.h"

#define LP_BASE 0x02F60000u

/* the tables: mod_livepatch_tab.c, written by apply_runtime_mod.py */
extern const unsigned g_lp_nfn, g_lp_nsite;
extern const uint32_t g_lp_entry[];          /* address of function i (bit 0 = Thumb) */
extern const uint16_t g_lp_site_fn[];        /* the function of site n */
extern const uint32_t g_lp_site_addr[];      /* the RAM address of site n */
extern const uint16_t g_lp_first[];          /* function i: its sites are g_lp_site_*[first..first+count) (sorted by function) */
extern const uint16_t g_lp_count[];
extern const uint32_t g_lp_words[];          /* the instruction words a site may be patched with (the catalog's code mods) */
extern const uint16_t g_lp_wfirst[];
extern const uint8_t g_lp_wcount[];
void interp_stub(Cpu* c, uint32_t addr);

#define LP_MAX_SITES 4096
#define LP_MAX_FN 2048
static uint32_t g_word[LP_MAX_SITES];
static uint8_t g_act[LP_MAX_SITES];
static uint8_t g_fn_on[LP_MAX_FN];
static int g_force = -1;

/* mod_cheats.c, at the start of every frame: nothing is patched until the cheats that are on say so */
void lp_clear(void) {
    memset(g_act, 0, sizeof g_act);
    memset(g_fn_on, 0, sizeof g_fn_on);
}

/* mod_cheats.c: a cheat wrote `word` to LP_BASE + 4n */
int lp_set(uint32_t addr, uint32_t word) {
    uint32_t n = (addr - LP_BASE) >> 2;
    if (n >= g_lp_nsite || n >= LP_MAX_SITES) return 1;                /* a number this game doesn't have: ignore */
    int allowed = 0;                                                  /* a peer in a session sends this too: only the words the mods use */
    for (unsigned k = 0; k < g_lp_wcount[n]; k++) if (g_lp_words[g_lp_wfirst[n] + k] == word) allowed = 1;
    if (!allowed) return 1;
    g_act[n] = 1; g_word[n] = word;
    if (g_lp_site_fn[n] < LP_MAX_FN) g_fn_on[g_lp_site_fn[n]] = 1;
    return 1;
}

static uint32_t* ram32(uint32_t a) { return (uint32_t*)&g_main_ram[a & (MAIN_RAM_SIZE - 1)]; }

/* the wrapper of function i (mod_livepatch_tab.c): `orig` is the compiled function */
void lp_call(unsigned i, Cpu* c, void (*orig)(Cpu*)) {
    if (g_force < 0) g_force = getenv("DQIX_LP_FORCE") != NULL;
    if (i >= LP_MAX_FN || (!g_fn_on[i] && !g_force)) { orig(c); return; }
    uint32_t save[64]; uint16_t at[64]; int n = 0;
    for (unsigned k = 0; k < g_lp_count[i] && n < 64; k++) {
        unsigned s = g_lp_first[i] + k;
        if (!g_act[s]) continue;
        at[n] = (uint16_t)s; save[n] = *ram32(g_lp_site_addr[s]);
        *ram32(g_lp_site_addr[s]) = g_word[s]; n++;
    }
    if (n && getenv("DQIX_MODLOG")) {                    /* the first time a function runs with a mod's instructions in it */
        static uint8_t seen[LP_MAX_FN];
        if (!seen[i]) { seen[i] = 1; fprintf(stderr, "mod: livepatch function %08x runs with %d patched instruction(s)\n", g_lp_entry[i] & ~1u, n); }
    }
    interp_stub(c, g_lp_entry[i]);
    while (n--) *ram32(g_lp_site_addr[at[n]]) = save[n];
}
