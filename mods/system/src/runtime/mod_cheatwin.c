/* DQIX Enhanced mods: the Cheats window inside the emulator (menu bar: Cheats > Cheats...).
 *
 * It shows the cheat list (mods\system\bin\catalog.txt, made by tools\catalog.py), keeps the switches in the state file
 * (mods\system\menu-state.txt) and puts live cheats into the game through the cheat mailbox, from inside the game's own
 * process, so there is no second program, no restart and, with the live code mods (livepatch.c), no rebuild:
 * a switch is on the moment you click it.
 *
 *   mod_cheatwin_boot()  at program start (mod_cheats.c): sets the options for the next start from the state file
 *                        and starts a thread that (re)sends every cheat that is on whenever the game forgot them
 *                        (new start, a session began or ended).
 *   mod_cheatwin_show()  menu bar: opens the window (a thread of its own; the game keeps running).
 *
 * Windows only; elsewhere the functions do nothing. Plain Win32 (owner-drawn page list, check boxes, drop-downs), so it needs nothing the game doesn't have.
 */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <winhttp.h>
#include "session.h"

int mod_cheats_post(const uint16_t* w, int n);       /* mod_cheats.c: words into the mailbox's ring; 0 = full or no mailbox */
uint32_t mod_cheats_gen(void);                       /* goes up whenever the game forgot every cheat */

typedef struct { char *id, *cat, *group, *kind, *status, *name, *option, *note, *mode, *keys, *env, *also, *file, *section, *who, *scope; int on, nops, undo; uint32_t* ops;
                 int gi; char* hay; char* about; } Ent;                        /* gi: index into g_g or -1; hay: the search text, lower case */
typedef struct { char *id, *cat, *title, *kind, *about; char* lt; int* mem; int nmem; } Grp;   /* lt: title lower case; mem: its entries */
typedef struct { char *cat, *title; } Sec;                                      /* a section of a page (folds open and shut), in the order shown */

static Ent* g_e; static int g_ne;
static Grp* g_g; static int g_ng;
static char** g_pg; static int g_npg;
static Sec* g_sec; static int g_nsec;
static char** g_st; static int g_nst;                /* the state file: lines "<kind> <id>" (live, code, launch, flag) */
static char g_root[MAX_PATH * 2], g_statepath[MAX_PATH * 2];
static CRITICAL_SECTION g_cs;
static int g_cs_init, g_loaded;
/* The window has two faces: the Cheats window (every page but Nuzlocke) and the Nuzlocke window (menu bar: Nuzlocke > Settings...), which shows only the
 * Nuzlocke page. They are the same window and the same state file; each leaves the other's cheats alone (Enabled, search). */
static int g_mode;                                  /* 0 Cheats, 1 Nuzlocke */
/* who is really there (mod_cheats.c mod_roster), polled while the window is open: a cheat for party member 2..4 or for an enemy is shown only
 * while that member / enemy exists; the live battle cheats only in a battle */
typedef struct { int inbattle; uint8_t party[4], enemy[6]; char name[4][12]; int enemy_hp[6]; int hp[4], mp[4], hpmax[4], mpmax[4], enemy_max_hp[6], enemy_max_mp[6]; } ModRoster;
void mod_roster(ModRoster* r);
static ModRoster g_ro;
static int who_ok(const Ent* e) {
    if (!strcmp(e->cat, "Live battle") && !g_ro.inbattle) return 0;
    if (!e->who[0]) return 1;
    int n = e->who[1] - '1';
    if (e->who[0] == 'p') {
        if (!(n >= 0 && n < 4 && g_ro.party[n])) return 0;
        if (strstr(e->id, ":revive")) return g_ro.inbattle && g_ro.hpmax[n] > 0 && g_ro.hp[n] == 0;      /* only for a fallen member */
        return 1;
    }
    if (e->who[0] == 'e') return g_ro.inbattle && n >= 0 && n < 6 && g_ro.enemy[n];
    return 1;
}
static int in_face(const Ent* e) { return g_mode == 1 ? !strcmp(e->cat, "Nuzlocke") || !strcmp(e->also, "Nuzlocke") : g_mode == 2 ? !strcmp(e->cat, "Live battle") : !(!strcmp(e->cat, "Nuzlocke") || !strcmp(e->also, "Nuzlocke")); }
static int is_nz(const Ent* e) { return !strcmp(e->cat, "Nuzlocke") || !strcmp(e->also, "Nuzlocke"); }
static int face_id(const char* id) { return !strncmp(id, "file:cheats/nuzlocke", 20) || !strncmp(id, "launch:nz-", 10) || !strncmp(id, "now:file:cheats/nuzlocke", 24) ? 1 : !strncmp(id, "live:battle:", 12) || !strncmp(id, "now:live:battle:", 16) ? 2 : 0; }

static char* xdup(const char* s, size_t n) { char* p = (char*)malloc(n + 1); if (!p) return NULL; memcpy(p, s, n); p[n] = 0; return p; }

/* ---- the project folder: ...\DQIX-Enhanced\game\dqix.exe -> ...\DQIX-Enhanced ---- */
static int find_root(void) {
    if (g_root[0]) return 1;
    char exe[MAX_PATH * 2]; DWORD n = GetModuleFileNameA(NULL, exe, sizeof exe);
    if (!n || n >= sizeof exe) return 0;
    for (int up = 0; up < 3; up++) {
        char* s = strrchr(exe, '\\'); if (!s) return 0; *s = 0;
        char cat[MAX_PATH * 2 + 64]; snprintf(cat, sizeof cat, "%s\\mods\\system\\bin\\catalog.txt", exe);
        if (GetFileAttributesA(cat) != INVALID_FILE_ATTRIBUTES) {
            snprintf(g_root, sizeof g_root, "%s", exe);
            const char* o = getenv("DQIX_MENU_STATE");
            if (o && *o) snprintf(g_statepath, sizeof g_statepath, "%s", o);
            else snprintf(g_statepath, sizeof g_statepath, "%s\\mods\\system\\menu-state.txt", exe);
            return 1;
        }
    }
    return 0;
}

static char* slurp(const char* path, size_t* len) {
    FILE* f = fopen(path, "rb"); if (!f) return NULL;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    char* b = (char*)malloc((size_t)n + 1); if (!b) { fclose(f); return NULL; }
    size_t got = fread(b, 1, (size_t)n, f); fclose(f); b[got] = 0; if (len) *len = got; return b;
}

/* ---- the catalog ---- */
static char* kv(char** tok, int nt, const char* key) {
    size_t kl = strlen(key);
    for (int i = 0; i < nt; i++) if (!strncmp(tok[i], key, kl) && tok[i][kl] == '=') return xdup(tok[i] + kl + 1, strlen(tok[i] + kl + 1));
    return xdup("", 0);
}

static void load_catalog(void) {
    if (g_loaded || !find_root()) return;
    char path[MAX_PATH * 2 + 64]; snprintf(path, sizeof path, "%s\\mods\\system\\bin\\catalog.txt", g_root);
    char* text = slurp(path, NULL); if (!text) return;
    int cap_e = 0, cap_g = 0, cap_p = 0;
    for (char* line = text; line && *line;) {
        char* nl = strchr(line, '\n'); if (nl) *nl = 0;
        size_t ll = strlen(line); if (ll && line[ll - 1] == '\r') line[ll - 1] = 0;
        char* tok[40]; int nt = 0;
        for (char* p = line; p && nt < 40;) { tok[nt++] = p; char* t = strchr(p, '\t'); if (!t) break; *t = 0; p = t + 1; }
        if (nt >= 1 && !strcmp(tok[0], "page")) {
            if (g_npg == cap_p) { cap_p = cap_p ? cap_p * 2 : 16; g_pg = (char**)realloc(g_pg, (size_t)cap_p * sizeof *g_pg); }
            g_pg[g_npg++] = kv(tok + 1, nt - 1, "title");
        } else if (nt >= 1 && !strcmp(tok[0], "section")) {
            g_sec = (Sec*)realloc(g_sec, (size_t)(g_nsec + 1) * sizeof *g_sec);
            g_sec[g_nsec].cat = kv(tok + 1, nt - 1, "cat"); g_sec[g_nsec].title = kv(tok + 1, nt - 1, "title"); g_nsec++;
        } else if (nt >= 1 && !strcmp(tok[0], "group")) {
            if (g_ng == cap_g) { cap_g = cap_g ? cap_g * 2 : 32; g_g = (Grp*)realloc(g_g, (size_t)cap_g * sizeof *g_g); }
            Grp* g = &g_g[g_ng++];
            g->id = kv(tok + 1, nt - 1, "id"); g->cat = kv(tok + 1, nt - 1, "cat"); g->title = kv(tok + 1, nt - 1, "title"); g->kind = kv(tok + 1, nt - 1, "kind");
            g->about = kv(tok + 1, nt - 1, "about");
        } else if (nt >= 1 && !strcmp(tok[0], "entry")) {
            if (g_ne == cap_e) { cap_e = cap_e ? cap_e * 2 : 256; g_e = (Ent*)realloc(g_e, (size_t)cap_e * sizeof *g_e); }
            Ent* e = &g_e[g_ne++]; memset(e, 0, sizeof *e);
            char** t = tok + 1; int n = nt - 1;
            e->id = kv(t, n, "id"); e->cat = kv(t, n, "cat"); e->group = kv(t, n, "group"); e->kind = kv(t, n, "kind"); e->status = kv(t, n, "status");
            e->name = kv(t, n, "name"); e->option = kv(t, n, "option"); e->note = kv(t, n, "note"); e->mode = kv(t, n, "mode"); e->keys = kv(t, n, "keys");
            e->env = kv(t, n, "env"); e->also = kv(t, n, "also"); e->file = kv(t, n, "file"); e->about = kv(t, n, "about");
            e->section = kv(t, n, "section"); e->who = kv(t, n, "who"); e->scope = kv(t, n, "scope");
            char* on = kv(t, n, "on"); e->on = on[0] == '1'; free(on);
            char* un = kv(t, n, "undo"); e->undo = un[0] == '1'; free(un);
            char* ops = kv(t, n, "ops");
            if (ops[0]) {
                int cnt = 1; for (char* c = ops; *c; c++) if (*c == ',') cnt++;
                e->ops = (uint32_t*)calloc((size_t)cnt * 2, 4);
                char* p = ops;
                while (e->ops && *p && e->nops < cnt) {
                    char* end; unsigned long a = strtoul(p, &end, 16); if (*end != ':') break;
                    unsigned long b = strtoul(end + 1, &end, 16);
                    e->ops[e->nops * 2] = (uint32_t)a; e->ops[e->nops * 2 + 1] = (uint32_t)b; e->nops++;
                    p = (*end == ',') ? end + 1 : end;
                    if (*end != ',') break;
                }
            }
            free(ops);
        }
        line = nl ? nl + 1 : NULL;
    }
    free(text);
    /* once: each entry's group, each group's members, and the lower-case text the search looks through */
    for (int k = 0; k < g_ng; k++) {
        Grp* g = &g_g[k]; g->mem = NULL; g->nmem = 0;
        g->lt = xdup(g->title, strlen(g->title)); for (char* c = g->lt; *c; c++) if ((unsigned char)*c < 128) *c = (char)tolower((unsigned char)*c);
    }
    for (int i = 0; i < g_ne; i++) {
        Ent* e = &g_e[i]; e->gi = -1;
        if (e->group[0]) for (int k = 0; k < g_ng; k++) if (!strcmp(g_g[k].id, e->group)) { e->gi = k; break; }
        if (e->gi >= 0 && strcmp(e->kind, "blocked")) { Grp* g = &g_g[e->gi]; g->mem = (int*)realloc(g->mem, (size_t)(g->nmem + 1) * sizeof *g->mem); g->mem[g->nmem++] = i; }
        size_t n = strlen(e->name) + strlen(e->option) + strlen(e->note) + strlen(e->cat) + strlen(e->also) + strlen(e->keys) + 8;
        e->hay = (char*)malloc(n);
        if (e->hay) {
            snprintf(e->hay, n, "%s %s %s %s %s %s", e->name, e->option, e->note, e->cat, e->also, e->keys);
            for (char* c = e->hay; *c; c++) if ((unsigned char)*c < 128) *c = (char)tolower((unsigned char)*c);
        }
    }
    g_loaded = 1;
}

/* ---- the state file ---- */
static void load_state(void) {
    char* text = slurp(g_statepath, NULL);
    for (int i = 0; i < g_nst; i++) free(g_st[i]);
    free(g_st); g_st = NULL; g_nst = 0;
    if (!text) return;
    int cap = 0;
    for (char* line = text; line && *line;) {
        char* nl = strchr(line, '\n'); if (nl) *nl = 0;
        size_t ll = strlen(line); while (ll && (line[ll - 1] == '\r' || line[ll - 1] == ' ')) line[--ll] = 0;
        if (ll) { if (g_nst == cap) { cap = cap ? cap * 2 : 64; g_st = (char**)realloc(g_st, (size_t)cap * sizeof *g_st); } g_st[g_nst++] = xdup(line, ll); }
        line = nl ? nl + 1 : NULL;
    }
    free(text);
}

static int st_find(const char* kind, const char* id) {
    char want[256]; snprintf(want, sizeof want, "%s %s", kind, id);
    for (int i = 0; i < g_nst; i++) if (!strcmp(g_st[i], want)) return i;
    return -1;
}
static int st_has(const char* kind, const char* id) { return st_find(kind, id) >= 0; }

static int g_overlay;                                         /* a guest shows the host's cheats: the user's own switches are kept aside and never written */
static void st_save(void) {
    if (g_overlay) return;
    FILE* f = fopen(g_statepath, "wb"); if (!f) return;
    for (int i = 0; i < g_nst; i++) fprintf(f, "%s\r\n", g_st[i]);
    fclose(f);
}

static void st_set(const char* kind, const char* id, int on) {
    int at = st_find(kind, id);
    if (on && at < 0) {
        g_st = (char**)realloc(g_st, (size_t)(g_nst + 1) * sizeof *g_st);
        char line[300]; snprintf(line, sizeof line, "%s %s", kind, id);
        g_st[g_nst++] = xdup(line, strlen(line));
    } else if (!on && at >= 0) {
        free(g_st[at]); memmove(&g_st[at], &g_st[at + 1], (size_t)(g_nst - at - 1) * sizeof *g_st); g_nst--;
    }
}

static const char* skind(const Ent* e) { return !strcmp(e->kind, "live") ? "live" : !strcmp(e->kind, "code") ? "code" : "launch"; }

static int ent_on(const Ent* e) { return st_has(skind(e), e->id); }

/* code mods that now switch live (livepatch.c): what the state file lists as "code" is "live" */
static void migrate_state(void) {
    int changed = 0;
    for (int i = 0; i < g_ne; i++) {
        if (strcmp(g_e[i].kind, "live")) continue;
        if (st_has("code", g_e[i].id)) { st_set("code", g_e[i].id, 0); st_set("live", g_e[i].id, 1); changed = 1; }
    }
    if (changed) st_save();
}

/* ---- a session is running: what would put the PCs out of sync can't be changed. A live cheat travels in the player's input stream, so every PC
 * carries out the same change on the same frame; a launch option or a code mod that needs a rebuild changes how the game starts or computes, and
 * a PC that had it different from the others would drift apart (desync). Those rows are greyed out and say why. */
static volatile LONG g_ses;                                   /* 1 while a session runs (the agent thread keeps it) */
static const char* lock_why_kind(const char* kind) {
    return !strcmp(kind, "launch")
        ? "Locked while you play with friends: it only takes effect when the game starts, and every PC has to start with the same setting or the session goes out of sync. Change it before the session."
        : "Locked while you play with friends: it changes how the game computes, so every PC has to have the same build or the session goes out of sync. Change it before the session.";
}
static int locked(const Ent* e) { return g_ses && (!strcmp(e->kind, "launch") || !strcmp(e->kind, "code")); }
static const char* lock_why(const Ent* e) { return lock_why_kind(e->kind); }

/* ---- sending cheats (the mailbox's messages, see mod_cheats.c) ---- */
static void post_words(const uint16_t* w, int n) {
    for (int tries = 0; tries < 400; tries++) { if (mod_cheats_post(w, n)) return; Sleep(10); }
}
static void send_raw(uint16_t id, int undo, const uint32_t* ops, int nops) {
    int n = 1 + 4 * nops;
    if (n > 0xFFF || !nops) return;
    uint16_t* w = (uint16_t*)malloc((size_t)(n + 1) * 2); if (!w) return;
    w[0] = (uint16_t)((undo ? 5 : 2) << 12 | n); w[1] = id;      /* 5: SET_UNDO, switching off puts its changes back */
    for (int i = 0; i < nops; i++) {
        uint32_t a = ops[i * 2], b = ops[i * 2 + 1];
        w[2 + i * 4] = (uint16_t)a; w[3 + i * 4] = (uint16_t)(a >> 16); w[4 + i * 4] = (uint16_t)b; w[5 + i * 4] = (uint16_t)(b >> 16);
    }
    post_words(w, n + 1); free(w);
}
static void send_clear_id(uint16_t id) {
    uint16_t w[2] = { (uint16_t)(3 << 12 | 1), id };
    post_words(w, 2);
}
static void send_set(int idx) { Ent* e = &g_e[idx]; send_raw((uint16_t)(idx + 1), e->undo, e->ops, e->nops); }
static void send_run(int idx) {
    Ent* e = &g_e[idx]; int n = 4 * e->nops;
    if (n > 0xFFF || !e->nops) return;
    uint16_t* w = (uint16_t*)malloc((size_t)(n + 1) * 2); if (!w) return;
    w[0] = (uint16_t)(1 << 12 | n);
    for (int i = 0; i < e->nops; i++) {
        uint32_t a = e->ops[i * 2], b = e->ops[i * 2 + 1];
        w[1 + i * 4] = (uint16_t)a; w[2 + i * 4] = (uint16_t)(a >> 16); w[3 + i * 4] = (uint16_t)b; w[4 + i * 4] = (uint16_t)(b >> 16);
    }
    post_words(w, n + 1); free(w);
}
static void send_clear(int idx) { send_clear_id((uint16_t)(idx + 1)); }

/* every live cheat that is on, again (the game started, or forgot them) */
static void resend_all(void) {
    if (!g_cs_init) return;
    EnterCriticalSection(&g_cs);
    for (int i = 0; i < g_ne; i++)
        if (!strcmp(g_e[i].kind, "live") && strcmp(g_e[i].mode, "once") && ent_on(&g_e[i])) send_set(i);
    LeaveCriticalSection(&g_cs);
}

/* ---- a guest takes the host's cheats (the host's console copy on this PC has them: mod_cheats.c, hc_publish). While the session runs the window
 * shows the host's cheats as the switches that are on and sends them in this player's own stream, so the guest can switch any of them off (a
 * live cheat can't put a session out of sync: it travels in the stream). The guest's own switches are kept aside in memory (g_st_saved) and are
 * never written (st_save does nothing meanwhile); when the session ends they come back and are sent again. Changes the host makes later follow.
 * A host cheat this game doesn't have in its list is sent as it is (ids from 0x8000) and can't be switched here. DQIX_AR_NO_HOST_CHEATS=1: off. */
