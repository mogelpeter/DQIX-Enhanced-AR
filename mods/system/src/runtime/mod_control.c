/* Remote control for tests (tools/drive.py): with DQIX_CONTROL=<folder> the game runs only as far as it is told.
 * Without that variable this does nothing.
 *
 * Once per frame, from input_update(). When nothing is left to do, the game writes into the folder
 *   screen.ppm   both screens (256 x 384, as DQIX_DUMP)
 *   ram.bin      main RAM
 *   state.txt    "<number of the last command> <frame>"   (written last: the other two are complete then)
 * and waits for cmd.txt: the command's number (one more than before), then "quit" or one line per piece of input,
 *   "<frames> <buttons, KEYINPUT order as in input.c> <touch 0/1> <x> <y>".
 * DQIX_CONTROL_IDLE=<seconds>: a game nobody talks to for that long ends by itself. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nds.h"
#include "session.h"
#ifdef _WIN32
#include <windows.h>

typedef struct { int frames, keys, touch, x, y; } Seg;
static Seg* g_seg;
static int g_nseg, g_cap, g_at, g_left;
static unsigned g_seq;

static void save(const char* dir, const char* name, const void* head, size_t nhead, const void* body, size_t nbody) {
    char path[700]; snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE* f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "mod: control: cannot write %s\n", path); rt_exit(1); }
    fwrite(head, 1, nhead, f); fwrite(body, 1, nbody, f); fclose(f);
}

static void report(const char* dir) {
    static uint8_t rgb[2 * 256 * 192 * 3];
    for (int i = 0; i < 2 * 256 * 192; i++) {
        uint32_t c = g_screen[i / (256 * 192)][i % (256 * 192)];
        rgb[3 * i] = (uint8_t)(c >> 16); rgb[3 * i + 1] = (uint8_t)(c >> 8); rgb[3 * i + 2] = (uint8_t)c;
    }
    save(dir, "screen.ppm", "P6\n256 384\n255\n", 15, rgb, sizeof rgb);
    save(dir, "ram.bin", "", 0, g_main_ram, MAIN_RAM_SIZE);
    char line[64]; int n = snprintf(line, sizeof line, "%u %llu\n", g_seq, (unsigned long long)g_frame);
    save(dir, "state.tmp", line, (size_t)n, "", 0);
    char from[700], to[700];
    snprintf(from, sizeof from, "%s/state.tmp", dir); snprintf(to, sizeof to, "%s/state.txt", dir);
    for (int i = 0; i < 500 && !MoveFileExA(from, to, MOVEFILE_REPLACE_EXISTING); i++) Sleep(2);   /* the tool may be reading it */
    fflush(stderr);
}

/* the next command, if there is one: fills g_seg; "quit" ends the game */
static int take(const char* dir) {
    char path[700]; snprintf(path, sizeof path, "%s/cmd.txt", dir);
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    unsigned seq = 0; char line[128];
    if (!fgets(line, sizeof line, f) || sscanf(line, "%u", &seq) != 1 || seq <= g_seq) { fclose(f); return 0; }
    g_seq = seq; g_nseg = g_at = 0;
    while (fgets(line, sizeof line, f)) {
        if (!strncmp(line, "quit", 4)) { fclose(f); fprintf(stderr, "mod: control: quit\n"); rt_exit(0); }
        Seg s;
        if (sscanf(line, "%d %d %d %d %d", &s.frames, &s.keys, &s.touch, &s.x, &s.y) != 5 || s.frames <= 0) continue;
        if (g_nseg == g_cap) { g_cap = g_cap ? g_cap * 2 : 64; g_seg = realloc(g_seg, sizeof(Seg) * (size_t)g_cap); }
        g_seg[g_nseg++] = s;
    }
    fclose(f);
    return 1;
}

void mod_control(uint16_t* keys, int* touch, int* x, int* y) {
    static int init; static const char* dir; static unsigned long long idle;
    if (!init) {
        init = 1; dir = session_hidden() ? NULL : getenv("DQIX_CONTROL");
        const char* e = getenv("DQIX_CONTROL_IDLE"); idle = e ? strtoull(e, NULL, 10) * 1000 : 1800000;
    }
    if (!dir) return;
    while (!g_left) {
        if (g_at < g_nseg) { g_left = g_seg[g_at].frames; break; }
        report(dir);
        unsigned long long since = GetTickCount64();
        while (!take(dir)) {
            if (GetTickCount64() - since > idle) { fprintf(stderr, "mod: control: nobody asked for anything, ending\n"); rt_exit(0); }
            Sleep(5);
        }
        if (!g_nseg) continue;                                  /* an empty command: report again */
    }
    const Seg* s = &g_seg[g_at];
    *keys |= (uint16_t)s->keys;
    if (s->touch) { *touch = 1; *x = s->x; *y = s->y; }
    if (!--g_left) g_at++;
}
#else
void mod_control(uint16_t* keys, int* touch, int* x, int* y) { (void)keys; (void)touch; (void)x; (void)y; }
#endif
