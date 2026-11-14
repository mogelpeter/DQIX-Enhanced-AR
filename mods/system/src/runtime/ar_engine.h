/* Action Replay DS code interpreter, working on a game's main RAM through
 * callbacks (so it can run against another process, or a test array).
 *
 * Only main RAM (0x02000000-0x023FFFFF, mirrored to 0x027FFFFF) is real.
 * The DS key registers aren't in memory in DQIX Enhanced (the runtime makes
 * them up when the game reads them), so key conditions are answered from
 * `keys`, given by the caller: the buttons held now, a bit each in the DS's
 * order (A B SELECT START RIGHT LEFT UP DOWN R L X Y, bit set = held), or
 * AR_KEYS_ALL for "every key the code asks for is held" (used when a code is
 * fired once from the Cheats window).
 *
 * A code can't hold the game up: a pass stops after AR_BUDGET steps (a loop
 * count gone wrong would otherwise freeze the frame it runs in). Nothing but
 * main RAM is ever written.
 */
#ifndef AR_ENGINE_H
#define AR_ENGINE_H
#include <stdint.h>
#include <stddef.h>

typedef struct {
    void* user;
    int (*read)(void* user, uint32_t ds_addr, void* out, size_t n);   /* 1 = ok */
    int (*write)(void* user, uint32_t ds_addr, const void* in, size_t n);
} ArMem;

typedef struct { uint32_t a, b; } ArOp;

static int ar_is_ram(uint32_t a) { return (a >> 24) == 0x02; }
static int ar_is_keyreg(uint32_t a) {
    return a == 0x04000130 || a == 0x04000136 || (a & 0x0FFFFFFF) == 0x027FFFA8;
}
#define AR_KEYS_ALL (-1)
#define AR_BUDGET   400000
/* what the game would read from a key register with `keys` held (a held key reads as 0) */
static uint32_t ar_keyreg(uint32_t a, int keys) {
    if (a == 0x04000130) return ~(uint32_t)keys & 0x3FF;
    if (a == 0x04000136) return 0x7F & ~((uint32_t)keys >> 10 & 3);          /* X, Y; pen up */
    return 0x2C00 & ~(((uint32_t)keys >> 10 & 3) << 10);                     /* the copy in RAM: X, Y */
}

static uint32_t ar_r32(ArMem* m, uint32_t a) { uint32_t v = 0; if (ar_is_ram(a)) m->read(m->user, a, &v, 4); return v; }
static uint32_t ar_r16(ArMem* m, uint32_t a) { uint16_t v = 0; if (ar_is_ram(a)) m->read(m->user, a, &v, 2); return v; }
static uint32_t ar_r8 (ArMem* m, uint32_t a) { uint8_t  v = 0; if (ar_is_ram(a)) m->read(m->user, a, &v, 1); return v; }
static void ar_w32(ArMem* m, uint32_t a, uint32_t v) { if (ar_is_ram(a)) m->write(m->user, a, &v, 4); }
static void ar_w16(ArMem* m, uint32_t a, uint32_t v) { uint16_t x = (uint16_t)v; if (ar_is_ram(a)) m->write(m->user, a, &x, 2); }
static void ar_w8 (ArMem* m, uint32_t a, uint32_t v) { uint8_t  x = (uint8_t)v;  if (ar_is_ram(a)) m->write(m->user, a, &x, 1); }

