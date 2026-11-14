/* Host test for the Nuzlocke randomizers (nuzlocke.c, and the random encounters in mod_data.c): the real code is compiled as it is and
 * run on the ROM's own tables. For every randomizer the changed copy must differ from the cartridge's file only where it is meant
 * to, deal out exactly the values that were there (nothing invented, nothing lost), keep the file's size, give the same result
 * for the same seed and another result for another one.
 *   gcc -I <game>/runtime -o t.exe test_nuzlocke_data.c    t.exe <rom.nds>
 * (run it for the European and the USA ROM)
 */
#include "../src/runtime/mod_data.c"
#include "../src/runtime/nuzlocke.c"

uint8_t* g_rom; size_t g_rom_size;
uint8_t g_main_ram[MAIN_RAM_SIZE]; uint64_t g_frame;
char* rt_getenv(const char* n) { (void)n; return NULL; }

static int fails;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); } } while (0)

static uint8_t* orig_of(const char* path, uint32_t* z) {
    uint32_t s; if (!mod_nds_lookup(path, &s, z)) { printf("FAIL: %s not in the ROM\n", path); exit(1); }
    return g_rom + s;
}
static void reset(uint32_t seed, const char* which) {
    for (int i = 0; i < nzn; i++) free(nzf[i].data);
    nzn = 0; g_nz_state = 0; g_seed = seed;
    (void)which;
}
static int cmp_u32(const void* a, const void* b) { uint32_t x = *(const uint32_t*)a, y = *(const uint32_t*)b; return x < y ? -1 : x > y; }
static int cmp_u16(const void* a, const void* b) { uint16_t x = *(const uint16_t*)a, y = *(const uint16_t*)b; return x < y ? -1 : x > y; }

/* every record's values of a file (tag, count, pointer), for a copy and for the original */
typedef struct { uint16_t tag; int cnt; uint8_t* v; } R;
static R ra[2048], rb[2048]; static int na, nb;
static void col_a(uint8_t* v, uint16_t t, int c, void* x) { (void)x; if (na < 2048) { ra[na].tag = t; ra[na].cnt = c; ra[na++].v = v; } }
static void col_b(uint8_t* v, uint16_t t, int c, void* x) { (void)x; if (nb < 2048) { rb[nb].tag = t; rb[nb].cnt = c; rb[nb++].v = v; } }
static void walk(uint8_t* a, uint8_t* b, uint32_t z) {
    na = nb = 0; mod_each_record(a, z, col_a, NULL); mod_each_record(b, z, col_b, NULL);
}

static void t_skills(uint32_t seed, uint8_t** out) {
    reset(seed, "skills"); rnd_skills();
    CHECK(nzn == 1, "skills: file not built");
    uint32_t z; uint8_t* o = orig_of("data/prm/skilltable.bin", &z);
    CHECK(nzf[0].size == z, "skills: size changed");
    uint8_t* tmp = (uint8_t*)malloc(z); memcpy(tmp, o, z);
    walk(nzf[0].data, tmp, z);
    CHECK(na == nb, "skills: record count");
    uint32_t pa[1024], pb[1024]; int n = 0, changed = 0;
    for (int i = 0; i < na; i++) {
        int isab = rb[i].tag == 0x66 && rb[i].cnt >= 9 && rd32(rb[i].v + 16) == 1 && rd32(rb[i].v + 12);
        for (int k = 0; k < rb[i].cnt; k++) {
            uint32_t x = rd32(ra[i].v + 4 * k), y = rd32(rb[i].v + 4 * k);
            if (x != y) { changed++; CHECK(isab && k == 3, "skills: record %d value %d changed but is not an ability", i, k); }
        }
        if (isab) { pa[n] = rd32(ra[i].v + 12); pb[n++] = rd32(rb[i].v + 12); }
    }
    qsort(pa, (size_t)n, 4, cmp_u32); qsort(pb, (size_t)n, 4, cmp_u32);
    CHECK(memcmp(pa, pb, (size_t)n * 4) == 0, "skills: abilities are not a permutation");
    CHECK(changed > n / 2, "skills: only %d of %d changed", changed, n);
    free(tmp);
    if (out) { *out = (uint8_t*)malloc(z); memcpy(*out, nzf[0].data, z); }
    printf("skills seed %u: %d abilities, %d moved\n", seed, n, changed);
}

