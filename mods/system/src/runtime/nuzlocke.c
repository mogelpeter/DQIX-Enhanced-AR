/* DQIX Enhanced mods: the Nuzlocke page of the Cheats window.
 *
 * Two parts, both the same on the USA and the European game (the party's RAM addresses are the same in both, and the
 * data tables are found by their path in the cartridge, not by an address):
 *
 *  1. RULES (nz_frame, called every frame from mod_cheats_in): permadeath, the hero's death ends the run, soul link pairs
 *     and the punishments. They are live cheats (switch addresses 02F5A5C0 + 4n, see mod_cheats.c), so they travel in the
 *     input stream like every other cheat and every PC of a session computes the same thing. Only in a game played alone
 *     the dead are also written to nuzlocke-run.txt (next to dqix.exe), so a dead party member stays dead when the game is
 *     started again or an older save is loaded; in a session nothing is read from or written to a file.
 *
 *  2. RANDOMIZERS (nz_overlay, called from mod_card_overlay, i.e. from every read of the cartridge): a seed turns the
 *     tables of the cartridge into a changed copy that is laid over the game's reads, exactly like mod_data.c does for the
 *     encounter tables. Launch options (DQIX_MOD_NZ_*), "All players" in a session: every PC must start with the same ones.
 *        DQIX_MOD_NZ_SEED=n     the seed (default 1)
 *        DQIX_MOD_NZ_SKILLS=1   which ability a skill tree gives (data/prm/skilltable.bin)
 *        DQIX_MOD_NZ_SPELLS=1   which spell a vocation learns at which level (data/prm/spelltable.bin)
 *        DQIX_MOD_NZ_GROWTH=1   where each vocation's stat growth comes from (data/prm/level0..12.bin)
 *        DQIX_MOD_NZ_DROPS=1    what monsters drop (data/prm/mon_btldata.nat)
 *        DQIX_MOD_NZ_SHOPS=1    what the shops sell (data/bin/menu/shopdata1.bin)
 *     (DQIX_MOD_NZ_ENC=1, random monsters in the field, lives in mod_data.c: it needs the encounter tables.)
 *  DQIX_MODLOG=1 prints what was done.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nds.h"

/* ---- mod_data.c ---- */
typedef void (*NzRecFn)(uint8_t* values, uint16_t tag, int cnt, void* ctx);
int mod_nds_lookup(const char* path, uint32_t* start, uint32_t* size);
void mod_each_record(uint8_t* b, uint32_t size, NzRecFn fn, void* ctx);

/* ---- the seeded random numbers (splitmix64) ---- */
static uint64_t g_rs;
static uint64_t rnd64(void) {
    uint64_t z = (g_rs += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}
static uint32_t rnd(uint32_t n) { return n ? (uint32_t)(rnd64() % n) : 0; }
void mod_nz_seed(uint32_t seed, uint32_t salt) { g_rs = ((uint64_t)seed << 32 | salt) ^ 0x4E5A4C4F434B45ull; rnd64(); }
uint32_t mod_nz_rnd(uint32_t n) { return rnd(n); }
static uint32_t nrd32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }
static void nwr32(uint8_t* p, uint32_t v) { memcpy(p, &v, 4); }
static uint16_t nrd16(const uint8_t* p) { uint16_t v; memcpy(&v, p, 2); return v; }
static void nwr16(uint8_t* p, uint16_t v) { memcpy(p, &v, 2); }

/* ---- the changed copies of the cartridge's files ---- */
#define NZ_MAXF 20
typedef struct { char name[40]; uint32_t start, size; uint8_t* data; } NzFile;
static NzFile nzf[NZ_MAXF]; static int nzn;
static int g_nz_state;                             /* 0 not built, 1 built, -1 nothing to do */
static uint32_t g_seed = 1;

static uint32_t env_u(const char* k, uint32_t def) { const char* v = getenv(k); return v && *v ? (uint32_t)strtoul(v, NULL, 10) : def; }

static NzFile* add_file(const char* path) {
    if (nzn >= NZ_MAXF) return NULL;
    NzFile* f = &nzf[nzn];
    uint32_t s, z;
    if (!mod_nds_lookup(path, &s, &z)) return NULL;
    uint8_t* d = (uint8_t*)malloc(z);
    if (!d) return NULL;
    memcpy(d, g_rom + s, z);
    snprintf(f->name, sizeof f->name, "%s", path);
    f->start = s; f->size = z; f->data = d; nzn++;
    return f;
}

