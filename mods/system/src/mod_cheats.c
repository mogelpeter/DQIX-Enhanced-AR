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
 * window (mods/system/src/cheats.c) puts it in a mailbox, this console sends it in
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
 * with each op as four words (address low, high, value low, high).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nds.h"
#include "session.h"
#include "ar_engine.h"
#ifdef _WIN32
#include <windows.h>
#endif

#define MC_MAGIC   0x43584451u         /* "DQXC" */
#define MC_VERSION 2                   /* 2: codes that are on see the buttons; 128 at a time */
#define MC_RING    8192
#define MC_EVENT   (1u << 30)
#define MC_SLOTS   128
#define MC_MAXLEN  0xFFF

/* the mailbox, shared with the cheat window (the same in mods/system/src/cheats.c) */
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
}
#endif

/* ---- the DS's memory, for the code interpreter ---- */
static int mc_read(void* u, uint32_t a, void* out, size_t n) {
    (void)u; a &= MAIN_RAM_SIZE - 1;
    if (a + n > MAIN_RAM_SIZE) return 0;
    memcpy(out, &g_main_ram[a], n); return 1;
}
/* A switch, not memory: a code that writes this address (mods/cheats/lower-level-more-exp.txt)
 * turns "lower-level characters get more experience" on for this frame (lowexp.c reads it).
 * It is cleared at the start of every frame and set again by the code while that is on, so it
 * is the same on every PC of a session. */
uint8_t g_mod_lowexp;
#define MC_SWITCH_LOWEXP 0x02F5A5A0u

static int mc_write(void* u, uint32_t a, const void* in, size_t n) {
    (void)u;
    if ((a & 0x0FFFFFFFu) == MC_SWITCH_LOWEXP) { g_mod_lowexp = 1; return 1; }
    a &= MAIN_RAM_SIZE - 1;
    if (a + n > MAIN_RAM_SIZE) return 0;
    memcpy(&g_main_ram[a], in, n); return 1;
}
static ArMem g_mem = { NULL, mc_read, mc_write };

/* ---- this console's cheats: the same on every PC, because they only ever
 * change through its input stream ---- */
typedef struct { int used; uint16_t id; int nops; ArOp* ops; } McSlot;
static McSlot g_slot[MC_SLOTS];
static uint16_t g_msg[MC_MAXLEN];
static int g_type, g_len, g_got;       /* the message being received */
static uint32_t g_done;

static void mc_forget(void) {
    for (int i = 0; i < MC_SLOTS; i++) { free(g_slot[i].ops); memset(&g_slot[i], 0, sizeof g_slot[i]); }
    g_type = g_len = g_got = 0;
    g_mod_lowexp = 0;
}

static ArOp* mc_ops(const uint16_t* w, int nops) {
    ArOp* ops = (ArOp*)calloc((size_t)(nops ? nops : 1), sizeof *ops);
    if (!ops) return NULL;
    for (int i = 0; i < nops; i++, w += 4) {
        ops[i].a = (uint32_t)w[0] | (uint32_t)w[1] << 16;
        ops[i].b = (uint32_t)w[2] | (uint32_t)w[3] << 16;
    }
    return ops;
}

static void mc_message(void) {
    switch (g_type) {
    case 1: {
        int n = g_len / 4; ArOp* ops = mc_ops(g_msg, n);
        if (ops) ar_run(&g_mem, ops, n, AR_KEYS_ALL);
        free(ops);
        break;
    }
    case 2: {
        if (g_len < 1) break;
        uint16_t id = g_msg[0]; int at = -1;
        for (int i = 0; i < MC_SLOTS; i++) if (g_slot[i].used && g_slot[i].id == id) { at = i; break; }
        for (int i = 0; i < MC_SLOTS && at < 0; i++) if (!g_slot[i].used) at = i;
        if (at < 0) break;
        free(g_slot[at].ops);
        g_slot[at].used = 1; g_slot[at].id = id; g_slot[at].nops = (g_len - 1) / 4;
        g_slot[at].ops = mc_ops(g_msg + 1, g_slot[at].nops);
        if (!g_slot[at].ops) memset(&g_slot[at], 0, sizeof g_slot[at]);
        break;
    }
    case 3:
        for (int i = 0; i < MC_SLOTS; i++) if (g_len >= 1 && g_slot[i].used && g_slot[i].id == g_msg[0]) { free(g_slot[i].ops); memset(&g_slot[i], 0, sizeof g_slot[i]); }
        break;
    case 4: mc_forget(); break;
    }
    g_done++;
    g_type = g_len = g_got = 0;
}

static void mc_word(uint16_t w) {
    if (!g_type) {
        int t = w >> 12;
        if (t < 1 || t > 4) return;                      /* not a header: skip it */
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
        if (g_box) { g_box->rd = g_box->wr; g_box->gen++; }
        last_ses = ses;
    }
    last_frame = g_frame;
    if (g_box) { g_box->session = (uint32_t)ses; g_box->frame = (uint32_t)g_frame; }
}

/* input.c, every frame: `local` is what the player presses now. If the cheat
 * window has something to send, this frame carries 16 bits of it. */
uint32_t mod_cheats_out(uint32_t local) {
    static int sending, waited;
    mc_sync();
    if (!g_box || session_hidden() || rt_hosted()) return local;
    uint32_t rd = g_box->rd;
    if (rd == g_box->wr) { sending = 0; waited = 0; return local; }
    /* don't lift the stylus in the middle of a stroke if a short wait avoids it */
    if (!sending && (local & (1u << 13)) && waited < 30) { waited++; return local; }
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
    int keys = (int)(v & 0xFFF);                         /* this console's buttons this frame: the same on every PC */
    for (int i = 0; i < MC_SLOTS; i++) if (g_slot[i].used) ar_run(&g_mem, g_slot[i].ops, g_slot[i].nops, keys);
    if (g_box) g_box->done = g_done;
    return v;
}