static void t_spells(uint32_t seed) {
    reset(seed, "spells"); rnd_spells();
    uint32_t z; uint8_t* o = orig_of("data/prm/spelltable.bin", &z);
    uint8_t* tmp = (uint8_t*)malloc(z); memcpy(tmp, o, z);
    walk(nzf[0].data, tmp, z);
    uint32_t pa[1024], pb[1024]; int n = 0, changed = 0;
    for (int i = 0; i < na; i++) {
        int sp = rb[i].tag == 0x67 && rb[i].cnt >= 3;
        for (int k = 0; k < rb[i].cnt; k++)
            if (rd32(ra[i].v + 4 * k) != rd32(rb[i].v + 4 * k)) { changed++; CHECK(sp && k == 1, "spells: record %d value %d changed", i, k); }
        if (sp) { pa[n] = rd32(ra[i].v + 4); pb[n++] = rd32(rb[i].v + 4); }
    }
    qsort(pa, (size_t)n, 4, cmp_u32); qsort(pb, (size_t)n, 4, cmp_u32);
    CHECK(memcmp(pa, pb, (size_t)n * 4) == 0, "spells: not a permutation");
    int dup = 0;
    for (int i = 0; i < na; i++) for (int j = 0; j < i; j++)
        if (ra[i].tag == 0x67 && ra[j].tag == 0x67 && rd32(ra[i].v) == rd32(ra[j].v) && rd32(ra[i].v + 4) == rd32(ra[j].v + 4)) dup++;
    CHECK(dup == 0, "spells: %d vocations got a spell twice", dup);
    CHECK(changed > n / 2, "spells: only %d of %d changed", changed, n);
    free(tmp);
    printf("spells seed %u: %d slots, %d moved, %d double\n", seed, n, changed, dup);
}

static void t_growth(uint32_t seed) {
    reset(seed, "growth"); rnd_growth();
    CHECK(nzn == 13, "growth: %d files", nzn);
    int changed = 0;
    for (int v = 0; v < 13 && v < nzn; v++) {
        uint32_t z; char p[40]; snprintf(p, sizeof p, "data/prm/level%d.bin", v);
        uint8_t* o = orig_of(p, &z);
        CHECK(nzf[v].size == z, "growth: size of %s", p);
        uint8_t* tmp = (uint8_t*)malloc(z); memcpy(tmp, o, z);
        walk(nzf[v].data, tmp, z);
        for (int i = 0; i < na; i++) for (int k = 0; k < rb[i].cnt; k++)
            if (rd32(ra[i].v + 4 * k) != rd32(rb[i].v + 4 * k)) {
                changed++; CHECK(rb[i].tag == 0x66 && rb[i].cnt >= 10 && k >= 1 && k <= 9, "growth: %s record %d value %d changed", p, i, k);
            }
        free(tmp);
    }
    /* per level and stat column the 13 vocations' values are the same set as before */
    for (int r = 0; r < 99; r++) for (int c = 1; c <= 9; c++) {
        uint32_t a[13], b[13];
        for (int v = 0; v < 13; v++) {
            uint32_t z; char p[40]; snprintf(p, sizeof p, "data/prm/level%d.bin", v);
            uint8_t* o = orig_of(p, &z); uint8_t* tmp = (uint8_t*)malloc(z); memcpy(tmp, o, z);
            walk(nzf[v].data, tmp, z);
            int idx = -1, seen = 0;
            for (int i = 0; i < na; i++) if (rb[i].tag == 0x66 && rb[i].cnt >= 10 && seen++ == r) { idx = i; break; }
            a[v] = rd32(ra[idx].v + 4 * c); b[v] = rd32(rb[idx].v + 4 * c); free(tmp);
        }
        qsort(a, 13, 4, cmp_u32); qsort(b, 13, 4, cmp_u32);
        if (memcmp(a, b, sizeof a)) { CHECK(0, "growth: level row %d column %d is not a permutation of the vocations", r, c); r = 99; break; }
    }
    CHECK(changed > 1000, "growth: only %d values changed", changed);
    printf("growth seed %u: %d values moved\n", seed, changed);
}

static void t_drops(uint32_t seed) {
    reset(seed, "drops"); rnd_drops();
    uint32_t z; uint8_t* o = orig_of("data/prm/mon_btldata.nat", &z);
    CHECK(nzn == 1 && nzf[0].size == z, "drops: build");
    uint32_t cnt = rd32(o) & 0xFFF; int changed = 0;
    uint16_t ca[1024], cb[1024], ra_[1024], rb_[1024]; int nc = 0, nr = 0;
    for (uint32_t m = 0; m < cnt; m++) {
        uint8_t* x = nzf[0].data + 4 + m * MON_REC; uint8_t* y = o + 4 + m * MON_REC;
        for (int k = 0; k < MON_REC; k++) if (x[k] != y[k]) { changed++; CHECK(g_ordinary[m] && k >= 4 && k < 8, "drops: monster %u byte %d changed (ordinary %d)", m, k, g_ordinary[m]); break; }
        if (g_ordinary[m]) {
            if (nrd16(y + 4)) { ca[nc] = nrd16(x + 4); cb[nc++] = nrd16(y + 4); }
            if (nrd16(y + 6)) { ra_[nr] = nrd16(x + 6); rb_[nr++] = nrd16(y + 6); }
        }
    }
    qsort(ca, (size_t)nc, 2, cmp_u16); qsort(cb, (size_t)nc, 2, cmp_u16); qsort(ra_, (size_t)nr, 2, cmp_u16); qsort(rb_, (size_t)nr, 2, cmp_u16);
    CHECK(!memcmp(ca, cb, (size_t)nc * 2) && !memcmp(ra_, rb_, (size_t)nr * 2), "drops: not a permutation");
    CHECK(changed > 100, "drops: %d monsters changed", changed);
    printf("drops seed %u: %d common, %d rare, %d monsters changed\n", seed, nc, nr, changed);
}