uint32_t mod_hostcheats_copy(uint8_t* out, uint32_t* used, uint32_t* n);
#define HC_CAP (1u << 19)
#define HOST_ID 0x8000u
typedef struct { uint16_t id; uint32_t h; int idx; } Mir;
static Mir g_mir[128]; static int g_nmir; static uint32_t g_mir_seq;
static char** g_st_saved; static int g_nst_saved;
static void follow_note(const wchar_t* t);
static void refresh_ui(void);
static uint32_t ops_hash(const uint32_t* ops, uint32_t nops) { uint32_t h = 2166136261u; for (uint32_t i = 0; i < nops * 2; i++) h = (h ^ ops[i]) * 16777619u; return h; }
static void overlay_enter(void) {
    EnterCriticalSection(&g_cs);
    g_st_saved = g_st; g_nst_saved = g_nst;
    g_st = (char**)malloc((size_t)(g_nst_saved + 1) * sizeof *g_st);
    for (int i = 0; i < g_nst_saved; i++) g_st[i] = xdup(g_st_saved[i], strlen(g_st_saved[i]));
    g_overlay = 1;                                              /* from here on nothing is written to menu-state.txt */
    for (int i = 0; i < g_ne; i++) if (!strcmp(g_e[i].kind, "live") && ent_on(&g_e[i])) st_set("live", g_e[i].id, 0);
    LeaveCriticalSection(&g_cs);
}
static void overlay_leave(void) {
    EnterCriticalSection(&g_cs);
    if (g_overlay) {
        for (int i = 0; i < g_nst; i++) free(g_st[i]);
        free(g_st); g_st = g_st_saved; g_nst = g_nst_saved; g_st_saved = NULL; g_nst_saved = 0; g_overlay = 0;
    }
    LeaveCriticalSection(&g_cs);
}
static void follow_sync(void) {
    static uint8_t* buf;
    if (!buf && !(buf = (uint8_t*)malloc(HC_CAP))) return;
    uint32_t used = 0, cnt = 0, seq = mod_hostcheats_copy(buf, &used, &cnt);
    if (!seq || seq == g_mir_seq) return;
    g_mir_seq = seq;
    Mir now[128]; int nn = 0, changed = 0;
    EnterCriticalSection(&g_cs);
    for (uint32_t o = 0; o + 8 <= used && nn < 128;) {
        uint16_t id, un; uint32_t no;
        memcpy(&id, buf + o, 2); memcpy(&un, buf + o + 2, 2); memcpy(&no, buf + o + 4, 4);
        if (no > 1023 || o + 8 + 8 * (size_t)no > used) break;
        uint32_t* ops = (uint32_t*)malloc(8 * (size_t)(no ? no : 1)); if (!ops) break;
        memcpy(ops, buf + o + 8, 8 * (size_t)no);
        uint32_t oh = ops_hash(ops, no), h = oh ^ un;
        int idx = id >= 1 && (int)id - 1 < g_ne && !strcmp(g_e[id - 1].kind, "live") && (uint32_t)g_e[id - 1].nops == no && ops_hash(g_e[id - 1].ops, no) == oh ? (int)id - 1 : -1;
        int same = 0; for (int k = 0; k < g_nmir; k++) if (g_mir[k].id == id && g_mir[k].h == h) same = 1;
        if (!same) {
            changed = 1;
            if (idx >= 0) { if (!ent_on(&g_e[idx])) st_set("live", g_e[idx].id, 1); send_set(idx); }
            else send_raw((uint16_t)(HOST_ID + (id & 0x7FFF)), un, ops, (int)no);
        }
        now[nn].id = id; now[nn].h = h; now[nn].idx = idx; nn++;
        free(ops); o += 8 + 8 * no;
    }
    for (int k = 0; k < g_nmir; k++) {
        int still = 0; for (int j = 0; j < nn; j++) if (now[j].id == g_mir[k].id) still = 1;
        if (still) continue;
        changed = 1;
        if (g_mir[k].idx >= 0) { if (ent_on(&g_e[g_mir[k].idx])) st_set("live", g_e[g_mir[k].idx].id, 0); send_clear(g_mir[k].idx); }
        else send_clear_id((uint16_t)(HOST_ID + (g_mir[k].id & 0x7FFF)));
    }
    memcpy(g_mir, now, sizeof(Mir) * (size_t)nn); g_nmir = nn;
    LeaveCriticalSection(&g_cs);
    if (changed) refresh_ui();
}

void mod_cheatwin_show(void);
static void open_mode(int mode);
static void apply_mode(void);
static char g_test_id[200], g_test_shot[MAX_PATH], g_test_search[400], g_test_import[4000];
static DWORD test_delay(void) { const char* d = getenv("DQIX_CHEATWIN_DELAY"); return d && *d ? (DWORD)atoi(d) : 1500; }     /* test hook: ms before the window opens */
static DWORD WINAPI agent(LPVOID unused) {
    (void)unused;
    uint32_t last = 0;
    const char* t = getenv("DQIX_CHEATWIN_TEST");
    if (t && *t) {
        const char* c = strchr(t, ',');
        snprintf(g_test_id, sizeof g_test_id, "%.*s", c ? (int)(c - t) : (int)strlen(t), t);
        if (c) snprintf(g_test_shot, sizeof g_test_shot, "%s", c + 1);
        Sleep(test_delay()); open_mode(face_id(g_test_id));
    }
    t = getenv("DQIX_CHEATWIN_SEARCH");                  /* test hook: searches;searches...[,picture] (see test_step) */
    if (t && *t && !g_test_id[0]) {
        const char* c = strchr(t, ',');
        snprintf(g_test_search, sizeof g_test_search, "%.*s", c ? (int)(c - t) : (int)strlen(t), t);
        if (c) snprintf(g_test_shot, sizeof g_test_shot, "%s", c + 1);
        Sleep(test_delay()); mod_cheatwin_show();
    }
    t = getenv("DQIX_CHEATWIN_IMPORT");                  /* test hook: a shared line (or "-": the cheats that are on) -> Import, then Share (see test_step) */
    if (t && *t && !g_test_id[0] && !g_test_search[0]) {
        snprintf(g_test_import, sizeof g_test_import, "%s", t);
        Sleep(test_delay()); mod_cheatwin_show();
    }
    int was = 0, no_host = getenv("DQIX_AR_NO_HOST_CHEATS") != NULL, fake = getenv("DQIX_CHEATWIN_FAKE_SESSION") != NULL;
    for (;;) {
        Sleep(200);
        uint32_t g = mod_cheats_gen();
        SessionInfo si; session_info(&si);
        int ses = si.state == 3, fol = ses && !si.host && si.me > 0 && !no_host;
        if (fake) ses = 1;                                  /* test hook: DQIX_CHEATWIN_FAKE_SESSION=1 locks the rows as in a session */
        if (ses != (int)g_ses) { g_ses = ses; refresh_ui(); }
        if (fol != was) {                                   /* joined (the host's cheats instead of mine) or the session ended (mine again) */
            was = fol; last = g; g_nmir = 0; g_mir_seq = 0;
            uint16_t all[1] = { (uint16_t)(4 << 12) }; post_words(all, 1);
            if (fol) {
                overlay_enter();
                follow_note(L"Playing with friends: the host's cheats are on for you. Yours come back when the session ends.");
            } else { overlay_leave(); resend_all(); follow_note(L""); }
            refresh_ui();
        } else if (g != last) { last = g; g_nmir = 0; g_mir_seq = 0; resend_all(); }
        if (fol) follow_sync();
    }
    return 0;
}

/* a switch changed: state, game */
static void apply(int idx, int on) {
    Ent* e = &g_e[idx];
    if (locked(e)) return;
    EnterCriticalSection(&g_cs);
    if (on && e->group[0])                                   /* a choice: one at a time */
        for (int i = 0; i < g_ne; i++)
            if (i != idx && !strcmp(g_e[i].group, e->group) && ent_on(&g_e[i])) {
                st_set(skind(&g_e[i]), g_e[i].id, 0);
                if (!strcmp(g_e[i].kind, "live")) send_clear(i);
            }
    st_set(skind(e), e->id, on);
    st_save();
    if (!strcmp(e->kind, "live")) { if (on) send_set(idx); else send_clear(idx); }
    LeaveCriticalSection(&g_cs);
}

/* ---- program start ---- */
static void upd_start(void);
void mod_cheatwin_boot(void) {
    if (getenv("DQIX_CHEATWIN_OFF")) return;                /* tests: nothing is sent or set by itself */
    if (!g_cs_init) { InitializeCriticalSection(&g_cs); g_cs_init = 1; }
    load_catalog();
    upd_start();                                             /* a newer release on GitHub? (a thread; asks once) */
    if (!g_loaded) return;
    load_state();
    migrate_state();                                         /* nothing is switched on by itself: a first start has every cheat off */
    for (int i = 0; i < g_ne; i++)                           /* options for the next start: set before the game reads them */
        if (!strcmp(g_e[i].kind, "launch") && ent_on(&g_e[i]) && strchr(g_e[i].env, '=')) _putenv(g_e[i].env);
    CreateThread(NULL, 0, agent, NULL, 0, NULL);
}

/* ---------------------------------------------------------------- the window
 * Left: the pages (owner-drawn list), the first one, "Enabled", lists everything that is on. Right: the page's rows in a scrolling panel. A row is a check box
 * (a cheat), a drop-down (a choice of which only one can be on: "Off" + the options). */
enum { IDC_SIDE = 100, IDC_SEARCH, IDC_CLOSE, IDC_TITLE, IDC_COUNT, IDC_NOTE, IDC_SHARE, IDC_IMPORT, IDC_ROW0 = 1000, WM_SHOW_CHEATS = WM_APP + 1 };
enum { R_CHECK, R_ONCE, R_GROUP, R_KEY, R_HEAD };                 /* R_HEAD: a section's title bar (click: open / shut); sec = its g_sec index */
typedef struct { int kind, idx, gi, y, h, nm, on, sec, *members; HWND main, sub, right, combo, btn; } Row;

/* ---- sections: a page's big lists folded into parts (catalog.py SECTIONS); which are open is kept in the state file ("open <page>/<section>") */
static void sec_key(int s, char* out, size_t n) { snprintf(out, n, "%s/%s", g_sec[s].cat, g_sec[s].title); }
static unsigned char g_bshut[128];                  /* the live battle window's sections are open unless folded (not saved) */
static int sec_open(int s) {
    if (!strcmp(g_sec[s].cat, "Live battle")) return s < 128 ? !g_bshut[s] : 1;
    char k[300]; sec_key(s, k, sizeof k); return st_has("open", k);
}
static int sec_of(const char* page, const Ent* e) {                 /* the entry's section on this page, or -1 */
    if (!e->section[0]) return -1;
    for (int s = 0; s < g_nsec; s++) if (!strcmp(g_sec[s].cat, page) && !strcmp(g_sec[s].title, e->section)) return s;
    return -1;
}
static int on_page(const Ent* e, const char* page) { return strcmp(e->kind, "blocked") && (!strcmp(e->cat, page) || !strcmp(e->also, page)); }
/* how many cheats (a choice counts once) a page has, or one section of it (sec >= 0), and how many of them are on */
static void page_count(const char* page, int sec, int* total, int* on) {
    *total = *on = 0;
    char* seen = (char*)calloc((size_t)g_ng + 1, 1); char* hit = (char*)calloc((size_t)g_ng + 1, 1);
    for (int i = 0; i < g_ne; i++) {
        const Ent* e = &g_e[i];
        if (!on_page(e, page) || (sec >= 0 && sec_of(page, e) != sec) || !who_ok(e)) continue;
        int o = ent_on(e);
        if (e->gi >= 0 && seen && hit) { if (!seen[e->gi]) { seen[e->gi] = 1; (*total)++; } if (o && !hit[e->gi]) { hit[e->gi] = 1; (*on)++; } continue; }
        (*total)++; *on += o;
    }
    free(seen); free(hit);
}
static void card_hide(void);                      /* the hover card (below) */

static HWND g_search;
static HWND g_bp;                                  /* the battle window's panel (face 2): cards for the party and the enemies */
static void bp_refresh(void);
static int g_search_page;
static HBRUSH g_box;
static HWND g_win, g_side, g_host, g_title, g_count, g_note, g_close, g_share, g_import;
static void follow_note(const wchar_t* t) { if (g_note) SetWindowTextW(g_note, t); }
#define WM_REFRESH_PAGE (WM_APP + 9)
static void refresh_ui(void) { if (g_host) PostMessageW(g_host, WM_REFRESH_PAGE, 0, 0); }
static HFONT g_font, g_small, g_bold, g_head, g_mono;
static HBRUSH g_white, g_gray;
static HWND g_tip;
static wchar_t g_tiptext[2100];
static Row* g_rows; static int g_nrows, g_scroll, g_total, g_on_page, g_cur_page = -1;
static int g_keep_scroll = -1;            /* build_page: scroll back to here (a section was folded) */
static int g_found;                       /* search page: how many rows matched (only the first SEARCH_MAX are built) */
static char g_last_q[200];                /* the search the page was last built for */
#define SEARCH_MAX 60

#define PAD_X 18
#define SIDE_W 176
#define COL_BG RGB(36, 37, 41)
#define COL_SIDE RGB(24, 25, 28)
#define COL_LINE RGB(52, 54, 59)
#define COL_TEXT RGB(230, 230, 234)
#define COL_GRAY RGB(144, 146, 154)
#define COL_ACCENT RGB(226, 178, 66)
#define COL_OFF RGB(70, 72, 79)
#define COL_BOX RGB(46, 48, 54)
#define SEARCH_H 44
#define IDT_SEARCH 100

static wchar_t* wide(const char* s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0); wchar_t* w = (wchar_t*)malloc((size_t)(n + 1) * sizeof *w);
    if (w) { MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n); w[n] = 0; }
    return w;
}

/* ---- a newer release on GitHub: asked about once, a moment after the start (and on demand: Cheats > Check for update) ----
 * mods\system\version.txt says which version of these cheats is installed (the installer writes it; a development folder has none, then
 * nothing is checked). A thread asks api.github.com for the latest release (the same WinHTTP the game's own updater uses). When it is newer
 * and was not turned down before, a box asks. Yes: the game closes by itself and mods\Update.bat -Auto downloads and installs it (a console
 * window shows how far it is); the installer offers to start the game again at the end. Tests: DQIX_AR_UPDATE_HOST=127.0.0.1:port reads
 * http://host/api instead, DQIX_AR_UPDATE_TEST=1 only prints "update: ..." to stderr, DQIX_AR_NO_UPDATE_CHECK=1 skips it. */
static int ver_parse(const char* s, int v[3]) {
    while (*s && (*s < '0' || *s > '9')) s++;
    return sscanf(s, "%d.%d.%d", &v[0], &v[1], &v[2]) == 3;
}
static int ver_newer(const char* a, const char* b) {          /* a > b */
    int x[3], y[3];
    if (!ver_parse(a, x) || !ver_parse(b, y)) return 0;
    for (int i = 0; i < 3; i++) if (x[i] != y[i]) return x[i] > y[i];
    return 0;
}

static int upd_fetch(char* tag, size_t tn) {
    int ok = 0; char host[128] = "api.github.com"; int port = INTERNET_DEFAULT_HTTPS_PORT, secure = 1;
    wchar_t whost[128], wpath[160] = L"/repos/" L"mogelpeter/DQIX-Enhanced-AR" L"/releases/latest";
    const char* th = getenv("DQIX_AR_UPDATE_HOST");
    if (th && *th) {
        snprintf(host, sizeof host, "%s", th); secure = 0; port = 80;
        char* c = strchr(host, ':'); if (c) { *c = 0; port = atoi(c + 1); }
        wcscpy(wpath, L"/api");
    }
    MultiByteToWideChar(CP_ACP, 0, host, -1, whost, 128);
    HINTERNET s = WinHttpOpen(L"DQIX-Enhanced-AR-game", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0), c = NULL, r = NULL;
    if (!s) return 0;
    WinHttpSetTimeouts(s, 8000, 8000, 15000, 30000);
    c = WinHttpConnect(s, whost, (INTERNET_PORT)port, 0);
    if (c) r = WinHttpOpenRequest(c, L"GET", wpath, NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, secure ? WINHTTP_FLAG_SECURE : 0);
    if (r && WinHttpSendRequest(r, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) && WinHttpReceiveResponse(r, NULL)) {
        DWORD code = 0, sz = sizeof code;
        WinHttpQueryHeaders(r, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, WINHTTP_HEADER_NAME_BY_INDEX, &code, &sz, WINHTTP_NO_HEADER_INDEX);
        if (code == 200) {
            char* b = (char*)malloc(1 << 17); size_t n = 0;
            for (;;) {
                DWORD avail = 0, got = 0;
                if (!b || !WinHttpQueryDataAvailable(r, &avail) || !avail || n + avail >= (1 << 17)) break;
                if (!WinHttpReadData(r, b + n, avail, &got)) break;
                n += got;
            }
            if (b) {
                b[n] = 0;
                const char* p = strstr(b, "\"tag_name\"");
                if (p && (p = strchr(p + 10, '"'))) {                              /* the opening quote of the value */
                    size_t i = 0; p++;
                    while (p[i] && p[i] != '"' && i + 1 < tn) { tag[i] = p[i]; i++; }
                    tag[i] = 0; ok = i > 0;
                }
                free(b);
            }
        }
    }
    if (r) WinHttpCloseHandle(r);
    if (c) WinHttpCloseHandle(c);
    WinHttpCloseHandle(s);
    return ok;
}

static void upd_run(void) {                                   /* the game closes, mods\Update.bat -Auto installs and starts it again */
    wchar_t* rootw = wide(g_root); wchar_t cmd[MAX_PATH * 6], script[MAX_PATH * 5];
    if (!rootw) return;
    swprintf(script, MAX_PATH * 5, L"ping -n 4 127.0.0.1 >nul & call \"%ls\\mods\\Update.bat\" -Auto", rootw);
    swprintf(cmd, MAX_PATH * 6, L"cmd.exe /s /c \"%ls\"", script);
    free(rootw);
    STARTUPINFOW si; memset(&si, 0, sizeof si); si.cb = sizeof si; PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        MessageBoxW(NULL, L"The update couldn't be started. Run mods\\Update.bat in the game folder yourself.", L"DQIX Enhanced AR", MB_OK | MB_ICONERROR | MB_TOPMOST);
        return;
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    ExitProcess(0);
}

static DWORD WINAPI upd_thread(LPVOID u) {
    int manual = u != NULL;                                    /* Cheats > Check for update: always answers, ignores "turned down" */
    int test = getenv("DQIX_AR_UPDATE_TEST") != NULL;
    Sleep(test ? 500 : manual ? 0 : 1500);                     /* at the start: a moment for the window, so the box comes before the game is played */
    char path[MAX_PATH * 2 + 64], have[32] = "", tag[32] = "", no[32] = "";
    snprintf(path, sizeof path, "%s\\mods\\system\\version.txt", g_root);
    FILE* f = fopen(path, "r");
    if (!f) { if (manual) MessageBoxW(NULL, L"This folder has no version number (a development copy), so it can't be compared.", L"DQIX Enhanced AR - update", MB_OK | MB_ICONINFORMATION | MB_TOPMOST); return 0; }
    if (fgets(have, sizeof have, f)) { char* e = strpbrk(have, "\r\n"); if (e) *e = 0; }
    fclose(f);
    int hv[3]; if (!ver_parse(have, hv)) return 0;
    if (!upd_fetch(tag, sizeof tag)) {
        if (manual) MessageBoxW(NULL, L"The newest version couldn't be looked up. Is the computer online?", L"DQIX Enhanced AR - update", MB_OK | MB_ICONWARNING | MB_TOPMOST);
        return 0;
    }
    if (!ver_newer(tag, have)) {
        if (manual) MessageBoxW(NULL, L"DQIX Enhanced AR is up to date.", L"DQIX Enhanced AR - update", MB_OK | MB_ICONINFORMATION | MB_TOPMOST);
        return 0;
    }
    snprintf(path, sizeof path, "%s\\mods\\system\\update-declined.txt", g_root);
    if (!manual && (f = fopen(path, "r")) != NULL) { if (fgets(no, sizeof no, f)) { char* e = strpbrk(no, "\r\n"); if (e) *e = 0; } fclose(f); }
    if (!strcmp(no, tag)) return 0;                            /* turned down once: not asked again for this version */
    if (test) { fprintf(stderr, "update: %s is available (installed %s)\n", tag, have); fflush(stderr); return 0; }
    wchar_t msg[600], wt[32], wh[32];
    MultiByteToWideChar(CP_ACP, 0, tag, -1, wt, 32); MultiByteToWideChar(CP_ACP, 0, have, -1, wh, 32);
    swprintf(msg, 600, L"A new version of DQIX Enhanced AR is available.\n\nInstalled: %ls\nNewest: %ls\n\nUpdate now? The game closes by itself, the update is installed (a few minutes) and the game can be started again.\nProgress you have not saved is lost: save first, then press Yes.\n\nNo = ask again for a later version. You can always run mods\\Update.bat, or Cheats > Check for update.", wh, wt);
    if (MessageBoxW(NULL, msg, L"DQIX Enhanced AR - update", MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND) == IDYES) upd_run();
    else if (!manual && (f = fopen(path, "w")) != NULL) { fprintf(f, "%s\n", tag); fclose(f); }
    return 0;
}