/* the records of one tag, collected */
#define NZ_MAXR 1024
typedef struct { uint8_t* v; int cnt; uint16_t tag; } NzRec;
static NzRec nzr[NZ_MAXR]; static int nzc;
static void collect(uint8_t* v, uint16_t tag, int cnt, void* ctx) {
    (void)ctx;
    if (nzc < NZ_MAXR) { nzr[nzc].v = v; nzr[nzc].cnt = cnt; nzr[nzc].tag = tag; nzc++; }
}
static void scan(NzFile* f) { nzc = 0; mod_each_record(f->data, f->size, collect, NULL); }

/* Fisher-Yates over an array of u32 */
static void shuffle32(uint32_t* a, int n) {
    for (int i = n - 1; i > 0; i--) { int j = (int)rnd((uint32_t)i + 1); uint32_t t = a[i]; a[i] = a[j]; a[j] = t; }
}

/* skill trees: the ability a row of a skill line gives (value 3, when value 4 says "an ability": 1) is dealt out again over all
 * those rows. Every ability is still learned exactly once, only in another skill line, at another skill point cost. */
static void rnd_skills(void) {
    NzFile* f = add_file("data/prm/skilltable.bin"); if (!f) return;
    scan(f);
    static uint32_t pool[NZ_MAXR]; static int at[NZ_MAXR]; int n = 0;
    for (int i = 0; i < nzc; i++)
        if (nzr[i].tag == 0x66 && nzr[i].cnt >= 9 && nrd32(nzr[i].v + 16) == 1 && nrd32(nzr[i].v + 12)) { pool[n] = nrd32(nzr[i].v + 12); at[n++] = i; }
    mod_nz_seed(g_seed, 1); shuffle32(pool, n);
    for (int k = 0; k < n; k++) nwr32(nzr[at[k]].v + 12, pool[k]);
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: %d skill-tree abilities dealt out again (seed %u)\n", n, g_seed);
}

/* class spells: (vocation, spell, level) rows; the spell column is dealt out again, then a vocation that got a spell twice
 * swaps one of them with a row of another vocation */
static void rnd_spells(void) {
    NzFile* f = add_file("data/prm/spelltable.bin"); if (!f) return;
    scan(f);
    static uint32_t pool[NZ_MAXR]; static int at[NZ_MAXR]; int n = 0;
    for (int i = 0; i < nzc; i++) if (nzr[i].tag == 0x67 && nzr[i].cnt >= 3) { pool[n] = nrd32(nzr[i].v + 4); at[n++] = i; }
    mod_nz_seed(g_seed, 2); shuffle32(pool, n);
    for (int pass = 0; pass < 400; pass++) {
        int bad = 0;
        for (int a = 0; a < n; a++) for (int b = 0; b < a; b++)
            if (nrd32(nzr[at[a]].v) == nrd32(nzr[at[b]].v) && pool[a] == pool[b]) {
                int j = (int)rnd((uint32_t)n); uint32_t t = pool[a]; pool[a] = pool[j]; pool[j] = t; bad++; break;
            }
        if (!bad) break;
    }
    for (int k = 0; k < n; k++) nwr32(nzr[at[k]].v + 4, pool[k]);
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: %d class spell slots dealt out again (seed %u)\n", n, g_seed);
}

/* stat growth: the 13 vocations' level tables (experience needed, then nine stat columns per level). Every stat column of a
 * vocation is taken from another vocation's table (a different draw for every column); the experience column stays. */
static void rnd_growth(void) {
    NzFile* t[13]; int rows = -1;
    static uint8_t* col[13][128]; 
    for (int v = 0; v < 13; v++) {
        char p[40]; snprintf(p, sizeof p, "data/prm/level%d.bin", v);
        t[v] = add_file(p); if (!t[v]) return;
        scan(t[v]);
        int n = 0;
        for (int i = 0; i < nzc && n < 128; i++) if (nzr[i].tag == 0x66 && nzr[i].cnt >= 10) col[v][n++] = nzr[i].v;
       
        if (rows < 0) rows = n; else if (rows != n) return;
    }
    static uint32_t save[13][128][10];
    for (int v = 0; v < 13; v++) for (int r = 0; r < rows; r++) for (int c = 0; c < 10; c++) save[v][r][c] = nrd32(col[v][r] + 4 * c);
    for (int c = 1; c <= 9; c++) {
        uint32_t perm[13]; for (int v = 0; v < 13; v++) perm[v] = (uint32_t)v;
        mod_nz_seed(g_seed, 100 + (uint32_t)c); shuffle32(perm, 13);
        for (int v = 0; v < 13; v++) for (int r = 0; r < rows; r++) nwr32(col[v][r] + 4 * c, save[perm[v]][r][c]);
    }
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: stat growth of 13 vocations mixed (%d levels, seed %u)\n", rows, g_seed);
}