static void t_shops(uint32_t seed) {
    reset(seed, "shops"); rnd_shops();
    uint32_t z; uint8_t* o = orig_of("data/bin/menu/shopdata1.bin", &z);
    uint8_t* tmp = (uint8_t*)malloc(z); memcpy(tmp, o, z);
    walk(nzf[0].data, tmp, z);
    uint32_t pa[4096], pb[4096]; int n = 0, changed = 0;
    for (int i = 0; i < na; i++) for (int k = 0; k < rb[i].cnt; k++) {
        uint32_t x = rd32(ra[i].v + 4 * k), y = rd32(rb[i].v + 4 * k);
        int shelf = rb[i].tag == 0x67 && rb[i].cnt >= 22 && k >= 2 && k < 22 && y;
        if (x != y) { changed++; CHECK(shelf, "shops: record %d value %d (a non-shelf) changed", i, k); }
        if (shelf) { pa[n] = x; pb[n++] = y; }
    }
    qsort(pa, (size_t)n, 4, cmp_u32); qsort(pb, (size_t)n, 4, cmp_u32);
    CHECK(!memcmp(pa, pb, (size_t)n * 4), "shops: not a permutation");
    CHECK(changed > n / 2, "shops: only %d of %d changed", changed, n);
    free(tmp);
    printf("shops seed %u: %d shelves, %d changed\n", seed, n, changed);
}

/* random encounters: a species always becomes the same other species, of about the same level, in both tables */
static void t_enc(uint32_t seed) {
    char sd[16]; snprintf(sd, sizeof sd, "%u", seed);
#ifdef _WIN32
    _putenv_s("DQIX_MOD_NZ_SEED", sd);
#else
    setenv("DQIX_MOD_NZ_SEED", sd, 1);
#endif
    build(0x40000u);
    CHECK(g_ready == 1, "enc: build failed");
    static uint16_t map[4096]; memset(map, 0, sizeof map);
    int changed = 0, slots = 0, bad = 0;
    for (int i = 0; i < 2; i++) {
        uint32_t z; uint8_t* o = orig_of(g_f[i].name, &z);
        CHECK(g_f[i].size == z, "enc: size of %s", g_f[i].name);
        for (uint32_t p = 0; p + 4 <= z; p += 4) {
            uint32_t a = rd32(o + p), b = rd32(g_f[i].data + p);
            if (a == b) continue;
            changed++;
            if ((a & ~0xFFFu) != (b & ~0xFFFu)) { bad++; continue; }
            uint32_t from = a & 0xFFF, to = b & 0xFFF;
            if (map[from] && map[from] != to) bad++;
            map[from] = (uint16_t)to; slots++;
            int lf, lt; if (!mon_level(from, &lf) || !mon_level(to, &lt)) bad++;
            else if ((lf == -99) != (lt == -99) || (lf != -99 && (lt < lf - 8 || lt > lf + 8))) bad++;
        }
    }
    CHECK(bad == 0, "enc: %d slots broke a rule (weights kept, one species -> one species, level band)", bad);
    CHECK(changed > 1000, "enc: only %d words changed", changed);
    printf("enc seed %u: %d words changed (%d monster slots)\n", seed, changed, slots);
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: t rom.nds\n"); return 2; }
    FILE* f = fopen(argv[1], "rb"); if (!f) { perror("rom"); return 2; }
    fseek(f, 0, SEEK_END); g_rom_size = (size_t)ftell(f); fseek(f, 0, SEEK_SET);
    g_rom = (uint8_t*)malloc(g_rom_size); if (fread(g_rom, 1, g_rom_size, f) != g_rom_size) return 2; fclose(f);
    printf("ROM %.4s\n", g_rom + 12);
    uint8_t *s1 = NULL, *s1b = NULL, *s2 = NULL; uint32_t z;
    t_skills(1, &s1); t_skills(1, &s1b); t_skills(2, &s2);
    orig_of("data/prm/skilltable.bin", &z);
    CHECK(!memcmp(s1, s1b, z), "skills: the same seed gave two results");
    CHECK(memcmp(s1, s2, z), "skills: another seed gave the same result");
    t_spells(1); t_spells(7);
    t_growth(1); t_growth(9);
    t_drops(1); t_drops(3);
    t_shops(1); t_shops(4);
    t_enc(1); t_enc(2);
    printf("%s (%d failed)\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