static void upd_start(void) {
    if (getenv("DQIX_AR_NO_UPDATE_CHECK") || !g_root[0]) return;
    HANDLE h = CreateThread(NULL, 0, upd_thread, NULL, 0, NULL);
    if (h) CloseHandle(h);
}
/* the menu item Cheats > Check for update (frontend_sdl.c, command 368) */
void mod_update_check(void) {
    if (!g_root[0]) return;
    HANDLE h = CreateThread(NULL, 0, upd_thread, (LPVOID)1, 0, NULL);
    if (h) CloseHandle(h);
}

static const char* label(const Ent* e) { return e->option[0] ? e->option : e->name; }

/* the small grey line under a cheat: the keys to hold, status, note. Cheats of a session are the host's, sent to every guest automatically (follow_sync),
 * so the grey line no longer says who has to switch what on; it only says when a change takes effect. */
static const char* when_words(const char* kind) {
    if (!strcmp(kind, "live")) return "";
    if (!strcmp(kind, "launch")) return "next start";
    return "needs a rebuild";
}
static const char* who_short(const Ent* e) { return when_words(e->kind); }
static const char* who_group(const Grp* g) { return when_words(g->kind); }

/* ---- smooth shapes (pills, round knobs, the drop-down's arrow): drawn into a 32-bit bitmap with anti-aliased edges (a signed
 * distance per pixel), text on top with GDI, then copied to the screen in one go (no flicker) */
typedef struct { HDC dc; HBITMAP bmp; HGDIOBJ old; uint32_t* px; int w, h; } Cv;
static int cv_begin(Cv* c, int w, int h, COLORREF bg) {
    memset(c, 0, sizeof *c);
    if (w <= 0 || h <= 0) return 0;
    BITMAPINFO bi; memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader; bi.bmiHeader.biWidth = w; bi.bmiHeader.biHeight = -h; bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
    void* bits = NULL;
    c->dc = CreateCompatibleDC(NULL);
    c->bmp = c->dc ? CreateDIBSection(c->dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0) : NULL;
    if (!c->bmp) { if (c->dc) DeleteDC(c->dc); memset(c, 0, sizeof *c); return 0; }
    c->old = SelectObject(c->dc, c->bmp); c->px = (uint32_t*)bits; c->w = w; c->h = h;
    uint32_t v = (uint32_t)GetRValue(bg) << 16 | (uint32_t)GetGValue(bg) << 8 | GetBValue(bg);
    for (int i = 0; i < w * h; i++) c->px[i] = v;
    SetBkMode(c->dc, TRANSPARENT);
    return 1;
}
static void cv_end(Cv* c, HDC dst, int x, int y) {
    if (!c->dc) return;
    GdiFlush();
    BitBlt(dst, x, y, c->w, c->h, c->dc, 0, 0, SRCCOPY);
    SelectObject(c->dc, c->old); DeleteObject(c->bmp); DeleteDC(c->dc); memset(c, 0, sizeof *c);
}
static void cv_blend(Cv* c, int x, int y, COLORREF col, float a) {
    uint32_t* p = &c->px[y * c->w + x]; uint32_t v = *p;
    float r = (float)(v >> 16 & 255), g = (float)(v >> 8 & 255), b = (float)(v & 255);
    r += ((float)GetRValue(col) - r) * a; g += ((float)GetGValue(col) - g) * a; b += ((float)GetBValue(col) - b) * a;
    *p = (uint32_t)(r + 0.5f) << 16 | (uint32_t)(g + 0.5f) << 8 | (uint32_t)(b + 0.5f);
}
/* a rounded box from (x0,y0) to (x1,y1) with corner radius r (half the height: a pill; a square with r = half: a circle);
 * ring > 0: only its outline, that wide */
static void cv_box(Cv* c, float x0, float y0, float x1, float y1, float r, COLORREF col, float ring) {
    float cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, hw = (x1 - x0) / 2, hh = (y1 - y0) / 2;
    if (r > hw) r = hw;
    if (r > hh) r = hh;
    int xa = (int)floorf(x0) - 1, xb = (int)ceilf(x1) + 1, ya = (int)floorf(y0) - 1, yb = (int)ceilf(y1) + 1;
    if (xa < 0) xa = 0;
    if (ya < 0) ya = 0;
    if (xb > c->w) xb = c->w;
    if (yb > c->h) yb = c->h;
    for (int y = ya; y < yb; y++)
        for (int x = xa; x < xb; x++) {
            float qx = fabsf((float)x + 0.5f - cx) - (hw - r), qy = fabsf((float)y + 0.5f - cy) - (hh - r);
            float ox = qx > 0 ? qx : 0, oy = qy > 0 ? qy : 0;
            float d = sqrtf(ox * ox + oy * oy) + fminf(fmaxf(qx, qy), 0.f) - r;
            float a = 0.5f - d; a = a < 0 ? 0 : a > 1 ? 1 : a;
            if (ring > 0) { float in = 0.5f - (d + ring); in = in < 0 ? 0 : in > 1 ? 1 : in; a -= in; }
            if (a > 0.003f) cv_blend(c, x, y, col, a);
        }
}
/* a line with round ends, w wide */
static void cv_line(Cv* c, float x0, float y0, float x1, float y1, float w, COLORREF col) {
    int xa = (int)floorf(fminf(x0, x1) - w) - 1, xb = (int)ceilf(fmaxf(x0, x1) + w) + 1, ya = (int)floorf(fminf(y0, y1) - w) - 1, yb = (int)ceilf(fmaxf(y0, y1) + w) + 1;
    if (xa < 0) xa = 0;
    if (ya < 0) ya = 0;
    if (xb > c->w) xb = c->w;
    if (yb > c->h) yb = c->h;
    float dx = x1 - x0, dy = y1 - y0, ll = dx * dx + dy * dy;
    for (int y = ya; y < yb; y++)
        for (int x = xa; x < xb; x++) {
            float px = (float)x + 0.5f - x0, py = (float)y + 0.5f - y0;
            float t = ll > 0 ? (px * dx + py * dy) / ll : 0; t = t < 0 ? 0 : t > 1 ? 1 : t;
            float ex = px - dx * t, ey = py - dy * t, d = sqrtf(ex * ex + ey * ey) - w / 2;
            float a = 0.5f - d; a = a < 0 ? 0 : a > 1 ? 1 : a;
            if (a > 0.003f) cv_blend(c, x, y, col, a);
        }
}
static void cv_text(Cv* c, const wchar_t* t, RECT r, HFONT f, COLORREF col, UINT fmt) {
    HGDIOBJ o = SelectObject(c->dc, f); SetTextColor(c->dc, col);
    DrawTextW(c->dc, t, -1, &r, fmt | DT_NOPREFIX); SelectObject(c->dc, o);
}

/* the grey line under a cheat */
static void tag_add(char* out, size_t n, const char* pre, const char* a, const char* b) {
    if (!a[0] && !b[0]) return;
    size_t u = strlen(out); if (u >= n) return;
    snprintf(out + u, n - u, "%s%s%s%s", u ? " \xC2\xB7 " : "", pre, a, b);
}
static void tag_text(const Ent* e, char* out, size_t n) {
    out[0] = 0;
    if (!strcmp(e->kind, "ui")) { snprintf(out, n, "%s", e->note); return; }
    if (locked(e)) { snprintf(out, n, "%s", lock_why(e)); return; }
    int untested = !strcmp(e->status, "untested");
    if (!(!strcmp(e->mode, "once") && !strcmp(e->kind, "live"))) {    /* a one-time row has no switch: no news about when it takes effect */
        tag_add(out, n, "", who_short(e), "");
        if (e->keys[0]) tag_add(out, n, "hold ", e->keys, "");
    }
    if (untested) tag_add(out, n, "", "untested", "");
    tag_add(out, n, "", e->note, "");
}

/* the hover text: the cheat's longer explanation (mods/system/about.tsv, through the catalog), nothing the row already shows
 * (name, who needs it, keys, labels and the note are in the row). No explanation: no hover box. */
static void hover_text(const char* about, wchar_t* out, size_t n) {
    out[0] = 0;
    if (!about || !about[0]) return;
    wchar_t* w = wide(about); if (w) { wcsncpy(out, w, n - 1); out[n - 1] = 0; free(w); }
}

/* ---- the grey line, drawn by hand: word-wrapped like DrawText, with the DS buttons in it (hold L+R, START+UP, [R],
 * L + R + SELECT...) in their own colour. rich_text(..., draw=0) only measures (the row height). */
#define COL_KEY RGB(122, 178, 255)
static int key_part(const wchar_t* p, int n, int loose) {     /* one button name; loose: also "Start", "Up"... */
    static const wchar_t* up[] = { L"A", L"B", L"X", L"Y", L"L", L"R", L"START", L"SELECT", L"UP", L"DOWN", L"LEFT", L"RIGHT" };
    static const wchar_t* cap[] = { L"Start", L"Select", L"Up", L"Down", L"Left", L"Right" };
    for (int i = 0; i < 12; i++) if ((int)wcslen(up[i]) == n && !wcsncmp(p, up[i], (size_t)n)) return 1;
    if (loose) for (int i = 0; i < 6; i++) if ((int)wcslen(cap[i]) == n && !wcsncmp(p, cap[i], (size_t)n)) return 1;
    return 0;
}
/* 2 = a combo (L+A, START+UP: always a key), 1 = a single button name, 0 = not one */
static int key_word(const wchar_t* w, int n) {
    int plus = 0, s = 0;
    for (int i = 0; i <= n; i++) {
        if (i == n || w[i] == L'+' || w[i] == L'/') {
            if (i == s || !key_part(w + s, i - s, 1)) return 0;
            if (i < n) plus = 1;
            s = i + 1;
        }
    }
    return plus ? 2 : 1;
}
static int rich_text(HDC dc, const wchar_t* t, RECT rc, int draw) {
    TEXTMETRICW tm; GetTextMetricsW(dc, &tm); int lh = tm.tmHeight, sp;
    SIZE z; GetTextExtentPoint32W(dc, L" ", 1, &z); sp = z.cx;
    int x = 0, y = 0, W = rc.right - rc.left, prevkey = 0, prevctx = 0;
    const wchar_t* p = t;
    if (draw) SetBkMode(dc, TRANSPARENT);
    while (*p) {
        int gap = 0; while (*p == L' ') { p++; gap++; }
        if (!*p) break;
        if (gap > 1 && x > 0) x += sp * (gap - 1);                    /* the separators keep their room */
        const wchar_t* q = p; while (*q && *q != L' ') q++;
        int n = (int)(q - p);
        /* the word without brackets and punctuation around it */
        const wchar_t* a = p; const wchar_t* b = q;
        while (a < b && (*a == L'(' || *a == L'[' || *a == L'"')) a++;
        while (b > a && wcschr(L").,:;!?]\"", b[-1])) b--;
        int k = key_word(a, (int)(b - a)), key = 0;
        if (k == 2) key = 1;                                         /* L+A, START+UP */
        else if (k == 1 && (b - a > 1) && iswupper(a[1])) key = 1;     /* START, SELECT, UP... in capitals */
        else if (k == 1 && (prevctx || prevkey || a > p)) key = 1;     /* "press A", "[R]", "L + R" */
        else if ((b - a) == 1 && *a == L'+' && prevkey) key = 1;       /* the "+" of "L + R" */
        GetTextExtentPoint32W(dc, p, n, &z);
        if (x > 0 && x + z.cx > W) { x = 0; y += lh; }
        if (draw && key) {                                   /* only the button in blue: brackets, quotes, commas stay grey */
            SIZE za, zb; GetTextExtentPoint32W(dc, p, (int)(a - p), &za); GetTextExtentPoint32W(dc, p, (int)(b - p), &zb);
            SetTextColor(dc, COL_GRAY); TextOutW(dc, rc.left + x, rc.top + y, p, (int)(a - p));
            SetTextColor(dc, COL_KEY); TextOutW(dc, rc.left + x + za.cx, rc.top + y, a, (int)(b - a));
            SetTextColor(dc, COL_GRAY); TextOutW(dc, rc.left + x + zb.cx, rc.top + y, b, (int)(q - b));
        } else if (draw) {
            SetTextColor(dc, COL_GRAY);
            TextOutW(dc, rc.left + x, rc.top + y, p, n);
        }
        x += z.cx + sp;
        /* "press" / "hold" / "push" make the next single letter a button */
        wchar_t lw[12] = { 0 }; int ln = (int)(b - a) < 11 ? (int)(b - a) : 0;
        for (int i = 0; i < ln; i++) lw[i] = (wchar_t)towlower(a[i]);
        prevctx = (ln && (!wcscmp(lw, L"press") || !wcscmp(lw, L"hold") || !wcscmp(lw, L"push") || !wcscmp(lw, L"pressing") || !wcscmp(lw, L"holding")))
                  || (prevkey && (!wcscmp(lw, L"and") || !wcscmp(lw, L"or") || !wcscmp(lw, L"then")));
        prevkey = key || (prevkey && prevctx);
        p = q;
    }
    return y + lh;
}

/* ---- the controls drawn by hand: hover, pills ---- */
static HWND g_hot;                                                 /* the control under the mouse (a lighter look) */
static LRESULT CALLBACK hot_proc(HWND h, UINT m, WPARAM wp, LPARAM lp);
static void hook(HWND h) { SetPropW(h, L"dqix.old", (HANDLE)SetWindowLongPtrW(h, GWLP_WNDPROC, (LONG_PTR)hot_proc)); }

/* a pill button (Close, Share, Import; "Use" on a row in green) */
static Row* row_of_id(int id);
static void draw_pill_button(const DRAWITEMSTRUCT* d) {
    RECT rc = d->rcItem; int w = rc.right - rc.left, h = rc.bottom - rc.top; Cv c;
    if (!cv_begin(&c, w, h, COL_BG)) return;
    int hot = g_hot == d->hwndItem, down = (d->itemState & ODS_SELECTED) != 0;
    int bid = GetDlgCtrlID(d->hwndItem), use = bid != IDC_CLOSE && bid != IDC_SHARE && bid != IDC_IMPORT;     /* a row's button: "Use" */
    float r = (float)h / 2;
    if (use) {                                               /* green: it does something now (the gold is for switches that are on) */
        Row* tr = row_of_id(bid); int tg_on = tr && tr->idx >= 0 && !strcmp(g_e[tr->idx].mode, "toggle") && tr->on;      /* Vanish while vanished: gold */
        cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)h - 0.5f, r, tg_on ? (down ? RGB(190, 150, 50) : hot ? RGB(250, 208, 108) : COL_ACCENT) : down ? RGB(48, 128, 94) : hot ? RGB(112, 214, 164) : RGB(84, 184, 138), 0);
        wchar_t ut[64]; GetWindowTextW(d->hwndItem, ut, 64);
        RECT ur = { 0, down ? 1 : 0, w, h + (down ? 1 : 0) };
        cv_text(&c, ut, ur, g_bold, RGB(10, 32, 22), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        cv_end(&c, d->hDC, rc.left, rc.top);
        return;
    }
    cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)h - 0.5f, r, hot ? RGB(96, 99, 108) : RGB(70, 72, 80), 0);
    cv_box(&c, 1.5f, 1.5f, (float)w - 1.5f, (float)h - 1.5f, r - 1, down ? RGB(40, 42, 47) : hot ? RGB(62, 64, 72) : RGB(49, 51, 57), 0);
    if ((d->itemState & ODS_FOCUS) && !(d->itemState & ODS_NOFOCUSRECT)) cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)h - 0.5f, r, COL_ACCENT, 1.5f);
    wchar_t t[64]; GetWindowTextW(d->hwndItem, t, 64);
    int id = GetDlgCtrlID(d->hwndItem), icon = id == IDC_SHARE ? 1 : id == IDC_IMPORT ? 2 : 0;
    if (icon) {                                              /* Share: an arrow out of a tray, Import: an arrow into it */
        HGDIOBJ o = SelectObject(c.dc, g_font); SIZE z; GetTextExtentPoint32W(c.dc, t, (int)wcslen(t), &z); SelectObject(c.dc, o);
        float x0 = (float)((w - (14 + 8 + z.cx)) / 2), cy = (float)h / 2 + (down ? 1 : 0), mx = x0 + 7;
        COLORREF ic = hot ? COL_ACCENT : COL_TEXT;
        cv_line(&c, x0 + 1, cy + 1, x0 + 1, cy + 6, 1.5f, ic); cv_line(&c, x0 + 1, cy + 6, x0 + 13, cy + 6, 1.5f, ic); cv_line(&c, x0 + 13, cy + 6, x0 + 13, cy + 1, 1.5f, ic);
        if (icon == 1) { cv_line(&c, mx, cy + 2, mx, cy - 7, 1.5f, ic); cv_line(&c, mx - 4, cy - 3, mx, cy - 7, 1.5f, ic); cv_line(&c, mx, cy - 7, mx + 4, cy - 3, 1.5f, ic); }
        else { cv_line(&c, mx, cy - 7, mx, cy + 2, 1.5f, ic); cv_line(&c, mx - 4, cy - 2, mx, cy + 2, 1.5f, ic); cv_line(&c, mx, cy + 2, mx + 4, cy - 2, 1.5f, ic); }
        RECT tr = { (int)x0 + 22, down ? 1 : 0, w, h + (down ? 1 : 0) };
        cv_text(&c, t, tr, g_font, COL_TEXT, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
    } else {
        RECT tr = { 0, down ? 1 : 0, w, h + (down ? 1 : 0) };
        cv_text(&c, t, tr, g_font, COL_TEXT, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    }
    cv_end(&c, d->hDC, rc.left, rc.top);
}

/* a drop-down drawn as a pill: what is chosen, and an arrow; something chosen (not Off): in the accent colour */
static void paint_combo(HWND h, HDC dc) {
    RECT rc; GetClientRect(h, &rc); int w = rc.right, ht = rc.bottom; Cv c;
    if (!cv_begin(&c, w, ht, COL_BG)) return;
    int hot = g_hot == h, open = (int)SendMessageW(h, CB_GETDROPPEDSTATE, 0, 0), focus = GetFocus() == h;
    int sel = (int)SendMessageW(h, CB_GETCURSEL, 0, 0);
    float r = (float)ht / 2;
    COLORREF edge = open || focus ? COL_ACCENT : hot ? RGB(96, 99, 108) : RGB(70, 72, 80);
    cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)ht - 0.5f, r, edge, 0);
    cv_box(&c, 1.5f, 1.5f, (float)w - 1.5f, (float)ht - 1.5f, r - 1, hot || open ? RGB(60, 62, 70) : RGB(49, 51, 57), 0);
    float ax = (float)w - 18, ay = (float)ht / 2;                  /* the arrow: a small V */
    COLORREF ac = sel > 0 ? COL_ACCENT : COL_GRAY;
    cv_line(&c, ax - 4, ay - 2, ax, ay + 2, 1.6f, ac); cv_line(&c, ax, ay + 2, ax + 4, ay - 2, 1.6f, ac);
    wchar_t t[300] = L"";
    if (sel >= 0 && SendMessageW(h, CB_GETLBTEXTLEN, (WPARAM)sel, 0) < 299) SendMessageW(h, CB_GETLBTEXT, (WPARAM)sel, (LPARAM)t);
    RECT tr = { 14, 0, w - 30, ht };
    cv_text(&c, t, tr, g_font, sel > 0 ? COL_ACCENT : COL_TEXT, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
    cv_end(&c, dc, 0, 0);
}

