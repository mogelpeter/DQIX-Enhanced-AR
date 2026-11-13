/* DQIX Enhanced mods: the Cheats window inside the emulator (menu bar: Cheats > Cheats...).
 *
 * It shows the same list as the cheat menu program (mods\system\bin\catalog.txt, made by tools\catalog.py), keeps the same
 * state file (mods\system\menu-state.txt) and puts live cheats into the game through the same mailbox, but from inside
 * the game's own process, so there is no second program, no restart and, with the live code mods (livepatch.c),
 * no rebuild: a switch is on the moment you click it.
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

int mod_cheats_post(const uint16_t* w, int n);       /* mod_cheats.c: words into the mailbox's ring; 0 = full or no mailbox */
uint32_t mod_cheats_gen(void);                       /* goes up whenever the game forgot every cheat */

typedef struct { char *id, *cat, *group, *kind, *status, *name, *option, *note, *mode, *keys, *env, *also, *file; int on, nops; uint32_t* ops; } Ent;
typedef struct { char *id, *cat, *title, *kind; } Grp;

static Ent* g_e; static int g_ne;
static Grp* g_g; static int g_ng;
static char** g_pg; static int g_npg;
static char** g_st; static int g_nst;                /* the state file: lines "<kind> <id>" (live, code, launch, flag) */
static char g_root[MAX_PATH * 2], g_statepath[MAX_PATH * 2];
static CRITICAL_SECTION g_cs;
static int g_cs_init, g_loaded;

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
        } else if (nt >= 1 && !strcmp(tok[0], "group")) {
            if (g_ng == cap_g) { cap_g = cap_g ? cap_g * 2 : 32; g_g = (Grp*)realloc(g_g, (size_t)cap_g * sizeof *g_g); }
            Grp* g = &g_g[g_ng++];
            g->id = kv(tok + 1, nt - 1, "id"); g->cat = kv(tok + 1, nt - 1, "cat"); g->title = kv(tok + 1, nt - 1, "title"); g->kind = kv(tok + 1, nt - 1, "kind");
        } else if (nt >= 1 && !strcmp(tok[0], "entry")) {
            if (g_ne == cap_e) { cap_e = cap_e ? cap_e * 2 : 256; g_e = (Ent*)realloc(g_e, (size_t)cap_e * sizeof *g_e); }
            Ent* e = &g_e[g_ne++]; memset(e, 0, sizeof *e);
            char** t = tok + 1; int n = nt - 1;
            e->id = kv(t, n, "id"); e->cat = kv(t, n, "cat"); e->group = kv(t, n, "group"); e->kind = kv(t, n, "kind"); e->status = kv(t, n, "status");
            e->name = kv(t, n, "name"); e->option = kv(t, n, "option"); e->note = kv(t, n, "note"); e->mode = kv(t, n, "mode"); e->keys = kv(t, n, "keys");
            e->env = kv(t, n, "env"); e->also = kv(t, n, "also"); e->file = kv(t, n, "file");
            char* on = kv(t, n, "on"); e->on = on[0] == '1'; free(on);
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

static void st_save(void) {
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

/* entries a hand-written file turns on by itself ("# enabled: yes"): on the first time only */
static void seed_defaults(void) {
    int changed = 0;
    for (int i = 0; i < g_ne; i++) {
        Ent* e = &g_e[i];
        if (!e->on || strcmp(e->kind, "live") || strncmp(e->id, "file:code/", 10)) continue;
        char flag[200]; snprintf(flag, sizeof flag, "seeded-%s", e->id);
        if (st_has("flag", flag)) continue;
        st_set("flag", flag, 1); st_set("live", e->id, 1); changed = 1;
    }
    if (changed) st_save();
}

/* ---- sending cheats (the mailbox's messages, see mod_cheats.c) ---- */
static void post_words(const uint16_t* w, int n) {
    for (int tries = 0; tries < 400; tries++) { if (mod_cheats_post(w, n)) return; Sleep(10); }
}
static void send_set(int idx) {
    Ent* e = &g_e[idx]; int n = 1 + 4 * e->nops;
    if (n > 0xFFF || !e->nops) return;
    uint16_t* w = (uint16_t*)malloc((size_t)(n + 1) * 2); if (!w) return;
    w[0] = (uint16_t)(2 << 12 | n); w[1] = (uint16_t)(idx + 1);
    for (int i = 0; i < e->nops; i++) {
        uint32_t a = e->ops[i * 2], b = e->ops[i * 2 + 1];
        w[2 + i * 4] = (uint16_t)a; w[3 + i * 4] = (uint16_t)(a >> 16); w[4 + i * 4] = (uint16_t)b; w[5 + i * 4] = (uint16_t)(b >> 16);
    }
    post_words(w, n + 1); free(w);
}
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
static void send_clear(int idx) {
    uint16_t w[2] = { (uint16_t)(3 << 12 | 1), (uint16_t)(idx + 1) };
    post_words(w, 2);
}

/* every live cheat that is on, again (the game started, or forgot them) */
static void resend_all(void) {
    if (!g_cs_init) return;
    EnterCriticalSection(&g_cs);
    for (int i = 0; i < g_ne; i++)
        if (!strcmp(g_e[i].kind, "live") && strcmp(g_e[i].mode, "once") && ent_on(&g_e[i])) send_set(i);
    LeaveCriticalSection(&g_cs);
}

void mod_cheatwin_show(void);
static char g_test_id[200], g_test_shot[MAX_PATH];
static DWORD WINAPI agent(LPVOID unused) {
    (void)unused;
    uint32_t last = 0;
    const char* t = getenv("DQIX_CHEATWIN_TEST");
    if (t && *t) {
        const char* c = strchr(t, ',');
        snprintf(g_test_id, sizeof g_test_id, "%.*s", c ? (int)(c - t) : (int)strlen(t), t);
        if (c) snprintf(g_test_shot, sizeof g_test_shot, "%s", c + 1);
        Sleep(1500); mod_cheatwin_show();
    }
    for (;;) {
        Sleep(200);
        uint32_t g = mod_cheats_gen();
        if (g != last) { last = g; resend_all(); }
    }
    return 0;
}

/* a switch changed: state, game */
static void apply(int idx, int on) {
    Ent* e = &g_e[idx];
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

static void all_off(void) {
    EnterCriticalSection(&g_cs);
    for (int i = 0; i < g_ne; i++) if (ent_on(&g_e[i])) { st_set(skind(&g_e[i]), g_e[i].id, 0); if (!strcmp(g_e[i].kind, "live")) send_clear(i); }
    st_save();
    LeaveCriticalSection(&g_cs);
}

/* ---- program start ---- */
void mod_cheatwin_boot(void) {
    if (getenv("DQIX_CHEATWIN_OFF")) return;                /* tests: nothing is sent or set by itself */
    if (!g_cs_init) { InitializeCriticalSection(&g_cs); g_cs_init = 1; }
    load_catalog();
    if (!g_loaded) return;
    load_state();
    migrate_state(); seed_defaults();
    for (int i = 0; i < g_ne; i++)                           /* options for the next start: set before the game reads them */
        if (!strcmp(g_e[i].kind, "launch") && ent_on(&g_e[i]) && strchr(g_e[i].env, '=')) _putenv(g_e[i].env);
    CreateThread(NULL, 0, agent, NULL, 0, NULL);
}

/* ---------------------------------------------------------------- the window
 * Left: the pages (owner-drawn list), the last one is "Keybinds". Right: the page's rows in a scrolling panel. A row is a check box
 * (a cheat), a drop-down (a choice of which only one can be on: "Off" + the options), or a name with its keys (Keybinds page). */
enum { IDC_SIDE = 100, IDC_OFF, IDC_CLOSE, IDC_TITLE, IDC_COUNT, IDC_NOTE, IDC_ROW0 = 1000, WM_SHOW_CHEATS = WM_APP + 1 };
enum { R_CHECK, R_ONCE, R_GROUP, R_KEY };
typedef struct { int kind, idx, gi, y, h, nm, members[64]; HWND main, sub, right, combo, btn; } Row;

static HWND g_win, g_side, g_host, g_title, g_count, g_note, g_off, g_close;
static HFONT g_font, g_small, g_bold, g_head, g_mono;
static HBRUSH g_white, g_gray;
static Row* g_rows; static int g_nrows, g_scroll, g_total, g_keys_page, g_cur_page = -1;

#define PAD_X 24
#define SIDE_W 210
#define COL_TEXT RGB(32, 32, 32)
#define COL_GRAY RGB(112, 112, 112)
#define COL_ACCENT RGB(0, 103, 192)

static wchar_t* wide(const char* s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0); wchar_t* w = (wchar_t*)malloc((size_t)(n + 1) * sizeof *w);
    if (w) { MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n); w[n] = 0; }
    return w;
}

static const Grp* grp_of(const char* id) { for (int i = 0; i < g_ng; i++) if (!strcmp(g_g[i].id, id)) return &g_g[i]; return NULL; }
static const char* label(const Ent* e) { return e->option[0] ? e->option : e->name; }

/* the small grey line under a cheat: who needs it, status, note (the keys are on their own page) */
static void tag_text(const Ent* e, char* out, size_t n) {
    const char* who;
    if (!strcmp(e->kind, "live")) who = "One player is enough";
    else if (!strcmp(e->kind, "launch")) who = !strncmp(e->env, "DQIX_MOD_", 9) ? "All players, next start" : "Your PC only, next start";
    else who = "All players, needs a rebuild";
    snprintf(out, n, "%s%s%s%s%s", who, !strcmp(e->status, "untested") ? "  \xC2\xB7  untested" : "", !strcmp(e->mode, "once") ? "  \xC2\xB7  once" : "",
             e->note[0] ? "  \xC2\xB7  " : "", e->note);
}

static HWND mk(const wchar_t* cls, const char* text, DWORD style, HFONT f, int id) {
    wchar_t* w = wide(text);
    HWND h = CreateWindowExW(0, cls, w, WS_CHILD | WS_VISIBLE | style, 0, 0, 10, 10, g_host, (HMENU)(UINT_PTR)id, GetModuleHandleW(NULL), NULL);
    free(w); SendMessageW(h, WM_SETFONT, (WPARAM)f, TRUE); return h;
}

static void clear_rows(void) {
    for (int i = 0; i < g_nrows; i++) {
        HWND hs[5] = { g_rows[i].main, g_rows[i].sub, g_rows[i].right, g_rows[i].combo, g_rows[i].btn };
        for (int k = 0; k < 5; k++) if (hs[k]) DestroyWindow(hs[k]);
    }
    free(g_rows); g_rows = NULL; g_nrows = 0;
}

static Row* add_row(int kind, int idx, int gi) {
    g_rows = (Row*)realloc(g_rows, (size_t)(g_nrows + 1) * sizeof *g_rows);
    Row* r = &g_rows[g_nrows]; memset(r, 0, sizeof *r); r->kind = kind; r->idx = idx; r->gi = gi; g_nrows++; return r;
}

static void update_count(void) {
    int cheats = 0, on = 0;
    for (int i = 0; i < g_nrows; i++) {
        Row* r = &g_rows[i];
        if (r->kind == R_CHECK) { cheats++; on += ent_on(&g_e[r->idx]); }
        else if (r->kind == R_GROUP) { cheats++; for (int k = 0; k < r->nm; k++) if (ent_on(&g_e[r->members[k]])) { on++; break; } }
    }
    char b[80]; if (g_cur_page == g_keys_page) snprintf(b, sizeof b, "Hold these keys on the controller"); else snprintf(b, sizeof b, "%d of %d on", on, cheats);
    wchar_t* w = wide(b); SetWindowTextW(g_count, w); free(w);
}

static void lay_rows(void) {
    RECT cr; GetClientRect(g_host, &cr); int W = cr.right;
    HDC dc = GetDC(g_host); int y = 4;
    for (int i = 0; i < g_nrows; i++) {
        Row* r = &g_rows[i];
        int rightw = r->kind == R_GROUP ? 240 : r->kind == R_KEY ? (W - 2 * PAD_X) * 42 / 100 : r->btn ? 104 : 0;
        int gap = rightw ? 16 : 0, textw = W - 2 * PAD_X - rightw - gap, indent = (r->kind == R_CHECK || r->kind == R_ONCE) ? 24 : 0;
        int subh = 0, rh = 0;
        wchar_t buf[600];
        if (r->sub) {
            GetWindowTextW(r->sub, buf, 600); HGDIOBJ o = SelectObject(dc, g_small);
            RECT m = { 0, 0, textw - indent, 0 }; DrawTextW(dc, buf, -1, &m, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX); subh = m.bottom; SelectObject(dc, o);
        }
        if (r->kind == R_KEY && r->right) {
            GetWindowTextW(r->right, buf, 600); HGDIOBJ o = SelectObject(dc, g_mono);
            RECT m = { 0, 0, rightw, 0 }; DrawTextW(dc, buf, -1, &m, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX); rh = m.bottom; SelectObject(dc, o);
        }
        int h = 12 + 20 + (subh ? 3 + subh : 0) + 12; if (rh + 24 > h) h = rh + 24; if (h < 52 && r->kind != R_KEY) h = 52; if (h < 48) h = 48;
        r->y = y; r->h = h;
        int top = y - g_scroll;
        MoveWindow(r->main, PAD_X, top + 12, textw, 20, FALSE);
        if (r->sub) MoveWindow(r->sub, PAD_X + indent, top + 12 + 20 + 3, textw - indent, subh, FALSE);
        if (r->combo) MoveWindow(r->combo, W - PAD_X - rightw, top + (h - 28) / 2, rightw, 240, FALSE);
        if (r->btn) MoveWindow(r->btn, W - PAD_X - rightw, top + (h - 30) / 2, rightw, 30, FALSE);
        if (r->kind == R_KEY && r->right) MoveWindow(r->right, W - PAD_X - rightw, top + (h - rh) / 2, rightw, rh, FALSE);
        y += h;
    }
    ReleaseDC(g_host, dc);
    g_total = y + 8;
    SCROLLINFO si; memset(&si, 0, sizeof si); si.cbSize = sizeof si; si.fMask = SIF_RANGE | SIF_PAGE | SIF_POS; si.nMax = g_total; si.nPage = (UINT)cr.bottom; si.nPos = g_scroll;
    SetScrollInfo(g_host, SB_VERT, &si, TRUE);
    RedrawWindow(g_host, NULL, NULL, RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN);
}

static void scroll_to(int pos) {
    RECT cr; GetClientRect(g_host, &cr); int max = g_total - cr.bottom; if (max < 0) max = 0;
    if (pos > max) pos = max; if (pos < 0) pos = 0;
    if (pos == g_scroll) return;
    g_scroll = pos; lay_rows();
}

static void build_page(void) {
    int sel = (int)SendMessageW(g_side, LB_GETCURSEL, 0, 0); if (sel < 0) return;
    int p = (int)SendMessageW(g_side, LB_GETITEMDATA, (WPARAM)sel, 0);
    clear_rows(); g_scroll = 0; g_cur_page = p;
    SetWindowTextW(g_note, L"");
    wchar_t* tt = wide(p == g_keys_page ? "Keybinds" : g_pg[p]); SetWindowTextW(g_title, tt); free(tt);
    if (p == g_keys_page) {
        for (int i = 0; i < g_ne; i++) {
            Ent* e = &g_e[i]; if (!strcmp(e->kind, "blocked") || !e->keys[0]) continue;
            Row* r = add_row(R_KEY, i, -1); int id = IDC_ROW0 + g_nrows - 1;
            r->main = mk(L"STATIC", e->name, SS_NOPREFIX | SS_ENDELLIPSIS, g_font, id);
            char sub[300]; snprintf(sub, sizeof sub, "%s", e->cat); r->sub = mk(L"STATIC", sub, SS_NOPREFIX, g_small, id);
            SetWindowLongPtrW(r->sub, GWLP_USERDATA, 1);
            r->right = mk(L"STATIC", e->keys, SS_NOPREFIX | SS_RIGHT, g_mono, id);
        }
    } else {
        char* seen = (char*)calloc((size_t)g_ng + 1, 1);
        for (int i = 0; i < g_ne; i++) {
            Ent* e = &g_e[i];
            if (!strcmp(e->kind, "blocked")) continue;
            if (strcmp(e->cat, g_pg[p]) && strcmp(e->also, g_pg[p])) continue;
            if (e->group[0]) {
                int gi = -1; for (int k = 0; k < g_ng; k++) if (!strcmp(g_g[k].id, e->group)) gi = k;
                if (gi >= 0) {
                    if (seen[gi]) continue;                      /* the whole choice is one row with a drop-down */
                    seen[gi] = 1;
                    Row* r = add_row(R_GROUP, -1, gi); int id = IDC_ROW0 + g_nrows - 1;
                    for (int k = 0; k < g_ne && r->nm < 64; k++) {
                        Ent* m = &g_e[k];
                        if (!strcmp(m->group, e->group) && strcmp(m->kind, "blocked") && (!strcmp(m->cat, g_pg[p]) || !strcmp(m->also, g_pg[p]))) r->members[r->nm++] = k;
                    }
                    r->main = mk(L"STATIC", g_g[gi].title, SS_NOPREFIX | SS_ENDELLIPSIS, g_bold, id);
                    r->sub = mk(L"STATIC", "Choose one. Only one of these can be on.", SS_NOPREFIX, g_small, id); SetWindowLongPtrW(r->sub, GWLP_USERDATA, 1);
                    r->combo = mk(L"COMBOBOX", "", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, g_font, id);
                    SendMessageW(r->combo, CB_ADDSTRING, 0, (LPARAM)L"Off");
                    int cur = 0;
                    for (int k = 0; k < r->nm; k++) {
                        char t[300]; snprintf(t, sizeof t, "%s%s", label(&g_e[r->members[k]]), !strcmp(g_e[r->members[k]].status, "untested") ? "  (untested)" : "");
                        wchar_t* w = wide(t); SendMessageW(r->combo, CB_ADDSTRING, 0, (LPARAM)w); free(w);
                        if (ent_on(&g_e[r->members[k]])) cur = k + 1;
                    }
                    SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)cur, 0);
                    SendMessageW(r->combo, CB_SETMINVISIBLE, 12, 0);
                    continue;
                }
            }
            int once = !strcmp(e->mode, "once"), both = !strcmp(e->kind, "live") && (once || !strcmp(e->mode, "both"));
            Row* r = add_row(once ? R_ONCE : R_CHECK, i, -1); int id = IDC_ROW0 + g_nrows - 1;
            if (once) r->main = mk(L"STATIC", label(e), SS_NOPREFIX | SS_ENDELLIPSIS, g_font, id);
            else {
                r->main = mk(L"BUTTON", label(e), BS_AUTOCHECKBOX | WS_TABSTOP, g_font, id);
                SendMessageW(r->main, BM_SETCHECK, ent_on(e) ? BST_CHECKED : BST_UNCHECKED, 0);
            }
            char tag[700]; tag_text(e, tag, sizeof tag);
            r->sub = mk(L"STATIC", tag, SS_NOPREFIX, g_small, id); SetWindowLongPtrW(r->sub, GWLP_USERDATA, 1);
            if (both) r->btn = mk(L"BUTTON", "Do it now", BS_PUSHBUTTON | WS_TABSTOP, g_font, id);
        }
        free(seen);
    }
    update_count();
    lay_rows();
}