/* monster drops: 132-byte records after a 4-byte count, the common drop is the 16-bit item at +4 and the rare one at +6 of a record.
 * Only the ordinary monsters (the field's: data/prm/fld_mondata.bin tag 0x65, value 3 not 0) are touched, so a boss that drops
 * something the story needs keeps it. The commons are dealt out among the commons, the rares among the rares. */
#define MON_REC 132
static uint8_t g_ordinary[1024];
static void ord_rec(uint8_t* v, uint16_t tag, int cnt, void* ctx) {
    (void)ctx;
    if (tag == 0x65 && cnt >= 3 && nrd32(v + 8) != 0) { uint32_t m = nrd32(v) & 0xFFF; if (m < sizeof g_ordinary) g_ordinary[m] = 1; }
}
static int load_ordinary(void) {
    static int done;
    if (done) return done > 0;
    uint32_t s, z; done = -1;
    if (!mod_nds_lookup("data/prm/fld_mondata.bin", &s, &z)) return 0;
    uint8_t* d = (uint8_t*)malloc(z); if (!d) return 0;
    memcpy(d, g_rom + s, z);
    mod_each_record(d, z, ord_rec, NULL);
    free(d); done = 1; return 1;
}
static void rnd_drops(void) {
    NzFile* f = add_file("data/prm/mon_btldata.nat"); if (!f || !load_ordinary()) return;
    uint32_t cnt = nrd32(f->data) & 0xFFF;
    if (4 + cnt * MON_REC > f->size) return;
    for (int slot = 0; slot < 2; slot++) {
        static uint32_t pool[1024]; static uint32_t at[1024]; int n = 0;
        for (uint32_t m = 0; m < cnt && m < sizeof g_ordinary; m++) {
            uint8_t* p = f->data + 4 + m * MON_REC + 4 + 2 * (uint32_t)slot;
            if (g_ordinary[m] && nrd16(p)) { pool[n] = nrd16(p); at[n++] = m; }
        }
        mod_nz_seed(g_seed, 200 + (uint32_t)slot); shuffle32(pool, n);
        for (int k = 0; k < n; k++) nwr16(f->data + 4 + at[k] * MON_REC + 4 + 2 * (uint32_t)slot, (uint16_t)pool[k]);
        if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: %d %s drops dealt out again (seed %u)\n", n, slot ? "rare" : "common", g_seed);
    }
}

/* shops: the shop lists are 20 item numbers per shop (0 = empty); the nonzero ones are dealt out among all the shops' slots */
static void rnd_shops(void) {
    NzFile* f = add_file("data/bin/menu/shopdata1.bin"); if (!f) return;
    scan(f);
    static uint32_t pool[NZ_MAXR * 4]; static uint8_t* at[NZ_MAXR * 4]; int n = 0;
    for (int i = 0; i < nzc; i++)
        if (nzr[i].tag == 0x67 && nzr[i].cnt >= 22)
            for (int k = 2; k < 22; k++) if (nrd32(nzr[i].v + 4 * k) && n < NZ_MAXR * 4) { pool[n] = nrd32(nzr[i].v + 4 * k); at[n++] = nzr[i].v + 4 * k; }
    mod_nz_seed(g_seed, 300); shuffle32(pool, n);
    for (int k = 0; k < n; k++) nwr32(at[k], pool[k]);
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: %d shop slots dealt out again (seed %u)\n", n, g_seed);
}

static void nz_build(void) {
    g_nz_state = -1;
    g_seed = env_u("DQIX_MOD_NZ_SEED", 1);
    if (env_u("DQIX_MOD_NZ_SKILLS", 0)) rnd_skills();
    if (env_u("DQIX_MOD_NZ_SPELLS", 0)) rnd_spells();
    if (env_u("DQIX_MOD_NZ_GROWTH", 0)) rnd_growth();
    if (env_u("DQIX_MOD_NZ_DROPS", 0)) rnd_drops();
    if (env_u("DQIX_MOD_NZ_SHOPS", 0)) rnd_shops();
    if (nzn) g_nz_state = 1;
}