static LRESULT CALLBACK hot_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    WNDPROC old = (WNDPROC)GetPropW(h, L"dqix.old");
    if (m == WM_MOUSEMOVE && g_hot != h) {
        HWND was = g_hot; g_hot = h;
        TRACKMOUSEEVENT t; memset(&t, 0, sizeof t); t.cbSize = sizeof t; t.dwFlags = TME_LEAVE; t.hwndTrack = h; TrackMouseEvent(&t);
        if (was && IsWindow(was)) InvalidateRect(was, NULL, FALSE);
        InvalidateRect(h, NULL, FALSE);
    } else if (m == WM_MOUSELEAVE && g_hot == h) { g_hot = NULL; InvalidateRect(h, NULL, FALSE); }
    else if (m == WM_NCDESTROY) { if (g_hot == h) g_hot = NULL; RemovePropW(h, L"dqix.old"); SetWindowLongPtrW(h, GWLP_WNDPROC, (LONG_PTR)old); return CallWindowProcW(old, h, m, wp, lp); }
    wchar_t cls[16]; GetClassNameW(h, cls, 16);
    if (!wcscmp(cls, L"ComboBox")) {
        if (m == WM_PAINT) { PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); paint_combo(h, dc); EndPaint(h, &ps); return 0; }
        if (m == WM_ERASEBKGND) return 1;
        if (m == WM_SETFOCUS || m == WM_KILLFOCUS || m == WM_ENABLE || m == CB_SETCURSEL) {
            LRESULT res = CallWindowProcW(old, h, m, wp, lp); InvalidateRect(h, NULL, FALSE); return res;
        }
    }
    return CallWindowProcW(old, h, m, wp, lp);
}

static void dark(HWND h, const wchar_t* theme);
static HWND mk(const wchar_t* cls, const char* text, DWORD style, HFONT f, int id) {
    wchar_t* w = wide(text);
    if (!wcscmp(cls, L"BUTTON") && !(style & BS_OWNERDRAW) && w && wcschr(w, L'&')) {          /* a button shows "&" as an underline: double it */
        size_t n = wcslen(w), k = 0; wchar_t* d = (wchar_t*)malloc((n * 2 + 1) * sizeof *d);
        if (d) { for (size_t i = 0; i < n; i++) { d[k++] = w[i]; if (w[i] == L'&') d[k++] = L'&'; } d[k] = 0; free(w); w = d; }
    }
    HWND h = CreateWindowExW(0, cls, w, WS_CHILD | WS_VISIBLE | style, 0, 0, 10, 10, g_host, (HMENU)(UINT_PTR)id, GetModuleHandleW(NULL), NULL);
    free(w); SendMessageW(h, WM_SETFONT, (WPARAM)f, TRUE);
    if (!wcscmp(cls, L"COMBOBOX") || (!wcscmp(cls, L"BUTTON") && (style & BS_OWNERDRAW))) hook(h);
    return h;
}

static void clear_rows(void) {
    for (int i = 0; i < g_nrows; i++) {
        HWND hs[5] = { g_rows[i].main, g_rows[i].sub, g_rows[i].right, g_rows[i].combo, g_rows[i].btn };
        for (int k = 0; k < 5; k++) if (hs[k]) DestroyWindow(hs[k]);
    }
    for (int i = 0; i < g_nrows && g_tip; i++) { TOOLINFOW ti; memset(&ti, 0, sizeof ti); ti.cbSize = sizeof ti; ti.hwnd = g_host; ti.uId = (UINT_PTR)i; SendMessageW(g_tip, TTM_DELTOOLW, 0, (LPARAM)&ti); }
    for (int i = 0; i < g_nrows; i++) free(g_rows[i].members);
    free(g_rows); g_rows = NULL; g_nrows = 0;
}

static Row* add_row(int kind, int idx, int gi) {
    g_rows = (Row*)realloc(g_rows, (size_t)(g_nrows + 1) * sizeof *g_rows);
    Row* r = &g_rows[g_nrows]; memset(r, 0, sizeof *r); r->kind = kind; r->idx = idx; r->gi = gi;
    if (g_tip) { TOOLINFOW ti; memset(&ti, 0, sizeof ti); ti.cbSize = sizeof ti; ti.uFlags = 0; ti.hwnd = g_host; ti.uId = (UINT_PTR)g_nrows; ti.lpszText = LPSTR_TEXTCALLBACKW; SendMessageW(g_tip, TTM_ADDTOOLW, 0, (LPARAM)&ti); }
    g_nrows++; return r;
}

static void update_count(void) {
    int cheats = 0, on = 0;
    for (int i = 0; i < g_nrows; i++) {
        Row* r = &g_rows[i];
        if (r->kind == R_CHECK || (r->kind == R_ONCE && r->idx >= 0 && !strcmp(g_e[r->idx].mode, "toggle"))) { cheats++; on += ent_on(&g_e[r->idx]); }
        else if (r->kind == R_GROUP) { cheats++; for (int k = 0; k < r->nm; k++) if (ent_on(&g_e[r->members[k]])) { on++; break; } }
    }
    if (g_cur_page >= 0 && g_cur_page < g_npg) page_count(g_pg[g_cur_page], -1, &cheats, &on);     /* a page: shut sections count too */
    for (int i = 0; i < g_nrows; i++) if (g_rows[i].kind == R_HEAD) InvalidateRect(g_rows[i].main, NULL, FALSE);
    char b[80]; if (g_cur_page == g_search_page) { if (g_found > cheats) snprintf(b, sizeof b, "%d found, first %d shown: type more words", g_found, cheats); else snprintf(b, sizeof b, "%d found, %d on", cheats, on); } else if (g_cur_page == g_on_page) snprintf(b, sizeof b, on ? "%d switched on (all pages)" : "Nothing is switched on", on); else snprintf(b, sizeof b, "%d of %d on", on, cheats);
    if (g_mode == 2) {
        int np = g_ro.party[0] + g_ro.party[1] + g_ro.party[2] + g_ro.party[3], ne = g_ro.enemy[0] + g_ro.enemy[1] + g_ro.enemy[2] + g_ro.enemy[3] + g_ro.enemy[4] + g_ro.enemy[5];
        if (g_ro.inbattle) snprintf(b, sizeof b, "In a battle: %d in your party, %d enem%s", np, ne, ne == 1 ? "y" : "ies"); else snprintf(b, sizeof b, "Not in a battle: these appear when a fight starts");
    }
    wchar_t* w = wide(b); SetWindowTextW(g_count, w); free(w);
}

static HDWP defer(HDWP d, HWND h, int x, int y, int w, int ht) {
    return d ? DeferWindowPos(d, h, NULL, x, y, w, ht, SWP_NOZORDER | SWP_NOACTIVATE) : NULL;
}

static void lay_rows(void) {
    RECT cr; GetClientRect(g_host, &cr); int W = cr.right;
    HDC dc = GetDC(g_host); int y = 4;
    HDWP dwp = BeginDeferWindowPos(g_nrows * 4 + 1);
    for (int i = 0; i < g_nrows; i++) {
        Row* r = &g_rows[i];
        if (r->kind == R_HEAD) {                                    /* a section's title bar: the whole width */
            r->y = y; r->h = 46;
            dwp = defer(dwp, r->main, PAD_X - 6, y - g_scroll + 8, W - 2 * PAD_X + 12, 32);
            if (g_tip) { TOOLINFOW ti; memset(&ti, 0, sizeof ti); ti.cbSize = sizeof ti; ti.hwnd = g_host; ti.uId = (UINT_PTR)i; ti.rect.right = W; ti.rect.top = y - g_scroll; ti.rect.bottom = ti.rect.top + r->h; SendMessageW(g_tip, TTM_NEWTOOLRECTW, 0, (LPARAM)&ti); }
            y += r->h; continue;
        }
        int rightw = r->kind == R_GROUP ? 230 : r->kind == R_KEY ? (W - 2 * PAD_X) * 42 / 100 : r->btn ? (r->idx >= 0 && !strcmp(g_e[r->idx].mode, "toggle") ? 190 : 112) : 0;
        int gap = rightw ? 14 : 0, textw = W - 2 * PAD_X - rightw - gap, indent = r->kind == R_CHECK ? 48 : 0;
        int subh = 0, rh = 0;
        wchar_t buf[600];
        if (r->sub) {
            GetWindowTextW(r->sub, buf, 600); HGDIOBJ o = SelectObject(dc, g_small);
            RECT m = { 0, 0, textw - indent, 0 }; subh = rich_text(dc, buf, m, 0); SelectObject(dc, o);
        }
        if (r->kind == R_KEY && r->right) {
            GetWindowTextW(r->right, buf, 600); HGDIOBJ o = SelectObject(dc, g_mono);
            RECT m = { 0, 0, rightw, 0 }; DrawTextW(dc, buf, -1, &m, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX); rh = m.bottom; SelectObject(dc, o);
        }
        int h = 8 + 26 + (subh ? 1 + subh : 0) + 10; if (rh + 18 > h) h = rh + 18; if (h < 50 && r->kind != R_KEY) h = 50; if (h < 40) h = 40;
        r->y = y; r->h = h;
        int top = y - g_scroll;
        dwp = defer(dwp, r->main, PAD_X, top + 8, textw, 26);
        if (r->sub) dwp = defer(dwp, r->sub, PAD_X + indent, top + 8 + 26 + 1, textw - indent, subh);
        if (r->combo) { RECT cb; GetWindowRect(r->combo, &cb); int ch = cb.bottom - cb.top; if (ch < 20 || ch > 60) ch = 30;
                        dwp = defer(dwp, r->combo, W - PAD_X - rightw, top + (h - ch) / 2, rightw, 300); }
        if (r->btn) dwp = defer(dwp, r->btn, W - PAD_X - rightw, top + (h - 30) / 2, rightw, 30);
        if (r->kind == R_KEY && r->right) dwp = defer(dwp, r->right, W - PAD_X - rightw, top + (h - rh) / 2, rightw, rh);
        if (g_tip) { TOOLINFOW ti; memset(&ti, 0, sizeof ti); ti.cbSize = sizeof ti; ti.hwnd = g_host; ti.uId = (UINT_PTR)i; ti.rect.left = 0; ti.rect.right = W; ti.rect.top = top; ti.rect.bottom = top + h; SendMessageW(g_tip, TTM_NEWTOOLRECTW, 0, (LPARAM)&ti); }
        y += h;
    }
    ReleaseDC(g_host, dc);
    if (dwp) EndDeferWindowPos(dwp);
    g_total = y + 8;
    { int max = g_total - cr.bottom; if (max < 0) max = 0; if (g_scroll > max) g_scroll = max; }
    RedrawWindow(g_host, NULL, NULL, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN);
}

/* scrolling: the screen's pixels are moved (ScrollWindowEx), only the strip that comes into view is painted, so nothing
 * flickers. Controls that were out of view are not moved by Windows: they are put where they belong without a redraw. */
static void scroll_to(int pos) {
    RECT cr; GetClientRect(g_host, &cr); int max = g_total - cr.bottom; if (max < 0) max = 0;
    if (pos > max) pos = max;
    if (pos < 0) pos = 0;
    if (pos == g_scroll) return;
    int dy = g_scroll - pos;
    int n = 0, cap = g_nrows * 5; HWND* hs = (HWND*)malloc((size_t)(cap ? cap : 1) * sizeof *hs); int* want = (int*)malloc((size_t)(cap ? cap : 1) * sizeof *want);
    for (int i = 0; i < g_nrows && hs && want; i++) {
        HWND c5[5] = { g_rows[i].main, g_rows[i].sub, g_rows[i].right, g_rows[i].combo, g_rows[i].btn };
        for (int k = 0; k < 5; k++) if (c5[k]) { RECT r; GetWindowRect(c5[k], &r); MapWindowPoints(NULL, g_host, (POINT*)&r, 2); hs[n] = c5[k]; want[n++] = r.top + dy; }
    }
    g_scroll = pos;
    ScrollWindowEx(g_host, 0, dy, NULL, NULL, NULL, NULL, SW_SCROLLCHILDREN | SW_INVALIDATE | SW_ERASE);
    for (int i = 0; i < n; i++) {
        RECT r; GetWindowRect(hs[i], &r); MapWindowPoints(NULL, g_host, (POINT*)&r, 2);
        if (r.top != want[i]) SetWindowPos(hs[i], NULL, r.left, want[i], 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOREDRAW | SWP_NOCOPYBITS);
    }
    free(hs); free(want);
    for (int i = 0; i < g_nrows && g_tip; i++) {
        TOOLINFOW ti; memset(&ti, 0, sizeof ti); ti.cbSize = sizeof ti; ti.hwnd = g_host; ti.uId = (UINT_PTR)i;
        ti.rect.left = 0; ti.rect.right = cr.right; ti.rect.top = g_rows[i].y - g_scroll; ti.rect.bottom = ti.rect.top + g_rows[i].h;
        SendMessageW(g_tip, TTM_NEWTOOLRECTW, 0, (LPARAM)&ti);
    }
    UpdateWindow(g_host);
}

/* the search box: its text, lower case, UTF-8 */
static void search_text(char* out, size_t n) {
    wchar_t w[200]; out[0] = 0;
    int len = g_search ? GetWindowTextW(g_search, w, 200) : 0; if (len <= 0) return;
    int k = WideCharToMultiByte(CP_UTF8, 0, w, len, out, (int)n - 1, NULL, NULL); if (k < 0) k = 0; out[k] = 0;
    for (char* c = out; *c; c++) if ((unsigned char)*c < 128) *c = (char)tolower((unsigned char)*c);
    char* a = out; while (*a == ' ') a++; if (a != out) memmove(out, a, strlen(a) + 1);
    size_t l = strlen(out); while (l && out[l - 1] == ' ') out[--l] = 0;
}

/* the search, split into words once per build */
static char g_qbuf[200]; static char* g_qw[24]; static int g_nqw;
static void split_query(const char* q) {
    snprintf(g_qbuf, sizeof g_qbuf, "%s", q); g_nqw = 0;
    for (char* t = strtok(g_qbuf, " "); t && g_nqw < 24; t = strtok(NULL, " ")) g_qw[g_nqw++] = t;
}
/* every word is in the text, or (for a member of a choice) in the text or the choice's title */
static int words_in(const char* a, const char* b) {
    for (int i = 0; i < g_nqw; i++) if (!(a && strstr(a, g_qw[i])) && !(b && strstr(b, g_qw[i]))) return 0;
    return 1;
}
static int match_words(const Ent* e) { return words_in(e->hay, e->gi >= 0 ? g_g[e->gi].lt : NULL); }

/* the row(s) of entry i on page p (a choice: one row for all its members, the first time one of them comes) */
static void add_entry(int p, int i, char* seen) {
    int special = p == g_on_page || p == g_search_page;
    Ent* e = &g_e[i];
    if (!strcmp(e->kind, "blocked")) return;
    if (special && is_nz(e)) return;                         /* the Nuzlocke window's own entries are not in the Cheats window's Enabled page or search */
    if (p != g_on_page && !who_ok(e)) return;                /* a member / enemy that isn't there */
    if (p == g_on_page) { if (!ent_on(e)) return; }          /* the Enabled page: everything that is on, from every page */
    else if (p == g_search_page) { if (!match_words(e)) return; }
    else if (strcmp(e->cat, g_pg[p]) && strcmp(e->also, g_pg[p])) return;
    if (e->gi >= 0) {
        int gi = e->gi;
        {
            if (seen[gi]) return;                      /* the whole choice is one row with a drop-down */
            seen[gi] = 1;
            if (p == g_search_page && ++g_found > SEARCH_MAX) return;
            Grp* g = &g_g[gi];
            /* searching: the members the words fit, or all of them when the choice's own title fits */
            int all = p == g_search_page && words_in(g->lt, NULL);
            Row* r = add_row(R_GROUP, -1, gi); int id = IDC_ROW0 + g_nrows - 1;
            r->members = (int*)malloc((size_t)(g->nmem ? g->nmem : 1) * sizeof *r->members);
            for (int j = 0; j < g->nmem && r->members; j++) {
                Ent* m = &g_e[g->mem[j]];
                if (p == g_search_page ? (all || match_words(m)) : (special || !strcmp(m->cat, g_pg[p]) || !strcmp(m->also, g_pg[p]))) r->members[r->nm++] = g->mem[j];
            }
            r->main = mk(L"STATIC", g_g[gi].title, SS_NOPREFIX | SS_ENDELLIPSIS | SS_CENTERIMAGE, g_bold, id);
            { char st[300]; const char* wg = who_group(g);
              if (g_ses && (!strcmp(g->kind, "launch") || !strcmp(g->kind, "code"))) snprintf(st, sizeof st, "%s", lock_why_kind(g->kind));
              else snprintf(st, sizeof st, "%s%sChoose one: only one of these can be on.", wg, wg[0] ? " \xC2\xB7 " : "");
              r->sub = mk(L"STATIC", st, SS_OWNERDRAW, g_small, id); SetWindowLongPtrW(r->sub, GWLP_USERDATA, 1); }
            r->combo = mk(L"COMBOBOX", "", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, g_font, id); dark(r->combo, L"DarkMode_CFD");
            SendMessageW(r->combo, CB_SETITEMHEIGHT, (WPARAM)-1, 24); SendMessageW(r->combo, CB_SETITEMHEIGHT, 0, 22);
            SendMessageW(r->combo, CB_ADDSTRING, 0, (LPARAM)L"Off");
            int cur = 0;
            for (int k = 0; k < r->nm; k++) {
                char t[300]; snprintf(t, sizeof t, "%s%s", label(&g_e[r->members[k]]), !strcmp(g_e[r->members[k]].status, "untested") ? "  (untested)" : "");
                wchar_t* w = wide(t); SendMessageW(r->combo, CB_ADDSTRING, 0, (LPARAM)w); free(w);
                if (ent_on(&g_e[r->members[k]])) cur = k + 1;
            }
            SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)cur, 0);
            SendMessageW(r->combo, CB_SETMINVISIBLE, 12, 0);
            if (g_ses && (!strcmp(g->kind, "launch") || !strcmp(g->kind, "code"))) EnableWindow(r->combo, FALSE);
            return;
        }
    }
    if (p == g_search_page && ++g_found > SEARCH_MAX) return;
    char shown[500]; snprintf(shown, sizeof shown, "%s", label(e));
    if (p == g_on_page) { const Grp* gg = e->gi >= 0 ? &g_g[e->gi] : NULL; if (gg) snprintf(shown, sizeof shown, "%s: %s", gg->title, label(e)); else snprintf(shown, sizeof shown, "%s", e->name); }
    int tgl = !strcmp(e->mode, "toggle");                       /* a button that is switched on and off (Vanish) */
    int once = !strcmp(e->mode, "once") || tgl, both = (!strcmp(e->kind, "live") && (once || !strcmp(e->mode, "both"))) || !strcmp(e->kind, "ui");
    Row* r = add_row(once ? R_ONCE : R_CHECK, i, -1); int id = IDC_ROW0 + g_nrows - 1;
    if (tgl) r->on = ent_on(e);
    if (once) r->main = mk(L"STATIC", shown, SS_NOPREFIX | SS_ENDELLIPSIS | SS_CENTERIMAGE, g_font, id);
    else {
        r->main = mk(L"BUTTON", shown, BS_OWNERDRAW | WS_TABSTOP, g_font, id);
        r->on = ent_on(e);
    }
    char tag[700]; tag_text(e, tag, sizeof tag);
    r->sub = mk(L"STATIC", tag, SS_OWNERDRAW, g_small, id); SetWindowLongPtrW(r->sub, GWLP_USERDATA, 1);
    if (both) r->btn = mk(L"BUTTON", !strcmp(e->kind, "ui") ? "Open" : tgl ? (r->on ? "Vanished \xC2\xB7 show up" : "Vanish") : "Use", BS_OWNERDRAW | WS_TABSTOP, g_font, id);
    if (locked(e) && r->kind == R_CHECK) EnableWindow(r->main, FALSE);
}