/* a switch was changed (click, or the test): state + game. Returns 0 when the change was refused (the control goes back). */
static int entry_changed(Row* r, int idx, int on) {
    Ent* e = &g_e[idx];
    if (!strcmp(e->kind, "code") && e->file[0]) {              /* a hand-written code file: its own switch, needs the build */
        SetWindowTextW(g_note, L"This one is switched in its file (mods\\system\\code) and needs a rebuild.");
        return 0;
    }
    apply(idx, on);
    SetWindowTextW(g_note, !strcmp(e->kind, "live") ? (on ? L"On." : L"Off.") : !strcmp(e->kind, "launch") ? L"Saved: takes effect the next time the game starts." : L"Saved: takes effect after the next \"Play with mods\" (rebuild).");
    (void)r; update_count();
    return 1;
}

static void group_changed(Row* r, int sel) {
    if (sel == 0) {
        for (int k = 0; k < r->nm; k++) {
            Ent* m = &g_e[r->members[k]];
            if (ent_on(m) && !(!strcmp(m->kind, "code") && m->file[0])) apply(r->members[k], 0);
        }
        SetWindowTextW(g_note, L"Off.");
        update_count(); return;
    }
    if (!entry_changed(r, r->members[sel - 1], 1)) {           /* refused: show what is really on */
        int cur = 0; for (int k = 0; k < r->nm; k++) if (ent_on(&g_e[r->members[k]])) cur = k + 1;
        SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)cur, 0);
    }
}