/* mod_data.c's mod_card_overlay, after it filled the buffer with the cartridge's bytes at ROM address addr */
void nz_overlay(uint32_t addr, uint32_t len, uint8_t* buf) {
    static int init;
    if (!len || !g_rom) return;
    if (!init) {
        init = 1;
        if (env_u("DQIX_MOD_NZ_SKILLS", 0) || env_u("DQIX_MOD_NZ_SPELLS", 0) || env_u("DQIX_MOD_NZ_GROWTH", 0) || env_u("DQIX_MOD_NZ_DROPS", 0) || env_u("DQIX_MOD_NZ_SHOPS", 0)) nz_build();
        else g_nz_state = -1;
    }
    if (g_nz_state <= 0) return;
    for (int i = 0; i < nzn; i++) {
        const NzFile* f = &nzf[i];
        uint32_t lo = addr > f->start ? addr : f->start;
        uint32_t hi = addr + len < f->start + f->size ? addr + len : f->start + f->size;
        if (lo < hi) {
            memcpy(buf + (lo - addr), f->data + (lo - f->start), hi - lo);
            if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: %s bytes %u..%u handed out\n", f->name, lo - f->start, hi - f->start);
        }
    }
}

/* ======================================================================== the rules */
#define NZ_PARTY0   0x020F54B4u        /* the first party member's record: his name (8-bit characters) */
#define NZ_STRIDE   0x964u             /* the next member's record is this much lower */
#define NZ_GOLD     0x020F6D48u
#define NZ_HP_FIELD 0x30u              /* the HP outside a battle (u16) */
#define NZ_BMAX     0x58u              /* the battle's own copy: maximum HP, nonzero only during a battle ... */
#define NZ_BHP      0x5Cu              /* ... and the HP now */
#define NZ_SLOTS    4
#define NZ_DEBOUNCE 4                  /* frames an HP of 0 must last before it counts as a death (a battle starting fills the numbers over a few frames) */

enum { NZ_PERMA = 1u << 0, NZ_HERO_END = 1u << 1, NZ_LINK = 1u << 2, NZ_GOLD_HALF = 1u << 3, NZ_GOLD_ALL = 1u << 4, NZ_CMD_NEW = 1u << 31 };

typedef struct { uint32_t hash; int seen_alive, zero, dead; } NzSlot;
static NzSlot g_s[NZ_SLOTS];
static uint32_t g_dead[64]; static char g_dead_name[64][12]; static int g_ndead;
static int g_loaded, g_cmd;
static uint32_t g_deaths;

static uint8_t* ram(uint32_t a) { return &g_main_ram[a & (MAIN_RAM_SIZE - 1)]; }
static const char* run_path(void) { return "nuzlocke-run.txt"; }

static uint32_t name_hash(uint32_t base) {
    const uint8_t* n = ram(base); uint32_t h = 2166136261u; int any = 0;
    for (int i = 0; i < 16 && n[i]; i++) { h = (h ^ n[i]) * 16777619u; any = 1; }
    return any ? h | 1u : 0;
}
static int is_dead_name(uint32_t h) { for (int i = 0; i < g_ndead; i++) if (g_dead[i] == h) return 1; return 0; }

static void save_run(void) {
    FILE* f = fopen(run_path(), "wb"); if (!f) return;
    fprintf(f, "# DQIX Enhanced Nuzlocke: the fallen. One line per dead party member (a number made of the name, then the name). Delete this file or use \"Start a new run\" to forget them.\n");
    for (int i = 0; i < g_ndead; i++) fprintf(f, "dead %08x %s\n", g_dead[i], g_dead_name[i]);
    fclose(f);
}
static void load_run(void) {
    FILE* f = fopen(run_path(), "rb"); if (!f) return;
    char line[128]; unsigned h; char nm[16];
    while (fgets(line, sizeof line, f)) {
        nm[0] = 0;
        if (sscanf(line, "dead %x %11s", &h, nm) >= 1 && g_ndead < 64) { g_dead[g_ndead] = h; snprintf(g_dead_name[g_ndead], sizeof g_dead_name[0], "%s", nm); g_ndead++; }
    }
    fclose(f);
}