/* a section's title in the battle window: who it is for, as it is now */
static void sec_label(const char* title, char* out, size_t n) {
    snprintf(out, n, "%s", title);
    if (g_mode != 2) return;
    int k = !strcmp(title, "Hero") ? 0 : !strncmp(title, "Player ", 7) ? title[7] - '1' : -1;
    if (k >= 0 && k < 4 && g_ro.name[k][0]) snprintf(out, n, "%s \xC2\xB7 %s", title, g_ro.name[k]);
    else if (!strncmp(title, "Enemy ", 6)) { k = title[6] - '1'; if (k >= 0 && k < 6 && g_ro.enemy[k]) snprintf(out, n, "%s \xC2\xB7 %d HP", title, g_ro.enemy_hp[k]); }
}

static void build_page(void) {
    if (g_mode == 2) { bp_refresh(); return; }
    char q[200]; search_text(q, sizeof q);
    int sel = (int)SendMessageW(g_side, LB_GETCURSEL, 0, 0); if (sel < 0 && !q[0]) return;
    int p = q[0] ? g_search_page : (int)SendMessageW(g_side, LB_GETITEMDATA, (WPARAM)sel, 0);
    if (p == g_search_page && g_cur_page == g_search_page && !strcmp(q, g_last_q)) return;      /* only spaces changed */
    snprintf(g_last_q, sizeof g_last_q, "%s", p == g_search_page ? q : "");
    if (p == g_search_page) split_query(q);
    int special = p == g_on_page || p == g_search_page;
    g_found = 0;
    ShowWindow(g_host, SW_HIDE);                                  /* built out of sight, shown in one go: no controls flying in from the corner */
    int keep = p == g_cur_page ? g_keep_scroll : -1; g_keep_scroll = -1;     /* a section folded open or shut: the page stays where it was */
    card_hide(); clear_rows(); g_scroll = 0; g_cur_page = p;
    SetWindowTextW(g_note, g_mode == 2 ? L"These work on the fight that is going on. Members and enemies that aren't there aren't listed." : L"");
    { char ts[260]; if (p == g_search_page) snprintf(ts, sizeof ts, "Search: %s", q); else snprintf(ts, sizeof ts, "%s", p == g_on_page ? "Enabled" : g_pg[p]);
      wchar_t* tt = wide(ts); SetWindowTextW(g_title, tt); free(tt); }
    {
        char* seen = (char*)calloc((size_t)g_ng + 1, 1);
        if (special) { for (int i = 0; i < g_ne; i++) add_entry(p, i, seen); }
        else {                                                   /* a page: what has no section on top, then each section's title bar and, when open, its rows */
            const char* pg = g_pg[p];
            for (int i = 0; i < g_ne; i++) if (sec_of(pg, &g_e[i]) < 0) add_entry(p, i, seen);
            for (int s = 0; s < g_nsec; s++) {
                if (strcmp(g_sec[s].cat, pg)) continue;
                int nvis = 0; for (int i = 0; i < g_ne; i++) if (sec_of(pg, &g_e[i]) == s && strcmp(g_e[i].kind, "blocked") && who_ok(&g_e[i])) nvis++;
                if (!nvis) continue;                                 /* nobody it is for is there */
                int open = sec_open(s);
                Row* r = add_row(R_HEAD, -1, -1); r->sec = s; r->on = open;
                char lab[200]; sec_label(g_sec[s].title, lab, sizeof lab);
                r->main = mk(L"BUTTON", lab, BS_OWNERDRAW | WS_TABSTOP, g_bold, IDC_ROW0 + g_nrows - 1);
                if (open) for (int i = 0; i < g_ne; i++) if (sec_of(pg, &g_e[i]) == s) add_entry(p, i, seen);
            }
        }
        free(seen);
    }
    update_count();
    lay_rows();
    if (keep > 0) {
        RECT cr; GetClientRect(g_host, &cr); int max = g_total - cr.bottom;
        if (keep > max) keep = max;
        if (keep > 0) { g_scroll = keep; lay_rows(); }
    }
    ShowWindow(g_host, SW_SHOW);
    RedrawWindow(g_host, NULL, NULL, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW);
}

/* a switch was changed (click, or the test): state + game. Returns 0 when the change was refused (the control goes back). */
/* a switch that only takes effect after a restart (a launch option) or a rebuild (a built-in code mod): ask, then do it */
static void restart_game(int rebuild) {
    wchar_t exe[MAX_PATH * 2], *rootw = wide(g_root), cmd[MAX_PATH * 6], script[MAX_PATH * 5];
    (void)exe;
    const wchar_t* cl = GetCommandLineW();
    /* the new game inherits this one's environment, where mod_cheatwin_boot put the launch options: take them all out, the new start sets the ones
     * that are still on (otherwise "Battle any monster" switched off still forced the monster: nothing roamed) */
    for (int i = 0; i < g_ne; i++)
        if (!strcmp(g_e[i].kind, "launch") && strchr(g_e[i].env, '=')) { char nm[128]; snprintf(nm, sizeof nm, "%s", g_e[i].env); *strchr(nm, '=') = 0; strcat(nm, "="); _putenv(nm); }
    if (rebuild) swprintf(script, MAX_PATH * 5, L"ping -n 4 127.0.0.1 >nul & call \"%ls\\mods\\Apply.bat\" apply & start \"\" %ls", rootw, cl);
    else swprintf(script, MAX_PATH * 5, L"ping -n 3 127.0.0.1 >nul & start \"\" %ls", cl);
    swprintf(cmd, MAX_PATH * 6, L"cmd.exe /s /c \"%ls\"", script);
    free(rootw);
    STARTUPINFOW si; memset(&si, 0, sizeof si); si.cb = sizeof si; PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, rebuild ? CREATE_NEW_CONSOLE : CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        MessageBoxW(g_win, L"The game couldn't be restarted. Close it and start it again yourself.", L"Cheats", MB_OK | MB_ICONERROR);
        return;
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    ExitProcess(0);
}

static void maybe_restart(const Ent* e) {
    int launch = !strcmp(e->kind, "launch"), code = !strcmp(e->kind, "code");
    if (!launch && !code) return;
    const wchar_t* msg = launch
        ? L"This setting only takes effect when the game starts again.\n\nRestart the game now? Progress you have not saved is lost: save first."
        : L"This cheat is built into the game: the game has to be rebuilt (a few minutes) and started again.\n\nRebuild and restart now? Progress you have not saved is lost: save first.";
    if (MessageBoxW(g_win, msg, L"Restart needed", MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2) == IDYES) restart_game(code);
}

static int entry_changed(Row* r, int idx, int on) {
    Ent* e = &g_e[idx];
    if (!strcmp(e->kind, "code") && e->file[0]) {              /* a hand-written code file: its own switch, needs the build */
        SetWindowTextW(g_note, L"This one is switched in its file (mods\\system\\cheats) and needs a rebuild.");
        return 0;
    }
    apply(idx, on);
    (void)r; update_count();
    SetWindowTextW(g_note, L"");
    maybe_restart(e);
    return 1;
}

static void group_changed(Row* r, int sel) {
    if (sel == 0) {
        for (int k = 0; k < r->nm; k++) {
            Ent* m = &g_e[r->members[k]];
            if (ent_on(m) && !(!strcmp(m->kind, "code") && m->file[0])) { apply(r->members[k], 0); SetWindowTextW(g_note, L""); update_count(); maybe_restart(m); }
        }
        update_count(); return;
    }
    if (!entry_changed(r, r->members[sel - 1], 1)) {           /* refused: show what is really on */
        int cur = 0; for (int k = 0; k < r->nm; k++) if (ent_on(&g_e[r->members[k]])) cur = k + 1;
        SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)cur, 0);
    }
}

static void layout(int cw, int ch) {
    int sw = g_mode == 2 ? 0 : SIDE_W;                 /* the battle window has no sidebar */
    MoveWindow(g_side, 0, SEARCH_H, SIDE_W, ch - SEARCH_H, TRUE);
    MoveWindow(g_search, 24, 14, SIDE_W - 48, 18, TRUE);
    MoveWindow(g_title, sw + PAD_X, 12, cw - sw - 2 * PAD_X - 214, 28, TRUE);
    MoveWindow(g_count, sw + PAD_X, 41, cw - sw - 2 * PAD_X - 214, 18, TRUE);
    MoveWindow(g_import, cw - PAD_X - 102, 16, 102, 30, TRUE);
    MoveWindow(g_share, cw - PAD_X - 102 - 8 - 100, 16, 100, 30, TRUE);
    MoveWindow(g_host, sw, 66, cw - sw, ch - 66 - 50, TRUE);
    if (g_bp) MoveWindow(g_bp, 0, 66, cw, ch - 66 - 50, TRUE);
    MoveWindow(g_note, sw + PAD_X, ch - 34, cw - sw - 2 * PAD_X - 262, 18, TRUE);
    MoveWindow(g_close, cw - PAD_X - 92, ch - 42, 92, 32, TRUE);
    if (g_nrows) lay_rows();
}

static Row* row_of_id(int id) { int i = id - IDC_ROW0; return i >= 0 && i < g_nrows ? &g_rows[i] : NULL; }

static void test_step(int step);

/* ---- the hover card: the cheat's longer explanation in a small window of its own, so it can reach past the window's edge
 * (kept on the screen it is on). Shown when the mouse rests on a row for a moment; gone when the mouse leaves, a click, a key,
 * the wheel or another page. */
static HWND g_card;
static int g_card_row = -1, g_card_want = -1;
static wchar_t g_card_text[2100];
#define IDT_CARD 201
#define IDT_CARDPOLL 202
#define CARD_PAD 12
#define CARD_W 380
static void card_hide(void) {
    g_card_want = -1; g_card_row = -1;
    if (g_card && IsWindowVisible(g_card)) ShowWindow(g_card, SW_HIDE);
}
static int row_at(POINT screen) {
    POINT pt = screen; ScreenToClient(g_host, &pt);
    for (int i = 0; i < g_nrows; i++) { int t = g_rows[i].y - g_scroll; if (pt.y >= t && pt.y < t + g_rows[i].h) return i; }
    return -1;
}
static void card_mouse(POINT screen) {
    int i = row_at(screen);
    if (i == g_card_row || i == g_card_want) return;
    card_hide();
    if (i < 0) return;
    g_card_want = i;
    SetTimer(g_host, IDT_CARD, 450, NULL); SetTimer(g_host, IDT_CARDPOLL, 120, NULL);
}
static void card_show_at(int i, POINT pt);
static void card_show(int i) { POINT pt; GetCursorPos(&pt); card_show_at(i, pt); }
static void card_show_at(int i, POINT pt) {
    if (!g_card || i < 0 || i >= g_nrows) return;
    Row* r = &g_rows[i];
    hover_text(r->kind == R_GROUP ? g_g[r->gi].about : r->idx >= 0 ? g_e[r->idx].about : NULL, g_card_text, 2100);
    if (!g_card_text[0]) { g_card_want = -1; return; }
    HDC dc = GetDC(g_card); HGDIOBJ o = SelectObject(dc, g_small);
    RECT m = { 0, 0, CARD_W - 2 * CARD_PAD, 0 }; DrawTextW(dc, g_card_text, -1, &m, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX);
    SelectObject(dc, o); ReleaseDC(g_card, dc);
    int w = m.right + 2 * CARD_PAD, ht = m.bottom + 2 * CARD_PAD;
    MONITORINFO mi; memset(&mi, 0, sizeof mi); mi.cbSize = sizeof mi; GetMonitorInfoW(MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST), &mi);
    RECT wa = mi.rcWork; int x = pt.x + 16, y = pt.y + 22;
    if (x + w > wa.right - 4) x = wa.right - 4 - w;
    if (x < wa.left + 4) x = wa.left + 4;
    if (y + ht > wa.bottom - 4) y = pt.y - ht - 12;                     /* no room below: above the mouse */
    if (y < wa.top + 4) y = wa.top + 4;
    g_card_row = i; g_card_want = -1;
    SetWindowPos(g_card, HWND_TOPMOST, x, y, w, ht, SWP_NOACTIVATE | SWP_SHOWWINDOW);
    InvalidateRect(g_card, NULL, FALSE);
}
static LRESULT CALLBACK cardproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    if (m == WM_PAINT) {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); RECT rc; GetClientRect(h, &rc); Cv c;
        if (cv_begin(&c, rc.right, rc.bottom, RGB(47, 49, 56))) {
            cv_box(&c, 0, 0, (float)rc.right, (float)rc.bottom, 0, RGB(78, 81, 90), 1.0f);     /* a thin edge */
            RECT tr = { CARD_PAD, CARD_PAD, rc.right - CARD_PAD, rc.bottom - CARD_PAD };
            cv_text(&c, g_card_text, tr, g_small, COL_TEXT, DT_WORDBREAK);
            cv_end(&c, dc, 0, 0);
        }
        EndPaint(h, &ps); return 0;
    }
    if (m == WM_ERASEBKGND) return 1;
    if (m == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
    if (m == WM_NCHITTEST) return HTTRANSPARENT;
    return DefWindowProcW(h, m, wp, lp);
}

/* a section's title bar: an arrow (right: shut, down: open), the title, and how many of its cheats are on */
static void draw_head(const DRAWITEMSTRUCT* d, const Row* r) {
    RECT rc = d->rcItem; int w = rc.right - rc.left, ht = rc.bottom - rc.top, hot = g_hot == d->hwndItem; Cv c;
    if (!cv_begin(&c, w, ht, COL_BG)) return;
    int total = 0, on = 0; page_count(g_sec[r->sec].cat, r->sec, &total, &on);
    cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)ht - 0.5f, 9, hot ? RGB(56, 58, 66) : RGB(44, 46, 52), 0);
    if ((d->itemState & ODS_FOCUS) && !(d->itemState & ODS_NOFOCUSRECT)) cv_box(&c, 0.5f, 0.5f, (float)w - 0.5f, (float)ht - 0.5f, 9, COL_ACCENT, 1.2f);
    float ax = 18, ay = (float)ht / 2; COLORREF ac = on ? COL_ACCENT : COL_GRAY;
    if (r->on) { cv_line(&c, ax - 4, ay - 2, ax, ay + 2, 1.7f, ac); cv_line(&c, ax, ay + 2, ax + 4, ay - 2, 1.7f, ac); }
    else { cv_line(&c, ax - 2, ay - 4, ax + 2, ay, 1.7f, ac); cv_line(&c, ax + 2, ay, ax - 2, ay + 4, 1.7f, ac); }
    wchar_t t[200]; GetWindowTextW(d->hwndItem, t, 200);
    RECT tr = { 34, 0, w - 130, ht }; cv_text(&c, t, tr, g_bold, COL_TEXT, DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);
    wchar_t cnt[64]; if (on) swprintf(cnt, 64, L"%d of %d on", on, total); else swprintf(cnt, 64, L"%d cheat%ls", total, total == 1 ? L"" : L"s");
    RECT cr = { w - 160, 0, w - 14, ht }; cv_text(&c, cnt, cr, g_small, on ? COL_ACCENT : COL_GRAY, DT_SINGLELINE | DT_VCENTER | DT_RIGHT);
    cv_end(&c, d->hDC, rc.left, rc.top);
}

/* fold section s open or shut (posted: the clicked title bar is replaced by the new page's) */
#define WM_TOGGLE_SECTION (WM_APP + 2)
static void toggle_section(int s) {
    char k[300]; sec_key(s, k, sizeof k);
    if (!strcmp(g_sec[s].cat, "Live battle")) { if (s < 128) g_bshut[s] ^= 1; }
    else { EnterCriticalSection(&g_cs); st_set("open", k, !st_has("open", k)); st_save(); LeaveCriticalSection(&g_cs); }
    g_keep_scroll = g_scroll; build_page();
    for (int i = 0; i < g_nrows; i++) if (g_rows[i].kind == R_HEAD && g_rows[i].sec == s) { SetFocus(g_rows[i].main); break; }
}

