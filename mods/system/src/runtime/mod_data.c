/* DQIX Enhanced mods: encounter tables for "Metal slimes only in the areas that have them" and
 * "Battle any monster you want".
 *
 * The monsters that roam a place are in three loose tables of the cartridge (see the DQIX wiki, "Encounters"):
 *   /data/prm/encfld.bin      by map and zone: tag 0x68 opens a zone, tag 0x67 is a monster that roams it
 *                             (the monster's number in the low 12 bits of the first value, its weight above)
 *   /data/prm/encbtl.bin      the same zones: tag 0x66 the roamers again, tag 0x67 the monsters that may join a battle
 *   /data/prm/fld_mondata.bin one tag 0x65 record per monster; value 1 is its level, -99 on the metal family
 *
 * The game reads the first two tables once, while it starts (found out by logging the cartridge reads of a headless run:
 * one pass each, at about frame 19), so these are launch options of the Cheats window, set when the game is started:
 *   DQIX_MOD_METAL=1   in every zone that has a metal monster among its roamers, every other roamer and companion becomes
 *                      that metal monster (the table keeps its size and layout; only the monster numbers change, the weights
 *                      stay). Zones without a metal monster are untouched.
 *   DQIX_MOD_FORCE=n   every roamer and companion of every zone becomes monster number n (bosses are not in these tables).
 * The ROM in memory is never changed: card.c calls mod_card_overlay after it filled its buffer and the changed copy of the
 * two tables is laid over it. In a session every player must start with the same choice, or the PCs read different tables.
 *
 * DQIX_MODLOG=1 prints what was handed out.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nds.h"


typedef struct { const char* name; uint32_t start, size; uint8_t* data; } MdFile;
static MdFile g_f[3] = { { "data/prm/encfld.bin" }, { "data/prm/encbtl.bin" }, { "data/prm/fld_mondata.bin" } };
static int g_ready;                                   /* 0 not built, 1 built, -1 can't */
static uint32_t g_key;                                /* what the built copies are for: 1 metal, 0x10000 + n force n */
static uint16_t g_metal[128];
static int g_nmetal;

static uint32_t rd32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }

/* NitroFS: a file's place in the ROM, by path */
static int lookup(const char* path, uint32_t* start, uint32_t* size) {
    if (!g_rom || g_rom_size < 0x50) return 0;
    uint32_t fnt = rd32(g_rom + 0x40), fat = rd32(g_rom + 0x48);
    uint16_t dir = 0xF000;
    const char* p = path;
    for (;;) {
        const char* slash = strchr(p, '/');
        size_t l = slash ? (size_t)(slash - p) : strlen(p);
        uint32_t base = fnt + (uint32_t)(dir & 0xFFF) * 8u;
        if (base + 8 > g_rom_size) return 0;
        uint32_t sub = rd32(g_rom + base); uint16_t fid; memcpy(&fid, g_rom + base + 4, 2);
        uint32_t q = fnt + sub; int found = 0;
        while (q < g_rom_size) {
            uint8_t b = g_rom[q++];
            if (!b) break;
            size_t nl = b & 0x7F;
            if (q + nl + 2 > g_rom_size) return 0;
            int match = nl == l && memcmp(g_rom + q, p, l) == 0;
            q += (uint32_t)nl;
            if (b & 0x80) {
                uint16_t sid; memcpy(&sid, g_rom + q, 2); q += 2;
                if (match && slash) { dir = sid; found = 1; break; }
            } else {
                if (match && !slash) {
                    uint32_t s = rd32(g_rom + fat + (uint32_t)fid * 8u), e = rd32(g_rom + fat + (uint32_t)fid * 8u + 4);
                    if (e <= s || e > g_rom_size) return 0;
                    *start = s; *size = e - s; return 1;
                }
                fid++;
            }
        }
        if (!found) return 0;
        p = slash + 1;
    }
}

/* the records of a tagged data table: header (records, string table offset, size, count), then u16 tag, u8 count,
 * two bits of type per value padded to a word, 4-byte values */
typedef void (*RecFn)(uint8_t* values, uint16_t tag, int cnt, void* ctx);
static void each_record(uint8_t* b, uint32_t size, RecFn fn, void* ctx) {
    if (size < 16) return;
    uint32_t stab = rd32(b + 4);
    if (stab > size) stab = size;
    uint32_t p = 16;
    while (p + 4 <= stab) {
        if (rd32(b + p) == 0xFFFFFFFFu) { p += 4; continue; }
        uint16_t tag = (uint16_t)(b[p] | b[p + 1] << 8);
        int cnt = b[p + 2];
        uint32_t tb = (uint32_t)(cnt * 2 + 7) / 8, hdr = ((3 + tb + 3) / 4) * 4;
        if (p + hdr + 4u * (uint32_t)cnt > stab) break;
        fn(b + p + hdr, tag, cnt, ctx);
        p += hdr + 4u * (uint32_t)cnt;
    }
}