/* what the game made of the dead member: no HP, in the field and in a battle */
static void pin(int i) {
    uint32_t b = NZ_PARTY0 - (uint32_t)i * NZ_STRIDE;
    nwr16(ram(b + NZ_HP_FIELD), 0);
    if (nrd16(ram(b + NZ_BMAX))) nwr16(ram(b + NZ_BHP), 0);
}

static void kill_slot(int i, int session, const char* why) {
    if (g_s[i].dead) return;
    g_s[i].dead = 1;
    uint32_t h = g_s[i].hash;
    if (h && !is_dead_name(h) && g_ndead < 64) {
        const uint8_t* nm = ram(NZ_PARTY0 - (uint32_t)i * NZ_STRIDE); int k = 0;
        for (; k < 10 && nm[k] >= 33 && nm[k] < 127; k++) g_dead_name[g_ndead][k] = (char)nm[k];
        g_dead_name[g_ndead][k] = 0; g_dead[g_ndead++] = h;
    }
    g_deaths++;
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "nuzlocke: party member %d falls (%s) at frame %llu\n", i + 1, why, (unsigned long long)g_frame);
    if (!session) save_run();
}

/* flags: the switches that are on this frame (bit n = the address 02F5A5C0 + 4n written). cmd: a one-off command. */
void nz_frame(uint32_t flags, int session) {
    if (!g_loaded) { g_loaded = 1; if (!session) load_run(); }
    if (g_cmd & 1) {                                    /* "Start a new run": nobody is dead */
        g_cmd = 0; g_ndead = 0; g_deaths = 0;
        memset(g_s, 0, sizeof g_s);
        if (!session) remove(run_path());
    }
    if (!(flags & NZ_PERMA)) { memset(g_s, 0, sizeof g_s); return; }
    int fell[NZ_SLOTS] = { 0, 0, 0, 0 };
    for (int i = 0; i < NZ_SLOTS; i++) {
        uint32_t b = NZ_PARTY0 - (uint32_t)i * NZ_STRIDE;
        uint32_t h = name_hash(b);
        NzSlot* s = &g_s[i];
        if (!h) { memset(s, 0, sizeof *s); continue; }
        if (s->hash != h) { memset(s, 0, sizeof *s); s->hash = h; s->dead = is_dead_name(h); }
        if (s->dead) { pin(i); continue; }
        int inb = nrd16(ram(b + NZ_BMAX)) != 0;
        int alive = (inb ? nrd16(ram(b + NZ_BHP)) : nrd16(ram(b + NZ_HP_FIELD))) != 0;
        if (alive) { s->seen_alive = 1; s->zero = 0; }
        else if (s->seen_alive && ++s->zero >= NZ_DEBOUNCE) fell[i] = 1;
    }
    for (int i = 0; i < NZ_SLOTS; i++) if (fell[i]) kill_slot(i, session, "KO");
    int fresh = 0; for (int i = 0; i < NZ_SLOTS; i++) fresh += fell[i];
    if (!fresh) return;
    if (flags & NZ_LINK)                                /* soul link: 1 and 2, 3 and 4 fall together */
        for (int i = 0; i < NZ_SLOTS; i++) if (fell[i] && g_s[i ^ 1].hash) kill_slot(i ^ 1, session, "soul link");
    if ((flags & NZ_HERO_END) && g_s[0].dead)           /* the hero is the run: when he falls everybody does */
        for (int i = 1; i < NZ_SLOTS; i++) if (g_s[i].hash) kill_slot(i, session, "the hero fell");
    if (flags & (NZ_GOLD_HALF | NZ_GOLD_ALL)) {
        uint32_t gold = nrd32(ram(NZ_GOLD));
        for (int k = 0; k < fresh; k++) gold = (flags & NZ_GOLD_ALL) ? 0 : gold / 2;
        nwr32(ram(NZ_GOLD), gold);
    }
    for (int i = 0; i < NZ_SLOTS; i++) if (g_s[i].dead) pin(i);
}

/* the cheat code "Start a new run" (once) writes the address 02F5A5FC: mod_cheats.c hands it over here */
void nz_command(int cmd) { g_cmd |= cmd; }
/* the game started again or a session began or ended: the console's own memory is new */
void nz_reset(void) { memset(g_s, 0, sizeof g_s); g_ndead = 0; g_loaded = 0; g_cmd = 0; }
uint32_t nz_deaths(void) { return g_deaths; }