/* the scrolling panel */
static LRESULT CALLBACK hostproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_CTLCOLORSTATIC: case WM_CTLCOLORBTN: {
        HDC dc = (HDC)wp; SetBkColor(dc, COL_BG); SetBkMode(dc, OPAQUE);
        SetTextColor(dc, GetWindowLongPtrW((HWND)lp, GWLP_USERDATA) == 1 ? COL_GRAY : COL_TEXT);
        return (LRESULT)g_white;
    }
    case WM_ERASEBKGND: { RECT r; GetClientRect(h, &r); FillRect((HDC)wp, &r, g_white); return 1; }
    case WM_DRAWITEM: {
        DRAWITEMSTRUCT* d = (DRAWITEMSTRUCT*)lp; Row* r = row_of_id((int)d->CtlID);
        if (r && r->sub == d->hwndItem) {                         /* the grey line, buttons in colour (drawn off screen, copied in one go) */
            wchar_t t[600]; GetWindowTextW(d->hwndItem, t, 600);
            RECT rc = d->rcItem; Cv c;
            if (!cv_begin(&c, rc.right - rc.left, rc.bottom - rc.top, COL_BG)) return TRUE;
            RECT inner = { 0, 0, c.w, c.h };
            HGDIOBJ of = SelectObject(c.dc, g_small); rich_text(c.dc, t, inner, 1); SelectObject(c.dc, of);
            cv_end(&c, d->hDC, rc.left, rc.top);
            return TRUE;
        }
        if (r && r->btn == d->hwndItem) { draw_pill_button(d); return TRUE; }
        if (r && r->kind == R_HEAD && r->main == d->hwndItem) { draw_head(d, r); return TRUE; }
        if (!r || r->main != d->hwndItem) break;
        {   /* the switch: a pill with a round knob, smooth edges; lighter under the mouse */
            RECT rc = d->rcItem; int w = rc.right - rc.left, ht = rc.bottom - rc.top, on = r->on, hot = g_hot == d->hwndItem; Cv c;
            if (!cv_begin(&c, w, ht, COL_BG)) return TRUE;
            float cy = (float)ht / 2, tw = 36, th = 20;
            int dis = !IsWindowEnabled(d->hwndItem);                 /* locked in a session: dimmed, no hover */
            if (dis) hot = 0;
            COLORREF track = dis ? (on ? RGB(110, 94, 54) : RGB(50, 51, 56)) : on ? (hot ? RGB(240, 194, 86) : COL_ACCENT) : (hot ? RGB(86, 88, 97) : COL_OFF);
            cv_box(&c, 0, cy - th / 2, tw, cy + th / 2, th / 2, track, 0);
            if (!on) cv_box(&c, 0, cy - th / 2, tw, cy + th / 2, th / 2, hot ? RGB(110, 113, 123) : RGB(92, 94, 103), 1.0f);
            float k = 14, kx = on ? tw - 3 - k : 3;
            cv_box(&c, kx, cy - k / 2 + 1, kx + k, cy + k / 2 + 1, k / 2, on ? RGB(170, 128, 30) : RGB(40, 41, 46), 0);   /* soft shadow */
            cv_box(&c, kx, cy - k / 2, kx + k, cy + k / 2, k / 2, on ? RGB(255, 255, 255) : RGB(214, 215, 221), 0);
            if ((d->itemState & ODS_FOCUS) && !(d->itemState & ODS_NOFOCUSRECT)) cv_box(&c, -0.5f, cy - th / 2 - 3, tw + 3, cy + th / 2 + 3, th / 2 + 3, COL_ACCENT, 1.2f);
            wchar_t t[400]; GetWindowTextW(d->hwndItem, t, 400);
            RECT tr = { 48, 0, w, ht }; cv_text(&c, t, tr, g_font, dis ? COL_GRAY : COL_TEXT, DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);
            cv_end(&c, d->hDC, rc.left, rc.top);
            return TRUE;
        }
    }
    case WM_PAINT: {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); RECT cr; GetClientRect(h, &cr);
        HPEN pen = CreatePen(PS_SOLID, 1, COL_LINE); HGDIOBJ old = SelectObject(dc, pen);
        for (int i = 0; i < g_nrows; i++) { int y = g_rows[i].y + g_rows[i].h - 1 - g_scroll; MoveToEx(dc, PAD_X, y, NULL); LineTo(dc, cr.right - PAD_X, y); }
        SelectObject(dc, old); DeleteObject(pen); EndPaint(h, &ps); return 0;
    }
    case WM_NOTIFY: {
        NMTTDISPINFOW* di = (NMTTDISPINFOW*)lp;
        if (di->hdr.hwndFrom == g_tip && di->hdr.code == TTN_GETDISPINFOW) {
            Row* r = (Row*)NULL; int i = (int)di->hdr.idFrom; if (i >= 0 && i < g_nrows) r = &g_rows[i];
            g_tiptext[0] = 0;
            if (r && r->kind == R_GROUP) hover_text(g_g[r->gi].about, g_tiptext, 2100);
            else if (r && r->idx >= 0) hover_text(g_e[r->idx].about, g_tiptext, 2100);
            di->lpszText = g_tiptext; return 0;
        }
        break;
    }
    case WM_VSCROLL: {
        SCROLLINFO si; memset(&si, 0, sizeof si); si.cbSize = sizeof si; si.fMask = SIF_ALL; GetScrollInfo(h, SB_VERT, &si);
        int pos = g_scroll;
        switch (LOWORD(wp)) {
        case SB_LINEUP: pos -= 40; break; case SB_LINEDOWN: pos += 40; break;
        case SB_PAGEUP: pos -= (int)si.nPage; break; case SB_PAGEDOWN: pos += (int)si.nPage; break;
        case SB_THUMBTRACK: case SB_THUMBPOSITION: pos = si.nTrackPos; break;
        case SB_TOP: pos = 0; break; case SB_BOTTOM: pos = g_total; break;
        }
        scroll_to(pos); return 0;
    }
    case WM_MOUSEWHEEL: card_hide(); scroll_to(g_scroll - (short)HIWORD(wp) * 60 / WHEEL_DELTA); return 0;
    case WM_TIMER:
        if (wp == IDT_CARD) { KillTimer(h, IDT_CARD); if (g_card_want >= 0) card_show(g_card_want); }
        else if (wp == IDT_CARDPOLL) {                       /* the mouse left the page (or the window went to the back): the card goes */
            POINT pt; GetCursorPos(&pt); HWND under = WindowFromPoint(pt);
            if (!(under == g_host || (under && IsChild(g_host, under))) || GetForegroundWindow() != g_win) { card_hide(); KillTimer(h, IDT_CARDPOLL); }
        }
        return 0;
    case WM_SIZE: if (g_nrows) lay_rows(); return 0;
    case WM_TOGGLE_SECTION: toggle_section((int)wp); return 0;
    case WM_REFRESH_PAGE: g_keep_scroll = g_scroll; g_last_q[0] = 0; build_page(); return 0;
    case WM_COMMAND: {
        Row* r = row_of_id(LOWORD(wp)); if (!r) break;
        int code = HIWORD(wp);
        if (r->kind == R_HEAD && code == BN_CLICKED) { PostMessageW(h, WM_TOGGLE_SECTION, (WPARAM)r->sec, 0); return 0; }
        if (r->kind == R_GROUP && code == CBN_SELCHANGE) group_changed(r, (int)SendMessageW(r->combo, CB_GETCURSEL, 0, 0));
        else if (r->kind == R_CHECK && (HWND)lp == r->main && code == BN_CLICKED) {
            int on = !r->on;
            if (entry_changed(r, r->idx, on)) r->on = on;
            InvalidateRect(r->main, NULL, FALSE);
        } else if (r->btn && (HWND)lp == r->btn && code == BN_CLICKED && !strcmp(g_e[r->idx].kind, "ui")) {
            g_mode = 2; mod_roster(&g_ro); PostMessageW(g_win, WM_SHOW_CHEATS, 0, 0);          /* the battle window (cards) */
        } else if (r->btn && (HWND)lp == r->btn && code == BN_CLICKED && !strcmp(g_e[r->idx].mode, "toggle")) {     /* Vanish: on, the button shows it, again: off */
            int on = !r->on;
            if (entry_changed(r, r->idx, on)) { r->on = on; SetWindowTextW(r->btn, on ? L"Vanished \u00B7 show up" : L"Vanish"); }
            InvalidateRect(r->btn, NULL, FALSE);
        } else if (r->btn && (HWND)lp == r->btn && code == BN_CLICKED && !strcmp(g_e[r->idx].kind, "live")) {
            EnterCriticalSection(&g_cs); send_run(r->idx); LeaveCriticalSection(&g_cs);
        }
        return 0;
    }
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void draw_side(DRAWITEMSTRUCT* d) {
    int data = d->itemID == (UINT)-1 ? 0 : (int)d->itemData; int sel = (d->itemState & ODS_SELECTED) != 0;
    HDC dc = d->hDC; RECT r = d->rcItem;
    FillRect(dc, &r, g_gray);
    if (d->itemID == (UINT)-1) return;
    if (data == g_on_page) { HPEN pen = CreatePen(PS_SOLID, 1, COL_LINE); HGDIOBJ o = SelectObject(dc, pen); MoveToEx(dc, r.left + 16, r.bottom - 1, NULL); LineTo(dc, r.right - 16, r.bottom - 1); SelectObject(dc, o); DeleteObject(pen); }
    if (sel) {
        RECT b = { r.left + 6, r.top + 2, r.right - 6, r.bottom - 2 }; HBRUSH hb = CreateSolidBrush(RGB(42, 44, 49)); FillRect(dc, &b, hb); DeleteObject(hb);
        RECT bar = { r.left + 6, r.top + 8, r.left + 9, r.bottom - 8 }; hb = CreateSolidBrush(COL_ACCENT); FillRect(dc, &bar, hb); DeleteObject(hb);
    }
    wchar_t t[200]; SendMessageW(d->hwndItem, LB_GETTEXT, d->itemID, (LPARAM)t);
    SetBkMode(dc, TRANSPARENT); SetTextColor(dc, COL_TEXT); HGDIOBJ o = SelectObject(dc, sel ? g_bold : g_font);
    RECT tr = { r.left + 20, r.top, r.right - 8, r.bottom }; DrawTextW(dc, t, -1, &tr, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS);
    SelectObject(dc, o);
}

/* ---- sharing the switches with friends: one line of text on the clipboard (paste it in a chat), Import reads it back.
 * "DQIX-CHEATS/1/<base64 of the state file's lines>": live, code and launch lines only (not which sections are open). */
#define SHARE_TAG "DQIX-CHEATS/1/"
static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static char* b64_enc(const unsigned char* s, size_t n) {
    char* o = (char*)malloc(n / 3 * 4 + 8); size_t k = 0; if (!o) return NULL;
    for (size_t i = 0; i < n; i += 3) {
        uint32_t v = (uint32_t)s[i] << 16 | (i + 1 < n ? (uint32_t)s[i + 1] << 8 : 0) | (i + 2 < n ? s[i + 2] : 0);
        o[k++] = b64[v >> 18 & 63]; o[k++] = b64[v >> 12 & 63]; o[k++] = i + 1 < n ? b64[v >> 6 & 63] : '='; o[k++] = i + 2 < n ? b64[v & 63] : '=';
    }
    o[k] = 0; return o;
}
static char* b64_dec(const char* s, size_t* n) {                 /* stops at the first character that isn't base64 */
    size_t len = 0; while (s[len] && (strchr(b64, s[len]) || s[len] == '=')) len++;
    char* o = (char*)malloc(len / 4 * 3 + 4); size_t k = 0; uint32_t v = 0; int bits = 0; if (!o) return NULL;
    for (size_t i = 0; i < len && s[i] != '='; i++) {
        v = v << 6 | (uint32_t)(strchr(b64, s[i]) - b64); bits += 6;
        if (bits >= 8) { bits -= 8; o[k++] = (char)(v >> bits & 255); }
    }
    o[k] = 0; *n = k; return o;
}
static int clip_put(const wchar_t* t) {
    size_t n = (wcslen(t) + 1) * sizeof *t; HGLOBAL g = GlobalAlloc(GMEM_MOVEABLE, n); if (!g) return 0;
    void* d = GlobalLock(g); if (!d) { GlobalFree(g); return 0; }
    memcpy(d, t, n); GlobalUnlock(g);
    if (!OpenClipboard(g_win)) { GlobalFree(g); return 0; }
    EmptyClipboard(); int ok = SetClipboardData(CF_UNICODETEXT, g) != NULL; CloseClipboard();
    if (!ok) GlobalFree(g);
    return ok;
}
static char* clip_get(void) {                                    /* UTF-8, or NULL */
    if (!OpenClipboard(g_win)) return NULL;
    char* out = NULL; HANDLE g = GetClipboardData(CF_UNICODETEXT);
    const wchar_t* w = g ? (const wchar_t*)GlobalLock(g) : NULL;
    if (w) {
        int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
        out = n > 0 ? (char*)malloc((size_t)n) : NULL;
        if (out) WideCharToMultiByte(CP_UTF8, 0, w, -1, out, n, NULL, NULL);
        GlobalUnlock(g);
    }
    CloseClipboard(); return out;
}

/* the line Share puts on the clipboard (NULL: nothing is on); *count = how many cheats */
static char* share_line(int* count) {
    size_t cap = 256, len = 0; char* txt = (char*)malloc(cap); *count = 0;
    if (!txt) return NULL;
    txt[0] = 0;
    EnterCriticalSection(&g_cs);
    for (int i = 0; i < g_ne; i++) {
        if (!strcmp(g_e[i].kind, "blocked") || !ent_on(&g_e[i])) continue;
        size_t need = strlen(g_e[i].id) + 12;
        if (len + need >= cap) { char* nt = (char*)realloc(txt, cap = (cap + need) * 2); if (!nt) break; txt = nt; }
        len += (size_t)snprintf(txt + len, cap - len, "%s %s\n", skind(&g_e[i]), g_e[i].id); (*count)++;
    }
    LeaveCriticalSection(&g_cs);
    if (!*count) { free(txt); return NULL; }
    char* enc = b64_enc((const unsigned char*)txt, len); free(txt); if (!enc) return NULL;
    size_t n = strlen(enc) + 200; char* line = (char*)malloc(n);
    if (line) snprintf(line, n, "DQIX Enhanced cheats (%d on) - copy this line, then press Import in the Cheats window: " SHARE_TAG "%s", *count, enc);
    free(enc); return line;
}

static void share_settings(void) {
    int count; char* line = share_line(&count);
    if (!line) { SetWindowTextW(g_note, L"Nothing is switched on: there is nothing to share yet."); return; }
    wchar_t* w = wide(line);
    if (w && clip_put(w)) {
        wchar_t note[160]; swprintf(note, 160, L"Copied %d cheat%ls to the clipboard: paste it to your friends, they press Import.", count, count == 1 ? L"" : L"s");
        SetWindowTextW(g_note, note);
    } else SetWindowTextW(g_note, L"The clipboard couldn't be used: try again.");
    free(w); free(line);
}

/* text with SHARE_TAG in it -> want[i] = 1 for each entry it switches on; returns how many, *missing = ids this list doesn't have */
static int read_shared(const char* text, int* want, int* missing) {
    const char* at = text ? strstr(text, SHARE_TAG) : NULL; int found = 0; *missing = 0;
    if (!at) return -1;
    size_t n = 0; char* txt = b64_dec(at + strlen(SHARE_TAG), &n);
    for (char* line = txt; txt && line && *line;) {
        char* nl = strchr(line, '\n'); if (nl) *nl = 0;
        char* sp = strchr(line, ' ');
        if (sp) {
            *sp = 0; int hit = -1;
            for (int i = 0; i < g_ne && hit < 0; i++) if (!strcmp(g_e[i].id, sp + 1) && !strcmp(skind(&g_e[i]), line) && strcmp(g_e[i].kind, "blocked")) hit = i;
            if (hit >= 0 && !want[hit]) { want[hit] = 1; found++; } else if (hit < 0) (*missing)++;
        }
        line = nl ? nl + 1 : NULL;
    }
    free(txt);
    return found;
}

/* switch exactly the wanted entries on (and everything else off); -> an entry that needs a restart or rebuild, or -1 */
static int apply_wanted(const int* want) {
    int restart = -1;
    for (int i = 0; i < g_ne; i++) {
        int fixed = !strcmp(g_e[i].kind, "code") && g_e[i].file[0];      /* switched in its file: left as it is */
        int now = ent_on(&g_e[i]), to = want[i];
        if (fixed || now == to) continue;
        if (strcmp(g_e[i].kind, "live") && restart < 0) restart = i;
        if (!to) apply(i, 0);
    }
    for (int i = 0; i < g_ne; i++) if (want[i] && !ent_on(&g_e[i]) && !(!strcmp(g_e[i].kind, "code") && g_e[i].file[0])) apply(i, 1);
    return restart;
}

static void import_settings(void) {
    char* clip = clip_get();
    int* want = (int*)calloc((size_t)g_ne + 1, sizeof *want); int missing = 0;
    int found = want ? read_shared(clip, want, &missing) : -1;
    free(clip);
    if (found < 0) {
        free(want);
        MessageBoxW(g_win, L"The clipboard has no shared cheat settings.\n\nCopy the whole line a friend sent you (it has DQIX-CHEATS in it), then press Import again.", L"Import", MB_OK | MB_ICONINFORMATION);
        return;
    }
    if (!found) {
        free(want);
        MessageBoxW(g_win, L"None of the shared cheats is in this game's list (a different game version or an older mods folder?).", L"Import", MB_OK | MB_ICONINFORMATION);
        return;
    }
    wchar_t msg[400];
    swprintf(msg, 400, L"Switch on the %d cheat%ls from the shared settings?\n\nEverything that is on now is switched off first.%ls", found, found == 1 ? L"" : L"s",
             missing ? L"\n\nSome of the shared cheats aren't in this game's list: they are left out." : L"");
    if (MessageBoxW(g_win, msg, L"Import", MB_YESNO | MB_ICONQUESTION) != IDYES) { free(want); return; }
    int restart = apply_wanted(want);
    free(want);
    build_page();
    wchar_t note[120]; swprintf(note, 120, L"Imported: %d cheat%ls on.", found, found == 1 ? L"" : L"s"); SetWindowTextW(g_note, note);
    if (restart >= 0) maybe_restart(&g_e[restart]);
}

/* ======================================================================== the battle window: cards for the party and the enemies
 * Only who is really in the fight gets a card (the party members the game has in its party, the enemies with HP left). A card has the member's
 * letter in a colour, the name, HP and MP bars with the numbers as they are now, and one big button per cheat (a glyph and a short word): a click
 * does it at once; a gold button is a switch that stays on. Enemy names come from mods\system\bin\monsters.tsv (the species whose maximum HP and
 * MP match the enemy's record, when that is unique), else "Enemy n". */
typedef struct { RECT r; int ent; } BBtn;
typedef struct { RECT r; int who; } BCard;
static BBtn g_bb[160]; static int g_nbb;
static BCard g_bc[12]; static int g_nbc;
static int g_bp_scroll, g_bp_total, g_bp_hot = -1, g_bp_flash = -1, g_bp_ehdr = -1;
static HFONT g_sym;
typedef struct { int hp, mp; char* name; } MonName;
static MonName* g_mn; static int g_nmn, g_mn_loaded;

static void load_monsters(void) {
    if (g_mn_loaded) return;
    g_mn_loaded = 1;
    char path[MAX_PATH * 2 + 64]; snprintf(path, sizeof path, "%s\\mods\\system\\bin\\monsters.tsv", g_root);
    char* t = slurp(path, NULL); if (!t) return;
    for (char* line = t; line && *line;) {
        char* nl = strchr(line, '\n'); if (nl) *nl = 0;
        int hp, mp; char nm[80];
        if (sscanf(line, "%d\t%d\t%79[^\r\n]", &hp, &mp, nm) == 3) {
            g_mn = (MonName*)realloc(g_mn, (size_t)(g_nmn + 1) * sizeof *g_mn);
            g_mn[g_nmn].hp = hp; g_mn[g_nmn].mp = mp; g_mn[g_nmn].name = xdup(nm, strlen(nm)); g_nmn++;
        }
        line = nl ? nl + 1 : NULL;
    }
    free(t);
}
static const char* enemy_name(int n) {
    load_monsters();
    for (int i = 0; i < g_nmn; i++) if (g_mn[i].hp == g_ro.enemy_max_hp[n] && g_mn[i].mp == g_ro.enemy_max_mp[n]) return g_mn[i].name;
    return NULL;
}

static const wchar_t* glyph_of(const Ent* e) {
    static const struct { const char* s; const wchar_t* g; } k[] = {
        { ":keep", L"∞" }, { ":max", L"♥" }, { ":tension", L"⚡" }, { ":coup", L"⚔" }, { ":invincible", L"✦" },
        { ":defeat", L"☠" }, { ":hp1", L"♡" }, { ":mp0", L"✖" }, { ":sleep", L"☾" }, { ":poison", L"☣" },
        { ":stun", L"✺" }, { ":confuse", L"?" } };
    for (size_t i = 0; i < sizeof k / sizeof *k; i++) if (strstr(e->id, k[i].s)) return k[i].g;
    return L"•";
}

/* one card (who 0..3 a party member, 4..9 an enemy) at x, y, width w; returns its bottom. The buttons are collected too. */
static int bp_card(int who, int x, int y, int w, HDC mdc) {
    int enemy = who >= 4;
    char tag[3] = { enemy ? 'e' : 'p', (char)('1' + (enemy ? who - 4 : who)), 0 };
    int cx = x + 14, cy = y + 68, last = cy;
    for (int i = 0; i < g_ne; i++) {
        const Ent* e = &g_e[i];
        if (strcmp(e->cat, "Live battle") || strcmp(e->who, tag)) continue;
        wchar_t* lw = wide(e->name); SIZE sz; GetTextExtentPoint32W(mdc, lw, (int)wcslen(lw), &sz); free(lw);
        int bw = 30 + sz.cx + 14;
        if (cx + bw > x + w - 14 && cx > x + 14) { cx = x + 14; cy += 38; }
        if (g_nbb < 160) { RECT r = { cx, cy, cx + bw, cy + 32 }; g_bb[g_nbb].r = r; g_bb[g_nbb].ent = i; g_nbb++; }
        cx += bw + 8; last = cy + 32;
    }
    int bottom = last + 14;
    if (g_nbc < 12) { RECT r = { x, y, x + w, bottom }; g_bc[g_nbc].r = r; g_bc[g_nbc].who = who; g_nbc++; }
    return bottom;
}

/* the cards and buttons for a panel of width w (rectangles in the panel's own coordinates, before scrolling) */
static void bp_build(int w) {
    g_nbb = g_nbc = 0; g_bp_total = 0; g_bp_ehdr = -1;
    if (!g_ro.inbattle) return;
    HDC mdc = GetDC(NULL); HGDIOBJ old = SelectObject(mdc, g_font);
    int pad = 16, gap = 12, two = w >= 640, colw = two ? (w - 3 * pad) / 2 : w - 2 * pad;
    int yp = 40, ye = 40, anye = 0;
    for (int n = 0; n < 6; n++) anye |= g_ro.enemy[n];
    for (int i = 0; i < 4; i++) if (g_ro.party[i]) yp = bp_card(i, pad, yp, colw, mdc) + gap;
    if (!two) { ye = yp + 4; if (anye) { g_bp_ehdr = ye; ye += 28; } }
    for (int n = 0; n < 6; n++) if (g_ro.enemy[n]) ye = bp_card(4 + n, two ? 2 * pad + colw : pad, ye, colw, mdc) + gap;
    g_bp_total = (yp > ye ? yp : ye) + 6;
    SelectObject(mdc, old); ReleaseDC(NULL, mdc);
}