static void layout(int cw, int ch) {
    MoveWindow(g_side, 0, 0, SIDE_W, ch, TRUE);
    MoveWindow(g_title, SIDE_W + PAD_X, 18, cw - SIDE_W - 2 * PAD_X, 30, TRUE);
    MoveWindow(g_count, SIDE_W + PAD_X, 50, cw - SIDE_W - 2 * PAD_X, 20, TRUE);
    MoveWindow(g_host, SIDE_W, 82, cw - SIDE_W, ch - 82 - 64, TRUE);
    MoveWindow(g_note, SIDE_W + PAD_X, ch - 40, cw - SIDE_W - 2 * PAD_X - 240, 20, TRUE);
    MoveWindow(g_off, cw - PAD_X - 130 - 8 - 90, ch - 46, 130, 32, TRUE);
    MoveWindow(g_close, cw - PAD_X - 90, ch - 46, 90, 32, TRUE);
    if (g_nrows) lay_rows();
}

static Row* row_of_id(int id) { int i = id - IDC_ROW0; return i >= 0 && i < g_nrows ? &g_rows[i] : NULL; }

static void test_step(int step);

/* the scrolling panel */
static LRESULT CALLBACK hostproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_CTLCOLORSTATIC: case WM_CTLCOLORBTN: {
        HDC dc = (HDC)wp; SetBkColor(dc, RGB(255, 255, 255)); SetBkMode(dc, OPAQUE);
        SetTextColor(dc, GetWindowLongPtrW((HWND)lp, GWLP_USERDATA) == 1 ? COL_GRAY : COL_TEXT);
        return (LRESULT)g_white;
    }
    case WM_ERASEBKGND: { RECT r; GetClientRect(h, &r); FillRect((HDC)wp, &r, g_white); return 1; }
    case WM_PAINT: {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); RECT cr; GetClientRect(h, &cr);
        HPEN pen = CreatePen(PS_SOLID, 1, RGB(234, 234, 234)); HGDIOBJ old = SelectObject(dc, pen);
        for (int i = 0; i < g_nrows; i++) { int y = g_rows[i].y + g_rows[i].h - 1 - g_scroll; MoveToEx(dc, PAD_X, y, NULL); LineTo(dc, cr.right - PAD_X, y); }
        SelectObject(dc, old); DeleteObject(pen); EndPaint(h, &ps); return 0;
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
    case WM_MOUSEWHEEL: scroll_to(g_scroll - (short)HIWORD(wp) * 60 / WHEEL_DELTA); return 0;
    case WM_SIZE: if (g_nrows) lay_rows(); return 0;
    case WM_COMMAND: {
        Row* r = row_of_id(LOWORD(wp)); if (!r) break;
        int code = HIWORD(wp);
        if (r->kind == R_GROUP && code == CBN_SELCHANGE) group_changed(r, (int)SendMessageW(r->combo, CB_GETCURSEL, 0, 0));
        else if (r->kind == R_CHECK && (HWND)lp == r->main && code == BN_CLICKED) {
            int on = SendMessageW(r->main, BM_GETCHECK, 0, 0) == BST_CHECKED;
            if (!entry_changed(r, r->idx, on)) SendMessageW(r->main, BM_SETCHECK, on ? BST_UNCHECKED : BST_CHECKED, 0);
        } else if (r->btn && (HWND)lp == r->btn && code == BN_CLICKED && !strcmp(g_e[r->idx].kind, "live")) {
            EnterCriticalSection(&g_cs); send_run(r->idx); LeaveCriticalSection(&g_cs); SetWindowTextW(g_note, L"Done (once).");
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
    if (data == g_keys_page) { HPEN pen = CreatePen(PS_SOLID, 1, RGB(222, 222, 222)); HGDIOBJ o = SelectObject(dc, pen); MoveToEx(dc, r.left + 16, r.top, NULL); LineTo(dc, r.right - 16, r.top); SelectObject(dc, o); DeleteObject(pen); }
    if (sel) {
        RECT b = { r.left + 8, r.top + 3, r.right - 8, r.bottom - 3 }; HBRUSH hb = CreateSolidBrush(RGB(228, 228, 228)); FillRect(dc, &b, hb); DeleteObject(hb);
        RECT bar = { r.left + 8, r.top + 11, r.left + 11, r.bottom - 11 }; hb = CreateSolidBrush(COL_ACCENT); FillRect(dc, &bar, hb); DeleteObject(hb);
    }
    wchar_t t[200]; SendMessageW(d->hwndItem, LB_GETTEXT, d->itemID, (LPARAM)t);
    SetBkMode(dc, TRANSPARENT); SetTextColor(dc, COL_TEXT); HGDIOBJ o = SelectObject(dc, sel ? g_bold : g_font);
    RECT tr = { r.left + 24, r.top, r.right - 12, r.bottom }; DrawTextW(dc, t, -1, &tr, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS);
    SelectObject(dc, o);
}

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_TIMER: KillTimer(h, wp); test_step((int)wp); return 0;
    case WM_SIZE: if (g_side) layout(LOWORD(lp), HIWORD(lp)); return 0;
    case WM_GETMINMAXINFO: { MINMAXINFO* mm = (MINMAXINFO*)lp; mm->ptMinTrackSize.x = 640; mm->ptMinTrackSize.y = 420; return 0; }
    case WM_SHOW_CHEATS: ShowWindow(h, SW_SHOWNORMAL); SetForegroundWindow(h); return 0;
    case WM_CLOSE: ShowWindow(h, SW_HIDE); return 0;                   /* hidden, not destroyed: the game goes on */
    case WM_CTLCOLORSTATIC: {
        HDC dc = (HDC)wp; HWND c = (HWND)lp; int id = GetDlgCtrlID(c);
        SetBkColor(dc, RGB(255, 255, 255)); SetTextColor(dc, id == IDC_TITLE ? COL_TEXT : COL_GRAY);
        return (LRESULT)g_white;
    }
    case WM_CTLCOLORLISTBOX: if ((HWND)lp == g_side) return (LRESULT)g_gray; break;
    case WM_MEASUREITEM: { MEASUREITEMSTRUCT* mi = (MEASUREITEMSTRUCT*)lp; if (mi->CtlID == IDC_SIDE) { mi->itemHeight = 38; return TRUE; } break; }
    case WM_DRAWITEM: if (wp == IDC_SIDE) { draw_side((DRAWITEMSTRUCT*)lp); return TRUE; } break;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_SIDE: if (HIWORD(wp) == LBN_SELCHANGE) build_page(); return 0;
        case IDC_CLOSE: ShowWindow(h, SW_HIDE); return 0;
        case IDC_OFF:
            if (MessageBoxW(h, L"Switch every cheat off?", L"Cheats", MB_YESNO | MB_ICONQUESTION) == IDYES) { all_off(); build_page(); SetWindowTextW(g_note, L"Everything is off."); }
            return 0;
        }
        break;
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* Test hook: DQIX_CHEATWIN_TEST=<entry id>[,<picture.bmp>] opens the window by itself, switches that cheat on the way a click does
 * (the page, then the row's check box) and draws the window into the picture. Used by tests/test_cheatwin.py. */
static void save_shot(HWND h, const char* path) {
    RECT r; GetWindowRect(h, &r); int w = r.right - r.left, ht = r.bottom - r.top;
    HDC dc = GetDC(NULL), mem = CreateCompatibleDC(dc);
    HBITMAP bmp = CreateCompatibleBitmap(dc, w, ht); HGDIOBJ old = SelectObject(mem, bmp);
    PrintWindow(h, mem, 2);
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

static void select_page_of(int idx) {
    for (int t = 0; t < (int)SendMessageW(g_side, LB_GETCOUNT, 0, 0); t++) {
        int p = (int)SendMessageW(g_side, LB_GETITEMDATA, (WPARAM)t, 0);
        if (p != g_keys_page && !strcmp(g_e[idx].cat, g_pg[p])) { SendMessageW(g_side, LB_SETCURSEL, (WPARAM)t, 0); build_page(); return; }
    }
}

static void test_step(int step) {
    if (step == 1) {
        int idx = -1; for (int i = 0; i < g_ne; i++) if (!strcmp(g_e[i].id, g_test_id)) idx = i;
        if (idx < 0) { fprintf(stderr, "cheatwin test: no entry %s\n", g_test_id); return; }
        select_page_of(idx);
        for (int i = 0; i < g_nrows; i++) {
            Row* r = &g_rows[i]; int k = -1;
            if (r->kind == R_CHECK && r->idx == idx) { SendMessageW(r->main, BM_SETCHECK, BST_CHECKED, 0); entry_changed(r, idx, 1); k = 0; }
            else if (r->kind == R_GROUP) { for (int q = 0; q < r->nm; q++) if (r->members[q] == idx) { SendMessageW(r->combo, CB_SETCURSEL, (WPARAM)(q + 1), 0); group_changed(r, q + 1); k = 0; } }
            if (k == 0) { fprintf(stderr, "cheatwin test: switched on %s\n", g_test_id); break; }
        }
    } else if (step == 2 && g_test_shot[0]) { save_shot(g_win, g_test_shot); fprintf(stderr, "cheatwin test: picture written\n"); }
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

static HFONT mkfont(const wchar_t* face, int px, int weight) {
    return CreateFontW(-px, 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, face);
}

static DWORD WINAPI ui_thread(LPVOID unused) {
    (void)unused;
    enable_styles();
    HMODULE cc = LoadLibraryW(L"comctl32.dll");
    if (cc) {
        typedef BOOL (WINAPI* Fn)(const INITCOMMONCONTROLSEX*);
        Fn f = (Fn)GetProcAddress(cc, "InitCommonControlsEx");
        INITCOMMONCONTROLSEX ic = { sizeof ic, ICC_STANDARD_CLASSES };
        if (f) f(&ic);
    }
    g_font = mkfont(L"Segoe UI", 14, FW_NORMAL); g_small = mkfont(L"Segoe UI", 12, FW_NORMAL); g_bold = mkfont(L"Segoe UI", 14, FW_SEMIBOLD);
    g_head = mkfont(L"Segoe UI", 24, FW_SEMIBOLD); g_mono = mkfont(L"Consolas", 13, FW_SEMIBOLD);
    g_white = CreateSolidBrush(RGB(255, 255, 255)); g_gray = CreateSolidBrush(RGB(243, 243, 243));
    HINSTANCE hi = GetModuleHandleW(NULL);
    WNDCLASSW wc; memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = wndproc; wc.hInstance = hi; wc.lpszClassName = L"DqixCheatWindow";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW); wc.hbrBackground = g_white;
    RegisterClassW(&wc);
    wc.lpfnWndProc = hostproc; wc.lpszClassName = L"DqixCheatPage"; RegisterClassW(&wc);
    g_win = CreateWindowExW(0, L"DqixCheatWindow", L"Cheats", WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT, CW_USEDEFAULT, 980, 700, NULL, NULL, hi, NULL);
    g_side = CreateWindowExW(0, L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP | LBS_NOTIFY | LBS_OWNERDRAWFIXED | LBS_HASSTRINGS | LBS_NOINTEGRALHEIGHT, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_SIDE, hi, NULL);
    g_title = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_NOPREFIX | SS_ENDELLIPSIS, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_TITLE, hi, NULL);
    g_count = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_NOPREFIX, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_COUNT, hi, NULL);
    g_host = CreateWindowExW(WS_EX_CONTROLPARENT, L"DqixCheatPage", L"", WS_CHILD | WS_VISIBLE | WS_VSCROLL | WS_CLIPCHILDREN, 0, 0, 10, 10, g_win, NULL, hi, NULL);
    g_note = CreateWindowExW(0, L"STATIC", L"Switches work at once while you play. Save your game first.", WS_CHILD | WS_VISIBLE | SS_NOPREFIX | SS_ENDELLIPSIS, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_NOTE, hi, NULL);
    g_off = CreateWindowExW(0, L"BUTTON", L"Everything off", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_OFF, hi, NULL);
    g_close = CreateWindowExW(0, L"BUTTON", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_CLOSE, hi, NULL);
    SendMessageW(g_title, WM_SETFONT, (WPARAM)g_head, TRUE); SendMessageW(g_count, WM_SETFONT, (WPARAM)g_small, TRUE); SendMessageW(g_note, WM_SETFONT, (WPARAM)g_small, TRUE);
    SendMessageW(g_off, WM_SETFONT, (WPARAM)g_font, TRUE); SendMessageW(g_close, WM_SETFONT, (WPARAM)g_font, TRUE); SendMessageW(g_side, WM_SETFONT, (WPARAM)g_font, TRUE);
    SendMessageW(g_side, LB_SETITEMHEIGHT, 0, 38);
    g_keys_page = g_npg;                                          /* the Keybinds entry: a page number past the real ones */
    for (int i = 0; i < g_npg; i++) {
        int has = 0; for (int k = 0; k < g_ne && !has; k++) has = strcmp(g_e[k].kind, "blocked") && (!strcmp(g_e[k].cat, g_pg[i]) || !strcmp(g_e[k].also, g_pg[i]));
        if (!has) continue;
        wchar_t* w = wide(g_pg[i]); int at = (int)SendMessageW(g_side, LB_ADDSTRING, 0, (LPARAM)w); SendMessageW(g_side, LB_SETITEMDATA, (WPARAM)at, i); free(w);
    }
    int at = (int)SendMessageW(g_side, LB_ADDSTRING, 0, (LPARAM)L"Keybinds"); SendMessageW(g_side, LB_SETITEMDATA, (WPARAM)at, g_keys_page);
    SendMessageW(g_side, LB_SETCURSEL, 0, 0);
    RECT r; GetClientRect(g_win, &r); layout(r.right, r.bottom);
    build_page();
    ShowWindow(g_win, SW_SHOWNORMAL); SetForegroundWindow(g_win);
    if (g_test_id[0]) { SetTimer(g_win, 1, 1500, NULL); SetTimer(g_win, 2, 4000, NULL); }
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(g_win, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    return 0;
}

void mod_cheatwin_show(void) {
    if (!g_cs_init) { InitializeCriticalSection(&g_cs); g_cs_init = 1; }
    if (!g_loaded) { load_catalog(); if (g_loaded) { load_state(); migrate_state(); seed_defaults(); } }
    if (!g_loaded) {
        MessageBoxW(NULL, L"There is no cheat list yet. Run \"mods\\Play with mods.bat\" once (it makes the list), then try again.", L"Cheats", MB_OK | MB_ICONINFORMATION);
        return;
    }
    static HANDLE th;
    if (!th) { th = CreateThread(NULL, 0, ui_thread, NULL, 0, NULL); return; }
    if (g_win) PostMessageW(g_win, WM_SHOW_CHEATS, 0, 0);
}
#else
void mod_cheatwin_boot(void) {}
void mod_cheatwin_show(void) {}
#endif