/* Runs one pass of a code (what an Action Replay does once per frame). */
static void ar_run(ArMem* m, const ArOp* ops, int n, int keys) {
    uint32_t offset = 0, data = 0;
    uint32_t budget = AR_BUDGET;
    int skip = 0;                    /* > 0: inside that many failed (or nested) conditions */
    int loop_start = -1; uint32_t loop_left = 0; int loop_skip = 0;
    for (int pc = 0; pc < n; pc++) {
        uint32_t a = ops[pc].a, b = ops[pc].b;
        uint32_t t = a >> 28, top = a >> 24;
        uint32_t addr = a & 0x0FFFFFFF;

        if (!budget--) return;
        if (skip) {                  /* only track nesting while skipping */
            if (t >= 0x3 && t <= 0xA) skip++;
            else if (top == 0xD0) skip--;
            else if (top == 0xD1 || top == 0xD2) {
                /* the end of a loop or of the code: conditions end here */
                skip = 0;
                if (top == 0xD2 && loop_start < 0) { offset = 0; data = 0; }
                if (loop_start >= 0) {
                    if (loop_left > 0) { loop_left--; skip = loop_skip; pc = loop_start; continue; }
                    loop_start = -1;
                    if (top == 0xD2) { offset = 0; data = 0; }
                }
            }
            else if (t == 0xE) pc += (int)((b + 7) / 8);     /* E's data lines aren't codes */
            continue;
        }

        if (t <= 0x2 || (t >= 0x3 && t <= 0xA) || t == 0xB) {
            if (t <= 0x2 || t == 0xB) addr += offset;   /* B: offset = word at [address + offset] (Action Replay DS) */
            else if (addr == 0) addr = offset;   /* conditions on address 0 use the offset */
        }
        switch (t) {
        case 0x0: ar_w32(m, addr, b); break;
        case 0x1: ar_w16(m, addr, b); break;
        case 0x2: ar_w8(m, addr, b); break;
        case 0x3: case 0x4: case 0x5: case 0x6: {
            if (ar_is_keyreg(addr) && keys == AR_KEYS_ALL) break;
            uint32_t v = ar_is_keyreg(addr) ? ar_keyreg(addr, keys) : ar_r32(m, addr);
            int ok = t == 3 ? b > v : t == 4 ? b < v : t == 5 ? b == v : b != v;
            if (!ok) skip = 1;
            break;
        }
        case 0x7: case 0x8: case 0x9: case 0xA: {
            if (ar_is_keyreg(addr) && keys == AR_KEYS_ALL) break;
            uint32_t v = (ar_is_keyreg(addr) ? ar_keyreg(addr, keys) : ar_r16(m, addr)) & ~(b >> 16) & 0xFFFF, y = b & 0xFFFF;
            int ok = t == 7 ? y > v : t == 8 ? y < v : t == 9 ? y == v : y != v;
            if (!ok) skip = 1;
            break;
        }
        case 0xB: offset = ar_r32(m, addr); break;
        case 0xC:
            if (top == 0xC0) { loop_start = pc; loop_left = b; loop_skip = 0; }
            break;
        case 0xD:
            switch (top) {
            case 0xD0: break;                                   /* end of a condition (that held) */
            case 0xD1: case 0xD2:
                if (loop_start >= 0) {
                    if (loop_left > 0) { loop_left--; pc = loop_start; break; }
                    loop_start = -1;
                }
                if (top == 0xD2) { offset = 0; data = 0; }
                break;
            case 0xD3: offset = b; break;
            case 0xD4: data += b; break;
            case 0xD5: data = b; break;
            case 0xD6: ar_w32(m, b + offset, data); offset += 4; break;
            case 0xD7: ar_w16(m, b + offset, data); offset += 2; break;
            case 0xD8: ar_w8(m, b + offset, data); offset += 1; break;
            case 0xD9: data = ar_r32(m, b + offset); break;
            case 0xDA: data = ar_r16(m, b + offset); break;
            case 0xDB: data = ar_r8(m, b + offset); break;
            case 0xDC: offset += b; break;
            }
            break;
        case 0xE: {                  /* E: write the next b bytes (in the following lines) */
            uint32_t dst = addr + offset;
            uint32_t i = 0;
            for (int l = pc + 1; l < n && i < b; l++) {
                uint32_t w[2] = { ops[l].a, ops[l].b };
                if (budget < 8) return;
                budget -= 8;
                for (int k = 0; k < 2 && i < b; k++)
                    for (int s = 0; s < 4 && i < b; s++, i++) ar_w8(m, dst + i, (w[k] >> (8 * s)) & 0xFF);   /* little-endian words */
            }
            pc += (int)((b + 7) / 8);
            break;
        }
        case 0xF:                    /* F: copy b bytes from the offset to the address */
            if (b > budget) return;
            budget -= b;
            for (uint32_t i = 0; i < b; i++) ar_w8(m, addr + i, ar_r8(m, offset + i));
            break;
        }
    }
}
#endif