static COLORREF who_color(int who) {
    static const COLORREF c[4] = { RGB(226, 178, 66), RGB(110, 160, 255), RGB(110, 210, 150), RGB(235, 130, 190) };
    return who < 4 ? c[who] : RGB(226, 96, 96);
}
static void bar(Cv* c, float x, float y, float w, float h, int cur, int mx, COLORREF col) {
    cv_box(c, x, y, x + w, y + h, h / 2, RGB(30, 31, 35), 0);
    if (mx <= 0) return;
    float f = (float)cur / (float)mx; if (f > 1) f = 1; if (f < 0) f = 0;
    if (f > 0) cv_box(c, x, y, x + fmaxf(h, w * f), y + h, h / 2, col, 0);
}
static COLORREF hp_color(int cur, int mx) { return mx <= 0 || cur * 2 > mx ? RGB(96, 200, 120) : cur * 4 > mx ? RGB(232, 190, 80) : RGB(232, 96, 96); }
static void put(Cv* c, const char* s, RECT r, HFONT f, COLORREF col, UINT fmt) { wchar_t* w = wide(s); cv_text(c, w, r, f, col, fmt); free(w); }

static void bp_paint(HWND h) {
    PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); RECT cr; GetClientRect(h, &cr);
    bp_build(cr.right);
    int maxs = g_bp_total - cr.bottom; if (maxs < 0) maxs = 0; if (g_bp_scroll > maxs) g_bp_scroll = maxs; if (g_bp_scroll < 0) g_bp_scroll = 0;
    int oy = -g_bp_scroll;
    Cv c;
    if (cv_begin(&c, cr.right, cr.bottom, COL_BG)) {
        if (!g_ro.inbattle) {
            RECT r = { 20, cr.bottom / 2 - 44, cr.right - 20, cr.bottom / 2 - 8 };
            cv_text(&c, L"No battle right now", r, g_head, COL_TEXT, DT_CENTER | DT_SINGLELINE);
            RECT r2 = { 20, cr.bottom / 2 + 2, cr.right - 20, cr.bottom / 2 + 50 };
            cv_text(&c, L"Start a fight: your party and the enemies show up here, ready to click.", r2, g_font, COL_GRAY, DT_CENTER | DT_WORDBREAK);
        } else {
            int two = cr.right >= 640, colw = two ? (cr.right - 48) / 2 : cr.right - 32;
            { RECT r = { 18, 12 + oy, 18 + colw, 34 + oy }; put(&c, "PARTY", r, g_bold, COL_GRAY, DT_SINGLELINE); }
            if (two) { RECT r = { 32 + colw, 12 + oy, cr.right - 10, 34 + oy }; put(&c, "ENEMIES", r, g_bold, COL_GRAY, DT_SINGLELINE); }
            else if (g_bp_ehdr >= 0) { RECT r = { 18, g_bp_ehdr + oy, cr.right - 10, g_bp_ehdr + 22 + oy }; put(&c, "ENEMIES", r, g_bold, COL_GRAY, DT_SINGLELINE); }
            for (int k = 0; k < g_nbc; k++) {
                const BCard* bc = &g_bc[k]; int who = bc->who, enemy = who >= 4, n = who - 4;
                float x0 = (float)bc->r.left, y0 = (float)(bc->r.top + oy), x1 = (float)bc->r.right, y1 = (float)(bc->r.bottom + oy);
                if (y1 < 0 || y0 > cr.bottom) continue;
                cv_box(&c, x0, y0, x1, y1, 12, COL_LINE, 1.0f); cv_box(&c, x0 + 1, y0 + 1, x1 - 1, y1 - 1, 11, COL_BOX, 0);
                cv_box(&c, x0 + 14, y0 + 12, x0 + 58, y0 + 56, 22, who_color(who), 0);
                int down = !enemy && g_ro.hpmax[who] > 0 && g_ro.hp[who] == 0;                  /* a fallen member: red name, HP 0 */
                char nm[40]; const char* name = enemy ? enemy_name(n) : g_ro.name[who];
                if (!name || !name[0]) snprintf(nm, sizeof nm, "Enemy %d", n + 1); else snprintf(nm, sizeof nm, "%s", name);
                RECT lr = { (int)x0 + 14, (int)y0 + 12, (int)x0 + 58, (int)y0 + 56 };
                if (enemy) cv_text(&c, L"☠", lr, g_sym, RGB(40, 24, 24), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
                else { char l[2] = { nm[0], 0 }; put(&c, l, lr, g_head, RGB(30, 30, 34), DT_CENTER | DT_VCENTER | DT_SINGLELINE); }
                RECT nr = { (int)x0 + 68, (int)y0 + 10, (int)x1 - 110, (int)y0 + 30 };
                put(&c, nm, nr, g_bold, down ? RGB(240, 104, 104) : COL_TEXT, DT_SINGLELINE | DT_END_ELLIPSIS);
                { char sub[40]; if (enemy) snprintf(sub, sizeof sub, "Enemy %d", n + 1); else if (who == 0) snprintf(sub, sizeof sub, "Hero"); else snprintf(sub, sizeof sub, "Player %d", who + 1);
                  RECT sr = { (int)x1 - 104, (int)y0 + 11, (int)x1 - 14, (int)y0 + 30 }; put(&c, sub, sr, g_small, COL_GRAY, DT_RIGHT | DT_SINGLELINE); }
                int hp = enemy ? g_ro.enemy_hp[n] : g_ro.hp[who], hm = enemy ? g_ro.enemy_max_hp[n] : g_ro.hpmax[who];
                float bx = x0 + 68, bw = x1 - 14 - bx - 74;
                bar(&c, bx, y0 + 38, bw, 8, hp, hm, hp_color(hp, hm));
                { char t[40]; if (down) snprintf(t, sizeof t, "Fallen"); else if (hm > 0) snprintf(t, sizeof t, "HP %d/%d", hp, hm); else snprintf(t, sizeof t, "HP %d", hp);
                  RECT tr = { (int)(bx + bw + 8), (int)y0 + 33, (int)x1 - 8, (int)y0 + 49 }; put(&c, t, tr, g_small, COL_TEXT, DT_SINGLELINE); }
                if (!enemy) {
                    int mp = g_ro.mp[who], mm = g_ro.mpmax[who];
                    bar(&c, bx, y0 + 52, bw, 8, mp, mm, RGB(104, 160, 240));
                    char t[40]; if (mm > 0) snprintf(t, sizeof t, "MP %d/%d", mp, mm); else snprintf(t, sizeof t, "MP %d", mp);
                    RECT tr = { (int)(bx + bw + 8), (int)y0 + 47, (int)x1 - 8, (int)y0 + 63 }; put(&c, t, tr, g_small, COL_GRAY, DT_SINGLELINE);
                }
            }
            for (int b = 0; b < g_nbb; b++) {
                const Ent* e = &g_e[g_bb[b].ent]; RECT r = g_bb[b].r;
                if (r.bottom + oy < 0 || r.top + oy > cr.bottom) continue;
                int on = ent_on(e), hot = b == g_bp_hot, flash = b == g_bp_flash;
                COLORREF fill = on || flash ? COL_ACCENT : hot ? RGB(92, 94, 104) : RGB(64, 66, 74), ink = on || flash ? RGB(32, 28, 16) : COL_TEXT;
                cv_box(&c, (float)r.left, (float)(r.top + oy), (float)r.right, (float)(r.bottom + oy), 16, fill, 0);
                RECT gr = { r.left + 2, r.top + oy, r.left + 30, r.bottom + oy };
                cv_text(&c, glyph_of(e), gr, g_sym, on || flash ? ink : COL_ACCENT, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
                RECT tr = { r.left + 30, r.top + oy, r.right - 6, r.bottom + oy };
                put(&c, e->name, tr, g_font, ink, DT_VCENTER | DT_SINGLELINE);
            }
        }
        cv_end(&c, dc, 0, 0);
    }
    EndPaint(h, &ps);
}

static int bp_hit(int x, int y) {
    POINT p = { x, y + g_bp_scroll };
    for (int b = 0; b < g_nbb; b++) if (PtInRect(&g_bb[b].r, p)) return b;
    return -1;
}
static void bp_note(int hit) {
    if (hit < 0) { SetWindowTextW(g_note, L"Click a button to use it. Gold buttons are switches that stay on."); return; }
    const Ent* e = &g_e[g_bb[hit].ent];
    char t[300]; snprintf(t, sizeof t, "%s%s%s", e->name, e->note[0] ? ": " : "", e->note);
    wchar_t* w = wide(t); SetWindowTextW(g_note, w); free(w);
}
static void bp_click(HWND h, int hit) {
    int idx = g_bb[hit].ent; Ent* e = &g_e[idx];
    if (!strcmp(e->mode, "once")) { send_run(idx); g_bp_flash = hit; SetTimer(h, 1, 220, NULL); }
    else apply(idx, !ent_on(e));
    InvalidateRect(h, NULL, FALSE);
}
static LRESULT CALLBACK bpproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: bp_paint(h); return 0;
    case WM_MOUSEMOVE: {
        int hit = bp_hit((short)LOWORD(lp), (short)HIWORD(lp));
        if (hit != g_bp_hot) { g_bp_hot = hit; bp_note(hit); InvalidateRect(h, NULL, FALSE); }
        TRACKMOUSEEVENT tme = { sizeof tme, TME_LEAVE, h, 0 }; TrackMouseEvent(&tme);
        return 0;
    }
    case WM_MOUSELEAVE: if (g_bp_hot >= 0) { g_bp_hot = -1; bp_note(-1); InvalidateRect(h, NULL, FALSE); } return 0;
    case WM_LBUTTONDOWN: { int hit = bp_hit((short)LOWORD(lp), (short)HIWORD(lp)); if (hit >= 0) bp_click(h, hit); return 0; }
    case WM_MOUSEWHEEL: g_bp_scroll -= (short)HIWORD(wp) / 2; InvalidateRect(h, NULL, FALSE); return 0;
    case WM_SIZE: InvalidateRect(h, NULL, FALSE); return 0;
    case WM_TIMER: KillTimer(h, wp); g_bp_flash = -1; InvalidateRect(h, NULL, FALSE); return 0;
    }
    return DefWindowProcW(h, m, wp, lp);
}

static void bp_refresh(void) {
    SetWindowTextW(g_title, L"Battle cheats");
    char b[100];
    int np = g_ro.party[0] + g_ro.party[1] + g_ro.party[2] + g_ro.party[3], ne = g_ro.enemy[0] + g_ro.enemy[1] + g_ro.enemy[2] + g_ro.enemy[3] + g_ro.enemy[4] + g_ro.enemy[5];
    if (g_ro.inbattle) snprintf(b, sizeof b, "In a battle: %d in your party, %d enem%s", np, ne, ne == 1 ? "y" : "ies"); else snprintf(b, sizeof b, "Not in a battle");
    wchar_t* w = wide(b); SetWindowTextW(g_count, w); free(w);
    if (g_bp) InvalidateRect(g_bp, NULL, FALSE);
}

/* every half second: has who is there changed (a member joined, a battle began, an enemy fell)? Then the page is built again, where it was */
#define IDT_ROSTER 77
static void roster_tick(void) {
    if (!IsWindowVisible(g_win)) return;
    ModRoster r; mod_roster(&r);
    if (!memcmp(&r, &g_ro, sizeof r)) return;
    int hp_only = r.inbattle == g_ro.inbattle && !memcmp(r.party, g_ro.party, 4) && !memcmp(r.enemy, g_ro.enemy, 6) && !memcmp(r.name, g_ro.name, sizeof r.name);
    g_ro = r;
    if (g_mode == 2) { bp_refresh(); return; }
    if (getenv("DQIX_CHEATWIN_TEST")) fprintf(stderr, "cheatwin roster: battle=%d party=%d%d%d%d enemies=%d%d%d%d%d%d\n", r.inbattle, r.party[0], r.party[1], r.party[2], r.party[3],
                                              r.enemy[0], r.enemy[1], r.enemy[2], r.enemy[3], r.enemy[4], r.enemy[5]);
    if (hp_only && g_mode != 2) return;                        /* only an enemy's HP moved: it matters just for the titles of the battle window */
    g_keep_scroll = g_scroll; g_cur_page = -1; build_page();
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_TIMER:
        if (wp == IDT_ROSTER) { roster_tick(); return 0; }
        KillTimer(h, wp); if (wp == IDT_SEARCH) build_page(); else test_step((int)wp); return 0;
    case WM_PAINT: {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); Cv c;              /* the search box: a pill */
        if (cv_begin(&c, SIDE_W, SEARCH_H, g_mode == 2 ? COL_BG : COL_SIDE)) {
            int focus = GetFocus() == g_search;
            if (!g_mode) {                                              /* the Nuzlocke window has no search */
                cv_box(&c, 10.5f, 7.5f, SIDE_W - 10.5f, 37.5f, 15, focus ? COL_ACCENT : COL_LINE, 0);
                cv_box(&c, 11.5f, 8.5f, SIDE_W - 11.5f, 36.5f, 14, COL_BOX, 0);
            }
            cv_end(&c, dc, 0, 0);
        }
        EndPaint(h, &ps); return 0;
    }
    case WM_CTLCOLOREDIT: { HDC dc = (HDC)wp; SetBkColor(dc, COL_BOX); SetTextColor(dc, COL_TEXT); return (LRESULT)g_box; }
    case WM_SIZE: if (g_side) layout(LOWORD(lp), HIWORD(lp)); return 0;
    case WM_GETMINMAXINFO: { MINMAXINFO* mm = (MINMAXINFO*)lp; mm->ptMinTrackSize.x = 560; mm->ptMinTrackSize.y = 380; return 0; }
    case WM_SHOW_CHEATS: EnterCriticalSection(&g_cs); load_state(); LeaveCriticalSection(&g_cs); apply_mode(); build_page(); ShowWindow(h, IsIconic(h) ? SW_RESTORE : SW_SHOWNORMAL); SetForegroundWindow(h); return 0;
    case WM_CLOSE: card_hide(); ShowWindow(h, SW_HIDE); return 0;      /* hidden, not destroyed: the game goes on */
    case WM_ACTIVATE: if (LOWORD(wp) == WA_INACTIVE) card_hide(); break;
    case WM_CTLCOLORSTATIC: {
        HDC dc = (HDC)wp; HWND c = (HWND)lp; int id = GetDlgCtrlID(c);
        SetBkColor(dc, COL_BG); SetTextColor(dc, id == IDC_TITLE ? COL_TEXT : COL_GRAY);
        return (LRESULT)g_white;
    }
    case WM_CTLCOLORLISTBOX: if ((HWND)lp == g_side) return (LRESULT)g_gray; break;
    case WM_MEASUREITEM: { MEASUREITEMSTRUCT* mi = (MEASUREITEMSTRUCT*)lp; if (mi->CtlID == IDC_SIDE) { mi->itemHeight = 32; return TRUE; } break; }
    case WM_DRAWITEM:
        if (wp == IDC_SIDE) { draw_side((DRAWITEMSTRUCT*)lp); return TRUE; }
        if (wp == IDC_CLOSE || wp == IDC_SHARE || wp == IDC_IMPORT) { draw_pill_button((DRAWITEMSTRUCT*)lp); return TRUE; }
        break;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_SIDE: if (HIWORD(wp) == LBN_SELCHANGE) { if (GetWindowTextLengthW(g_search)) { SetWindowTextW(g_search, L""); KillTimer(h, IDT_SEARCH); } build_page(); } return 0;
        case IDC_SEARCH:
            if (HIWORD(wp) == EN_CHANGE) SetTimer(h, IDT_SEARCH, 120, NULL);
            if (HIWORD(wp) == EN_SETFOCUS || HIWORD(wp) == EN_KILLFOCUS) { RECT t = { 0, 0, SIDE_W, SEARCH_H }; InvalidateRect(h, &t, FALSE); }
            return 0;
        case IDC_CLOSE: case IDCANCEL: ShowWindow(h, SW_HIDE); return 0;
        case IDC_SHARE: share_settings(); return 0;
        case IDC_IMPORT: import_settings(); return 0;
        }
        break;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* Test hook: DQIX_CHEATWIN_TEST=<entry id>[,<picture.bmp>] opens the window by itself, switches that cheat on the way a click does
 * (the page, then the row's check box) and draws the window into the picture. Used by tests/test_cheatwin.py. */
static void save_shot(HWND h, const char* path) {
    RECT r; GetWindowRect(h, &r);
    if (g_card && IsWindowVisible(g_card)) {                 /* the hover card is up: the screen itself, window and card */
        RECT c; GetWindowRect(g_card, &c); UnionRect(&r, &r, &c);
    }
    int w = r.right - r.left, ht = r.bottom - r.top;
    HDC dc = GetDC(NULL), mem = CreateCompatibleDC(dc);
    HBITMAP bmp = CreateCompatibleBitmap(dc, w, ht); HGDIOBJ old = SelectObject(mem, bmp);
    if (g_card && IsWindowVisible(g_card)) BitBlt(mem, 0, 0, w, ht, dc, r.left, r.top, SRCCOPY);
    else PrintWindow(h, mem, 2);
    BITMAPINFOHEADER bi; memset(&bi, 0, sizeof bi); bi.biSize = sizeof bi; bi.biWidth = w; bi.biHeight = ht; bi.biPlanes = 1; bi.biBitCount = 24;
    int stride = (w * 3 + 3) & ~3; unsigned char* px = (unsigned char*)malloc((size_t)stride * (size_t)ht);
    if (px && GetDIBits(mem, bmp, 0, (UINT)ht, px, (BITMAPINFO*)&bi, DIB_RGB_COLORS)) {
        FILE* f = fopen(path, "wb");
        if (f) {
            BITMAPFILEHEADER fh; memset(&fh, 0, sizeof fh); fh.bfType = 0x4D42; fh.bfOffBits = sizeof fh + sizeof bi; fh.bfSize = fh.bfOffBits + (DWORD)(stride * ht);
            fwrite(&fh, sizeof fh, 1, f); fwrite(&bi, sizeof bi, 1, f); fwrite(px, 1, (size_t)stride * (size_t)ht, f); fclose(f);
        }
    }
    free(px); SelectObject(mem, old); DeleteObject(bmp); DeleteDC(mem); ReleaseDC(NULL, dc);
}

/* the sidebar of the current face: Enabled and every page but Nuzlocke, or just the Nuzlocke page */
static void apply_mode(void) {
    SetWindowTextW(g_win, g_mode == 1 ? L"Nuzlocke" : g_mode == 2 ? L"Battle cheats" : L"Cheats");
    SendMessageW(g_search, 0x1501 /*EM_SETCUEBANNER*/, TRUE, (LPARAM)L"Search cheats");
    ShowWindow(g_search, g_mode ? SW_HIDE : SW_SHOW);
    SetWindowTextW(g_note, g_mode == 2 ? L"Click a button to use it. Gold buttons are switches that stay on." : L"Switches work at once while you play. Save your game first.");
    SetWindowTextW(g_search, L"");
    ShowWindow(g_side, g_mode == 2 ? SW_HIDE : SW_SHOW); ShowWindow(g_host, g_mode == 2 ? SW_HIDE : SW_SHOW);
    ShowWindow(g_share, g_mode == 2 ? SW_HIDE : SW_SHOW); ShowWindow(g_import, g_mode == 2 ? SW_HIDE : SW_SHOW);
    if (g_bp) ShowWindow(g_bp, g_mode == 2 ? SW_SHOW : SW_HIDE);
    { RECT lr; GetClientRect(g_win, &lr); layout(lr.right, lr.bottom); }
    SendMessageW(g_side, LB_RESETCONTENT, 0, 0);
    if (!g_mode) { int at0 = (int)SendMessageW(g_side, LB_ADDSTRING, 0, (LPARAM)L"Enabled"); SendMessageW(g_side, LB_SETITEMDATA, (WPARAM)at0, g_on_page); }
    for (int i = 0; i < g_npg; i++) {
        { int nz = !strcmp(g_pg[i], "Nuzlocke"), lb = !strcmp(g_pg[i], "Live battle");
          if (g_mode == 0 ? (nz || lb) : g_mode == 1 ? !nz : !lb) continue; }
        int has = 0; for (int k = 0; k < g_ne && !has; k++) has = strcmp(g_e[k].kind, "blocked") && (!strcmp(g_e[k].cat, g_pg[i]) || !strcmp(g_e[k].also, g_pg[i]));
        if (!has) continue;
        wchar_t* w = wide(g_pg[i]); int at = (int)SendMessageW(g_side, LB_ADDSTRING, 0, (LPARAM)w); SendMessageW(g_side, LB_SETITEMDATA, (WPARAM)at, i); free(w);
    }
    SendMessageW(g_side, LB_SETCURSEL, g_mode ? 0 : 1, 0);
    g_cur_page = -1;
    InvalidateRect(g_win, NULL, TRUE);
}

static void select_page_of(int idx) {
    for (int t = 0; t < (int)SendMessageW(g_side, LB_GETCOUNT, 0, 0); t++) {
        int p = (int)SendMessageW(g_side, LB_GETITEMDATA, (WPARAM)t, 0);
        if (p != g_on_page && !strcmp(g_e[idx].cat, g_pg[p])) {
            int s = sec_of(g_pg[p], &g_e[idx]);                  /* its section folded open (not saved) */
            if (s >= 0 && !sec_open(s)) { char k[300]; sec_key(s, k, sizeof k); st_set("open", k, 1); }
            SendMessageW(g_side, LB_SETCURSEL, (WPARAM)t, 0); build_page(); return;
        }
    }
}

/* the search test: types each search (separated by ';'), builds the page and checks it: every row and every drop-down
 * entry fits the words, at most SEARCH_MAX rows; one log line each, the last one stays on screen for the picture */
static void test_search(void) {
    char all[400]; snprintf(all, sizeof all, "%s", g_test_search);
    char* save = NULL;
    for (char* q = strtok_s(all, ";", &save); q; q = strtok_s(NULL, ";", &save)) {
        wchar_t* w = wide(q); SetWindowTextW(g_search, w); free(w);
        KillTimer(g_win, IDT_SEARCH);
        LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
        g_last_q[0] = 0; build_page();
        QueryPerformanceCounter(&b);
        int bad = 0, members = 0;
        for (int i = 0; i < g_nrows; i++) {
            Row* r = &g_rows[i];
            if (r->kind == R_GROUP) { int title = words_in(g_g[r->gi].lt, NULL); for (int k = 0; k < r->nm; k++) { members++; if (!title && !match_words(&g_e[r->members[k]])) bad++; } }
            else if (r->idx >= 0 && !match_words(&g_e[r->idx])) bad++;
        }
        fprintf(stderr, "cheatwin search: q=%s rows=%d found=%d members=%d bad=%d ms=%.1f\n", q, g_nrows, g_found, members, bad,
                (double)(b.QuadPart - a.QuadPart) * 1000.0 / (double)f.QuadPart);
    }
}

static void test_step(int step) {
    if (step == 1 && g_test_import[0]) {                    /* Import without the question, then what Share would copy */
        if (strcmp(g_test_import, "-")) {
            int* want = (int*)calloc((size_t)g_ne + 1, sizeof *want); int missing = 0;
            int found = want ? read_shared(g_test_import, want, &missing) : -1;
            if (found > 0) apply_wanted(want);
            free(want);
            fprintf(stderr, "cheatwin import: found=%d missing=%d\n", found, missing);
        }
        int count; char* line = share_line(&count);
        fprintf(stderr, "cheatwin share: count=%d %s\n", count, line ? line : "");
        free(line);
        return;
    }
    if (step == 1 && g_test_search[0]) test_search();
    else if (step == 1) {
        int now = !strncmp(g_test_id, "now:", 4);              /* "now:<id>": press its Do it now button instead of switching it on */
        const char* id = g_test_id + (now ? 4 : 0);
        int idx = -1; for (int i = 0; i < g_ne; i++) if (!strcmp(g_e[i].id, id)) idx = i;
        if (idx < 0) { fprintf(stderr, "cheatwin test: no entry %s\n", id); return; }
        if (g_mode == 2) {                                      /* the battle window has cards, not rows */
            if (now) { send_run(idx); fprintf(stderr, "cheatwin test: did it now %s\n", id); } else { apply(idx, 1); fprintf(stderr, "cheatwin test: switched on %s\n", id); }
            InvalidateRect(g_bp, NULL, FALSE); return;
        }
        select_page_of(idx);
        if (locked(&g_e[idx])) { fprintf(stderr, "cheatwin test: locked %s\n", id); return; }
        for (int i = 0; i < g_nrows && now; i++) {
            Row* r = &g_rows[i];
            if ((r->kind == R_CHECK || r->kind == R_ONCE) && r->idx == idx) {
                if (!r->btn) { fprintf(stderr, "cheatwin test: no Do it now button for %s\n", id); return; }
                SendMessageW(r->btn, BM_CLICK, 0, 0);
                fprintf(stderr, "cheatwin test: did it now %s\n", id);
                return;
            }
        }
        if (now) { fprintf(stderr, "cheatwin test: no row for %s\n", id); return; }
        for (int i = 0; i < g_nrows; i++) {
            Row* r = &g_rows[i]; int k = -1;
            if (r->kind == R_CHECK && r->idx == idx) { r->on = 1; InvalidateRect(r->main, NULL, FALSE); entry_changed(r, idx, 1); k = 0; }
            else if (r->kind == R_ONCE && r->idx == idx && r->btn && !strcmp(g_e[idx].mode, "toggle")) { SendMessageW(r->btn, BM_CLICK, 0, 0); k = 0; }
            else if (r->kind == R_GROUP) { for (int q = 0; q < r->nm; q++) if (r->members[q] == idx) { SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)(q + 1), 0); group_changed(r, q + 1); k = 0; } }
            if (k == 0) { fprintf(stderr, "cheatwin test: switched on %s\n", g_test_id); break; }
        }
    } else if (step == 2 && g_test_shot[0]) {
        const char* sc = getenv("DQIX_CHEATWIN_SCROLL");          /* tests: scroll in steps first (the controls must follow) */
        if (getenv("DQIX_CHEATWIN_CARD")) {                     /* tests: the hover card of the last row with one, at the window's bottom right */
            RECT cr; GetClientRect(g_host, &cr); POINT pt = { cr.right - 20, cr.bottom - 20 }; ClientToScreen(g_host, &pt);
            for (int i = g_nrows - 1; i >= 0; i--) {
                const char* ab = g_rows[i].kind == R_GROUP ? g_g[g_rows[i].gi].about : g_rows[i].idx >= 0 ? g_e[g_rows[i].idx].about : "";
                if (ab && ab[0] && g_rows[i].y - g_scroll < cr.bottom) { card_show_at(i, pt); UpdateWindow(g_card); Sleep(400); break; }
            }
        }
        if (sc && *sc) { int to = atoi(sc); for (int k = 1; k <= 8; k++) scroll_to(to * k / 8);
                         RECT cr; GetClientRect(g_host, &cr); fprintf(stderr, "cheatwin test: scrolled %d of %d (page %d)\n", g_scroll, g_total, (int)cr.bottom); }
        save_shot(g_win, g_test_shot); fprintf(stderr, "cheatwin test: picture written\n");
    }
}