static int is_metal(uint32_t mon) {
    for (int i = 0; i < g_nmetal; i++) if (g_metal[i] == mon) return 1;
    return 0;
}

static void metal_rec(uint8_t* v, uint16_t tag, int cnt, void* ctx) {
    (void)ctx;
    if (tag == 0x65 && cnt >= 3 && (int32_t)rd32(v + 4) == -99 && g_nmetal < 128) g_metal[g_nmetal++] = (uint16_t)(rd32(v) & 0xFFF);
}

#define ZMAX 256
typedef struct { int roam_tag, comp_tag, force; uint8_t* rec[ZMAX]; int roamer[ZMAX]; int n; int changed; } Zone;

static void zone_flush(Zone* z) {
    int m = z->force ? z->force : -1;
    for (int i = 0; i < z->n && m < 0; i++)
        if (z->roamer[i] && is_metal(rd32(z->rec[i]) & 0xFFF)) m = (int)(rd32(z->rec[i]) & 0xFFF);
    if (m >= 0)
        for (int i = 0; i < z->n; i++) {
            uint32_t w = rd32(z->rec[i]);
            if (z->force || !is_metal(w & 0xFFF)) { w = (w & ~0xFFFu) | (uint32_t)m; memcpy(z->rec[i], &w, 4); z->changed++; }
        }
    z->n = 0;
}

static void zone_rec(uint8_t* v, uint16_t tag, int cnt, void* ctx) {
    Zone* z = (Zone*)ctx;
    if (tag == 0x68 || tag == 0x69) { zone_flush(z); return; }
    if (cnt < 1 || z->n >= ZMAX) return;
    if (tag == z->roam_tag) { z->rec[z->n] = v; z->roamer[z->n++] = 1; }
    else if (tag == z->comp_tag) { z->rec[z->n] = v; z->roamer[z->n++] = 0; }
}

static void build(uint32_t key) {
    g_ready = -1; g_key = key;
    int force = key >= 0x10000u ? (int)(key & 0xFFF) : 0;
    for (int i = 0; i < 3; i++) {
        if (!lookup(g_f[i].name, &g_f[i].start, &g_f[i].size)) return;
        free(g_f[i].data);
        g_f[i].data = (uint8_t*)malloc(g_f[i].size);
        if (!g_f[i].data) return;
        memcpy(g_f[i].data, g_rom + g_f[i].start, g_f[i].size);
    }
    g_nmetal = 0;
    each_record(g_f[2].data, g_f[2].size, metal_rec, NULL);
    if (!g_nmetal) return;
    Zone z;
    memset(&z, 0, sizeof z); z.roam_tag = 0x67; z.comp_tag = -1; z.force = force;   /* encfld: tag 0x67 roams */
    each_record(g_f[0].data, g_f[0].size, zone_rec, &z); zone_flush(&z);
    int c0 = z.changed;
    memset(&z, 0, sizeof z); z.roam_tag = 0x66; z.comp_tag = 0x67; z.force = force;   /* encbtl: 0x66 roamers, 0x67 companions */
    each_record(g_f[1].data, g_f[1].size, zone_rec, &z); zone_flush(&z);
    g_ready = 1;
    if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod_data: %d metal monsters; %d roamer numbers changed in encfld, %d in encbtl\n", g_nmetal, c0, z.changed);
}

/* card.c, after it filled its buffer with the bytes at ROM address addr */
void mod_card_overlay(uint32_t addr, uint32_t len, uint8_t* buf) {
    static int init;
    static uint32_t key;                                  /* 0 off, 1 metal only, 0x10000 + n: everything is monster n */
    if (!init) {
        init = 1;
        const char* f = getenv("DQIX_MOD_FORCE");
        int n = f ? atoi(f) : 0;
        key = n > 0 && n < 4096 ? 0x10000u | (uint32_t)n : getenv("DQIX_MOD_METAL") ? 1u : 0u;
    }
    if (!len || !key) return;
    if (!g_ready || g_key != key) build(key);
    if (g_ready < 0) return;
    for (int i = 0; i < 2; i++) {
        const MdFile* f = &g_f[i];
        uint32_t lo = addr > f->start ? addr : f->start;
        uint32_t hi = addr + len < f->start + f->size ? addr + len : f->start + f->size;
        if (lo < hi) {
            memcpy(buf + (lo - addr), f->data + (lo - f->start), hi - lo);
            if (getenv("DQIX_MODLOG")) fprintf(stderr, "mod_data: %s bytes %u..%u handed out\n", f->name, lo - f->start, hi - f->start);
        }
    }
}