/* look of the system's current controls (rounded check boxes, flat drop-downs): comctl32 version 6 through an activation context made
 * from a manifest in the temp folder (the game's exe has none) */
static void enable_styles(void) {
    static const char xml[] =
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n"
        "<assembly xmlns=\"urn:schemas-microsoft-com:asm.v1\" manifestVersion=\"1.0\"><dependency><dependentAssembly>"
        "<assemblyIdentity type=\"win32\" name=\"Microsoft.Windows.Common-Controls\" version=\"6.0.0.0\" processorArchitecture=\"*\" publicKeyToken=\"6595b64144ccf1df\" language=\"*\"/>"
        "</dependentAssembly></dependency></assembly>\r\n";
    wchar_t dir[MAX_PATH], path[MAX_PATH + 40];
    if (!GetTempPathW(MAX_PATH, dir)) return;
    _snwprintf(path, MAX_PATH + 40, L"%sdqix-cheatwin-%lu.manifest", dir, GetCurrentProcessId());
    FILE* f = _wfopen(path, L"wb"); if (!f) return;
    fwrite(xml, 1, sizeof xml - 1, f); fclose(f);
    ACTCTXW ac; memset(&ac, 0, sizeof ac); ac.cbSize = sizeof ac; ac.lpSource = path;
    HANDLE h = CreateActCtxW(&ac); DeleteFileW(path);
    ULONG_PTR cookie; if (h != INVALID_HANDLE_VALUE) ActivateActCtx(h, &cookie);   /* kept active for this thread's lifetime */
}

static void dark(HWND h, const wchar_t* theme) {                 /* the system's dark look for a control (Windows 10 1809 and later; else it stays as it is) */
    static HMODULE ux; typedef HRESULT (WINAPI* Fn)(HWND, LPCWSTR, LPCWSTR); static Fn f;
    if (!ux) { ux = LoadLibraryW(L"uxtheme.dll"); if (ux) f = (Fn)GetProcAddress(ux, "SetWindowTheme"); }
    if (f && h) f(h, theme, NULL);
}

static void dark_title(HWND h) {
    HMODULE dm = LoadLibraryW(L"dwmapi.dll"); if (!dm) return;
    typedef HRESULT (WINAPI* Fn)(HWND, DWORD, LPCVOID, DWORD); Fn f = (Fn)GetProcAddress(dm, "DwmSetWindowAttribute");
    BOOL on = TRUE; if (f) f(h, 20, &on, sizeof on);
}

static HFONT mkfont(const wchar_t* face, int px, int weight) {
    return CreateFontW(-px, 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, face);
}

/* JetBrains Mono for the window: the one installed on the PC, else the copy in mods/system/fonts (loaded for this program
 * only); without either, Segoe UI. GDI names the semi-bold cut a family of its own ("JetBrains Mono SemiBold"). */
static int font_is(HFONT f, const wchar_t* face) {
    HDC dc = GetDC(NULL); HGDIOBJ o = SelectObject(dc, f); wchar_t got[64] = L""; GetTextFaceW(dc, 64, got); SelectObject(dc, o); ReleaseDC(NULL, dc);
    return !_wcsicmp(got, face);
}
static void load_fonts(void) {
    static const char* files[] = { "JetBrainsMono-Regular.ttf", "JetBrainsMono-SemiBold.ttf", "JetBrainsMono-Bold.ttf" };
    for (int i = 0; i < 3; i++) {
        char p[MAX_PATH * 2 + 64]; snprintf(p, sizeof p, "%s\\mods\\system\\fonts\\%s", g_root, files[i]);
        AddFontResourceExA(p, FR_PRIVATE, NULL);
    }
}
static HFONT ui_font(int px, int weight) {
    HFONT f;
    if (weight >= FW_SEMIBOLD) {
        f = mkfont(L"JetBrains Mono SemiBold", px, FW_NORMAL); if (font_is(f, L"JetBrains Mono SemiBold")) return f; DeleteObject(f);
        f = mkfont(L"JetBrains Mono", px, FW_BOLD);
    } else f = mkfont(L"JetBrains Mono", px, weight);
    if (font_is(f, L"JetBrains Mono")) return f;
    DeleteObject(f);
    return mkfont(L"Segoe UI", px + 1, weight);
}

static DWORD WINAPI ui_thread(LPVOID unused) {
    (void)unused;
    enable_styles();
    HMODULE cc = LoadLibraryW(L"comctl32.dll");
    if (cc) {
        typedef BOOL (WINAPI* Fn)(const INITCOMMONCONTROLSEX*);
        Fn f = (Fn)GetProcAddress(cc, "InitCommonControlsEx");
        INITCOMMONCONTROLSEX ic = { sizeof ic, ICC_STANDARD_CLASSES | ICC_TAB_CLASSES };
        if (f) f(&ic);
    }
    load_fonts();
    g_font = ui_font(12, FW_NORMAL); g_small = ui_font(11, FW_NORMAL); g_bold = ui_font(12, FW_SEMIBOLD);
    g_head = ui_font(18, FW_SEMIBOLD); g_mono = ui_font(11, FW_SEMIBOLD);
    g_sym = CreateFontW(-16, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI Symbol");
    g_box = CreateSolidBrush(COL_BOX); g_white = CreateSolidBrush(COL_BG); g_gray = CreateSolidBrush(COL_SIDE);
    HINSTANCE hi = GetModuleHandleW(NULL);
    WNDCLASSW wc; memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = wndproc; wc.hInstance = hi; wc.lpszClassName = L"DqixCheatWindow";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW); wc.hbrBackground = g_white;
    /* the game's own icon (resource 1 of dqix.exe, build/icon/dqix.rc); a build without it keeps the default */
    HICON ico_big = (HICON)LoadImageW(hi, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXICON), GetSystemMetrics(SM_CYICON), 0);
    HICON ico_small = (HICON)LoadImageW(hi, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), 0);
    wc.hIcon = ico_big;
    RegisterClassW(&wc);
    wc.hIcon = NULL;
    wc.lpfnWndProc = hostproc; wc.lpszClassName = L"DqixCheatPage"; RegisterClassW(&wc);
    wc.lpfnWndProc = bpproc; wc.lpszClassName = L"DqixBattlePanel"; RegisterClassW(&wc);
    g_win = CreateWindowExW(0, L"DqixCheatWindow", L"Cheats", WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT, CW_USEDEFAULT, 800, 560, NULL, NULL, hi, NULL);
    if (ico_big) SendMessageW(g_win, WM_SETICON, ICON_BIG, (LPARAM)ico_big);
    if (ico_small) SendMessageW(g_win, WM_SETICON, ICON_SMALL, (LPARAM)ico_small);
    g_side = CreateWindowExW(0, L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP | LBS_NOTIFY | LBS_OWNERDRAWFIXED | LBS_HASSTRINGS | LBS_NOINTEGRALHEIGHT, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_SIDE, hi, NULL);
    g_search = CreateWindowExW(0, L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_SEARCH, hi, NULL);
    SendMessageW(g_search, WM_SETFONT, (WPARAM)g_font, TRUE); SendMessageW(g_search, 0x1501 /*EM_SETCUEBANNER*/, TRUE, (LPARAM)L"Search cheats"); SendMessageW(g_search, EM_LIMITTEXT, 100, 0);
    g_title = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_NOPREFIX | SS_ENDELLIPSIS, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_TITLE, hi, NULL);
    g_count = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_NOPREFIX, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_COUNT, hi, NULL);
    g_host = CreateWindowExW(WS_EX_CONTROLPARENT, L"DqixCheatPage", L"", WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN, 0, 0, 10, 10, g_win, NULL, hi, NULL);
    g_bp = CreateWindowExW(0, L"DqixBattlePanel", L"", WS_CHILD, 0, 0, 10, 10, g_win, NULL, hi, NULL);
    g_note = CreateWindowExW(0, L"STATIC", L"Switches work at once while you play. Save your game first.", WS_CHILD | WS_VISIBLE | SS_NOPREFIX | SS_ENDELLIPSIS, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_NOTE, hi, NULL);
    g_close = CreateWindowExW(0, L"BUTTON", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_CLOSE, hi, NULL);
    g_share = CreateWindowExW(0, L"BUTTON", L"Share", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_SHARE, hi, NULL);
    g_import = CreateWindowExW(0, L"BUTTON", L"Import", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_IMPORT, hi, NULL);
    hook(g_close); hook(g_share); hook(g_import);
    SendMessageW(g_share, WM_SETFONT, (WPARAM)g_font, TRUE); SendMessageW(g_import, WM_SETFONT, (WPARAM)g_font, TRUE);
    SendMessageW(g_title, WM_SETFONT, (WPARAM)g_head, TRUE); SendMessageW(g_count, WM_SETFONT, (WPARAM)g_small, TRUE); SendMessageW(g_note, WM_SETFONT, (WPARAM)g_small, TRUE);
    SendMessageW(g_close, WM_SETFONT, (WPARAM)g_font, TRUE); SendMessageW(g_side, WM_SETFONT, (WPARAM)g_font, TRUE);
    SendMessageW(g_side, LB_SETITEMHEIGHT, 0, 32);
    wc.lpfnWndProc = cardproc; wc.lpszClassName = L"DqixCheatCard"; wc.hbrBackground = NULL; wc.style = CS_DROPSHADOW; RegisterClassW(&wc);
    g_card = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE, L"DqixCheatCard", L"", WS_POPUP, 0, 0, 10, 10, g_win, NULL, hi, NULL);
    if (g_card) {                                                      /* Windows 11: round corners */
        HMODULE dm = LoadLibraryW(L"dwmapi.dll"); typedef HRESULT (WINAPI* Fn)(HWND, DWORD, LPCVOID, DWORD);
        Fn f = dm ? (Fn)(void*)GetProcAddress(dm, "DwmSetWindowAttribute") : NULL; DWORD round = 3 /*DWMWCP_ROUNDSMALL*/;
        if (f) f(g_card, 33 /*DWMWA_WINDOW_CORNER_PREFERENCE*/, &round, sizeof round);
    }
    dark_title(g_win); dark(g_host, L"DarkMode_Explorer");
    g_on_page = g_npg; g_search_page = g_npg + 1;                                            /* the Enabled entry: a page number past the real ones */
    apply_mode();
    SetTimer(g_win, IDT_ROSTER, 300, NULL);
    RECT r; GetClientRect(g_win, &r); layout(r.right, r.bottom);
    build_page();
    ShowWindow(g_win, SW_SHOWNORMAL); SetForegroundWindow(g_win);
    if (g_test_id[0] || g_test_search[0] || g_test_import[0]) { SetTimer(g_win, 1, 1500, NULL); SetTimer(g_win, 2, 4000, NULL); }
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (msg.message == WM_MOUSEMOVE && msg.hwnd && (msg.hwnd == g_host || IsChild(g_host, msg.hwnd))) card_mouse(msg.pt);
        else if (msg.message == WM_LBUTTONDOWN || msg.message == WM_RBUTTONDOWN || msg.message == WM_KEYDOWN) card_hide();
        if (msg.message == WM_MOUSEWHEEL) {                      /* the wheel scrolls the page, whatever has the focus (a drop-down must not change by it) */
            POINT pt = { (short)LOWORD(msg.lParam), (short)HIWORD(msg.lParam) }; HWND under = WindowFromPoint(pt);
            if (under == g_bp) { SendMessageW(g_bp, WM_MOUSEWHEEL, msg.wParam, msg.lParam); continue; }
            if (under == g_host || (under && IsChild(g_host, under))) { SendMessageW(g_host, WM_MOUSEWHEEL, msg.wParam, msg.lParam); continue; }
        }
        if (!IsDialogMessageW(g_win, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    return 0;
}

static void open_mode(int mode) {
    g_mode = mode;
    mod_roster(&g_ro);
    if (!g_cs_init) { InitializeCriticalSection(&g_cs); g_cs_init = 1; }
    if (!g_loaded) { load_catalog(); if (g_loaded) { load_state(); migrate_state(); } }
    if (!g_loaded) {
        MessageBoxW(NULL, L"There is no cheat list yet. Run \"mods\\Apply.bat\" once (it makes the list), then try again.", L"Cheats", MB_OK | MB_ICONINFORMATION);
        return;
    }
    static HANDLE th;
    if (!th) { th = CreateThread(NULL, 0, ui_thread, NULL, 0, NULL); return; }
    if (g_win) PostMessageW(g_win, WM_SHOW_CHEATS, 0, 0);
}
void mod_cheatwin_show(void) { open_mode(0); }          /* menu bar: Cheats > Cheats... */
void mod_nuzlocke_show(void) { open_mode(1); }          /* menu bar: Nuzlocke > Settings... */
void mod_battle_show(void) { open_mode(2); }            /* menu bar: Cheats > Battle cheats... */
#else
void mod_cheatwin_boot(void) {}
void mod_cheatwin_show(void) {}
void mod_nuzlocke_show(void) {}
void mod_battle_show(void) {}
#endif
