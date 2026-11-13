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
 * Windows only; elsewhere the functions do nothing. Plain Win32 (tab + list view), so it needs nothing the game doesn't have.
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
    seed_defaults();
    for (int i = 0; i < g_ne; i++)                           /* options for the next start: set before the game reads them */
        if (!strcmp(g_e[i].kind, "launch") && ent_on(&g_e[i]) && strchr(g_e[i].env, '=')) _putenv(g_e[i].env);
    CreateThread(NULL, 0, agent, NULL, 0, NULL);
}

/* ---------------------------------------------------------------- the window */
enum { IDC_TAB = 100, IDC_LIST, IDC_INFO, IDC_ONCE, IDC_OFF, IDC_CLOSE, IDC_NOTE, WM_SHOW_CHEATS = WM_APP + 1 };
static HWND g_win, g_tab, g_list, g_info, g_once, g_note;
static int g_filling;
static HFONT g_font;

static wchar_t* wide(const char* s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0); wchar_t* w = (wchar_t*)malloc((size_t)(n + 1) * sizeof *w);
    if (w) { MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n); w[n] = 0; }
    return w;
}

static const Grp* grp_of(const char* id) { for (int i = 0; i < g_ng; i++) if (!strcmp(g_g[i].id, id)) return &g_g[i]; return NULL; }

static const char* label(const Ent* e) { return e->option[0] ? e->option : e->name; }

static void tag_text(const Ent* e, char* out, size_t n) {
    out[0] = 0;
    const char* who;
    if (!strcmp(e->kind, "live")) who = "one player is enough";
    else if (!strcmp(e->kind, "launch")) who = !strncmp(e->env, "DQIX_MOD_", 9) ? "all players, next start" : "own PC, next start";
    else who = "all players, needs a rebuild";
    snprintf(out, n, "%s%s%s%s%s", who, e->keys[0] ? " | keys: " : "", e->keys, !strcmp(e->status, "untested") ? " | untested" : "", !strcmp(e->mode, "once") ? " | once" : "");
}

static int row_entry(int row) {
    LVITEMW it; memset(&it, 0, sizeof it); it.mask = LVIF_PARAM; it.iItem = row;
    return SendMessageW(g_list, LVM_GETITEMW, 0, (LPARAM)&it) ? (int)it.lParam : -1;
}

static void fill_page(void) {
    int sel = TabCtrl_GetCurSel(g_tab), p = -1;
    if (sel >= 0) { TCITEMW ti; memset(&ti, 0, sizeof ti); ti.mask = TCIF_PARAM; if (SendMessageW(g_tab, TCM_GETITEMW, (WPARAM)sel, (LPARAM)&ti)) p = (int)ti.lParam; }
    if (p < 0 || p >= g_npg) return;                         /* (tabs of pages without a visible cheat are left out: the page number is kept in the tab) */
    g_filling = 1;
    SendMessageW(g_list, WM_SETREDRAW, FALSE, 0);
    ListView_DeleteAllItems(g_list);
    char* seen = (char*)calloc((size_t)g_ng + 1, 1);
    int row = 0;
    for (int i = 0; i < g_ne; i++) {
        Ent* e = &g_e[i];
        if (!strcmp(e->kind, "blocked")) continue;
        if (strcmp(e->cat, g_pg[p]) && strcmp(e->also, g_pg[p])) continue;
        if (e->group[0]) {
            int gi = -1; for (int k = 0; k < g_ng; k++) if (!strcmp(g_g[k].id, e->group)) gi = k;
            if (gi >= 0 && !seen[gi]) {                      /* the heading of a choice, once */
                seen[gi] = 1;
                char head[300]; snprintf(head, sizeof head, "%s   (choose one)", g_g[gi].title);
                wchar_t* w = wide(head);
                LVITEMW it; memset(&it, 0, sizeof it); it.mask = LVIF_TEXT | LVIF_PARAM; it.iItem = row; it.pszText = w; it.lParam = -1 - gi;
                SendMessageW(g_list, LVM_INSERTITEMW, 0, (LPARAM)&it); free(w);
                ListView_SetItemState(g_list, row, INDEXTOSTATEIMAGEMASK(0), LVIS_STATEIMAGEMASK);
                row++;
            }
        }
        char txt[400]; snprintf(txt, sizeof txt, "%s%s", e->group[0] ? "      " : "", label(e));
        wchar_t* w = wide(txt);
        LVITEMW it; memset(&it, 0, sizeof it); it.mask = LVIF_TEXT | LVIF_PARAM; it.iItem = row; it.pszText = w; it.lParam = i;
        SendMessageW(g_list, LVM_INSERTITEMW, 0, (LPARAM)&it); free(w);
        char tag[300]; tag_text(e, tag, sizeof tag); wchar_t* wt = wide(tag);
        LVITEMW sub; memset(&sub, 0, sizeof sub); sub.mask = LVIF_TEXT; sub.iItem = row; sub.iSubItem = 1; sub.pszText = wt;
        SendMessageW(g_list, LVM_SETITEMW, 0, (LPARAM)&sub); free(wt);
        if (!strcmp(e->mode, "once")) { ListView_SetItemState(g_list, row, INDEXTOSTATEIMAGEMASK(0), LVIS_STATEIMAGEMASK); }
        else { ListView_SetItemState(g_list, row, INDEXTOSTATEIMAGEMASK(ent_on(e) ? 2 : 1), LVIS_STATEIMAGEMASK); }
        row++;
    }
    free(seen);
    SendMessageW(g_list, WM_SETREDRAW, TRUE, 0);
    g_filling = 0;
    SetWindowTextW(g_info, L"");
    EnableWindow(g_once, FALSE);
}

static void show_info(int idx) {
    if (idx < 0) { SetWindowTextW(g_info, L""); EnableWindow(g_once, FALSE); return; }
    Ent* e = &g_e[idx]; char buf[2400], tag[300]; tag_text(e, tag, sizeof tag);
    const Grp* g = e->group[0] ? grp_of(e->group) : NULL;
    snprintf(buf, sizeof buf, "%s%s%s\r\n%s\r\n%s%s%s",
             e->name, g ? "   (" : "", g ? g->title : "",
             tag, e->note[0] ? e->note : "",
             !strcmp(e->kind, "code") ? "\r\nChanges how the game works: it takes effect after the next \"Play with mods\" (the game is built again)." : "",
             !strcmp(e->kind, "launch") ? "\r\nTakes effect the next time the game starts." : "");
    if (g) strncat(buf, ")", sizeof buf - strlen(buf) - 1);
    wchar_t* w = wide(buf); SetWindowTextW(g_info, w); free(w);
    EnableWindow(g_once, !strcmp(e->kind, "live") && (!strcmp(e->mode, "once") || !strcmp(e->mode, "both")));
}

static void layout(int cw, int ch) {
    MoveWindow(g_tab, 8, 8, cw - 16, ch - 140, TRUE);
    RECT r = { 0, 0, cw - 16, ch - 140 }; TabCtrl_AdjustRect(g_tab, FALSE, &r);
    MoveWindow(g_list, 8 + r.left, 8 + r.top, r.right - r.left, r.bottom - r.top, TRUE);
    int w = r.right - r.left - 24; if (w < 200) w = 200;
    ListView_SetColumnWidth(g_list, 0, w * 58 / 100); ListView_SetColumnWidth(g_list, 1, w * 42 / 100);
    MoveWindow(g_info, 8, ch - 126, cw - 16, 74, TRUE);
    MoveWindow(g_once, 8, ch - 44, 110, 28, TRUE);
    MoveWindow(GetDlgItem(g_win, IDC_OFF), 126, ch - 44, 130, 28, TRUE);
    MoveWindow(g_note, 266, ch - 42, cw - 266 - 110 - 16, 24, TRUE);
    MoveWindow(GetDlgItem(g_win, IDC_CLOSE), cw - 108, ch - 44, 100, 28, TRUE);
}

static void test_step(int step);
static void set_font(HWND h) { SendMessageW(h, WM_SETFONT, (WPARAM)g_font, TRUE); }

static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_TIMER: KillTimer(h, wp); test_step((int)wp); return 0;
    case WM_SIZE: if (g_tab) layout(LOWORD(lp), HIWORD(lp)); return 0;
    case WM_GETMINMAXINFO: { MINMAXINFO* mm = (MINMAXINFO*)lp; mm->ptMinTrackSize.x = 560; mm->ptMinTrackSize.y = 420; return 0; }
    case WM_SHOW_CHEATS: ShowWindow(h, SW_SHOWNORMAL); SetForegroundWindow(h); return 0;
    case WM_CLOSE: ShowWindow(h, SW_HIDE); return 0;                   /* hidden, not destroyed: the game goes on */
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case IDC_CLOSE: ShowWindow(h, SW_HIDE); return 0;
        case IDC_OFF:
            if (MessageBoxW(h, L"Switch every cheat off?", L"Cheats", MB_YESNO | MB_ICONQUESTION) == IDYES) { all_off(); fill_page(); SetWindowTextW(g_note, L"Everything is off."); }
            return 0;
        case IDC_ONCE: {
            int sel = ListView_GetNextItem(g_list, -1, LVNI_SELECTED), idx = sel >= 0 ? row_entry(sel) : -1;
            if (idx >= 0 && !strcmp(g_e[idx].kind, "live")) { EnterCriticalSection(&g_cs); send_run(idx); LeaveCriticalSection(&g_cs); SetWindowTextW(g_note, L"Done (once)."); }
            return 0;
        }
        }
        break;
    case WM_NOTIFY: {
        NMHDR* nh = (NMHDR*)lp;
        if (nh->idFrom == IDC_TAB && nh->code == TCN_SELCHANGE) { fill_page(); return 0; }
        if (nh->idFrom == IDC_LIST && nh->code == LVN_ITEMCHANGED && !g_filling) {
            NMLISTVIEW* nl = (NMLISTVIEW*)lp;
            int idx = (int)nl->lParam;
            if (idx < 0) { LVITEMW it; memset(&it, 0, sizeof it); it.mask = LVIF_PARAM; it.iItem = nl->iItem; if (SendMessageW(g_list, LVM_GETITEMW, 0, (LPARAM)&it)) idx = (int)it.lParam; }
            if (nl->uChanged & LVIF_STATE) {
                if ((nl->uNewState & LVIS_SELECTED) && !(nl->uOldState & LVIS_SELECTED)) show_info(idx);
                int oldc = (int)((nl->uOldState & LVIS_STATEIMAGEMASK) >> 12), newc = (int)((nl->uNewState & LVIS_STATEIMAGEMASK) >> 12);
                if (idx >= 0 && oldc && newc && oldc != newc) {
                    int on = newc == 2;
                    if (!strcmp(g_e[idx].kind, "code") && g_e[idx].file[0]) {       /* a hand-written code file: its own switch, needs the build */
                        SetWindowTextW(g_note, L"This one is switched in its file (mods\\system\\code) and needs a rebuild.");
                        g_filling = 1; ListView_SetItemState(g_list, nl->iItem, INDEXTOSTATEIMAGEMASK(oldc), LVIS_STATEIMAGEMASK); g_filling = 0;
                        return 0;
                    }
                    apply(idx, on);
                    SetWindowTextW(g_note, !strcmp(g_e[idx].kind, "live") ? (on ? L"On." : L"Off.") : !strcmp(g_e[idx].kind, "launch") ? L"Saved: takes effect the next time the game starts." : L"Saved: takes effect after the next \"Play with mods\" (rebuild).");
                    if (on && g_e[idx].group[0]) { int keep = nl->iItem; (void)keep; g_filling = 1; fill_page(); g_filling = 0; }
                }
            }
        }
        return 0;
    }
    }
    return DefWindowProcW(h, m, wp, lp);
}

/* Test hook: DQIX_CHEATWIN_TEST=<entry id>[,<picture.bmp>] opens the window by itself, switches that cheat on the way a click does
 * (the page's tab, then the row's check box) and draws the window into the picture. Used by tests/test_cheatwin.py. */
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

static void test_step(int step) {
    if (step == 1) {
        int idx = -1; for (int i = 0; i < g_ne; i++) if (!strcmp(g_e[i].id, g_test_id)) idx = i;
        if (idx < 0) { fprintf(stderr, "cheatwin test: no entry %s\n", g_test_id); return; }
        for (int t = 0; t < TabCtrl_GetItemCount(g_tab); t++) {          /* the page that has it */
            TCITEMW ti; memset(&ti, 0, sizeof ti); ti.mask = TCIF_PARAM; SendMessageW(g_tab, TCM_GETITEMW, (WPARAM)t, (LPARAM)&ti);
            if (!strcmp(g_e[idx].cat, g_pg[ti.lParam])) { TabCtrl_SetCurSel(g_tab, t); fill_page(); break; }
        }
        for (int row = 0; row < ListView_GetItemCount(g_list); row++)
            if (row_entry(row) == idx) { ListView_SetItemState(g_list, row, INDEXTOSTATEIMAGEMASK(2), LVIS_STATEIMAGEMASK); ListView_SetItemState(g_list, row, LVIS_SELECTED, LVIS_SELECTED); fprintf(stderr, "cheatwin test: switched on %s\n", g_test_id); break; }
    } else if (step == 2 && g_test_shot[0]) { save_shot(g_win, g_test_shot); fprintf(stderr, "cheatwin test: picture written\n"); }
}

static DWORD WINAPI ui_thread(LPVOID unused) {
    (void)unused;
    HMODULE cc = LoadLibraryW(L"comctl32.dll");
    if (cc) {
        typedef BOOL (WINAPI* Fn)(const INITCOMMONCONTROLSEX*);
        Fn f = (Fn)GetProcAddress(cc, "InitCommonControlsEx");
        INITCOMMONCONTROLSEX ic = { sizeof ic, ICC_LISTVIEW_CLASSES | ICC_TAB_CLASSES };
        if (f) f(&ic);
    }
    g_font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
    WNDCLASSW wc; memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = wndproc; wc.hInstance = GetModuleHandleW(NULL); wc.lpszClassName = L"DqixCheatWindow";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW); wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    RegisterClassW(&wc);
    g_win = CreateWindowExW(0, L"DqixCheatWindow", L"Cheats", WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT, CW_USEDEFAULT, 820, 640, NULL, NULL, wc.hInstance, NULL);
    g_tab = CreateWindowExW(0, L"SysTabControl32", L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | TCS_MULTILINE, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_TAB, wc.hInstance, NULL);
    g_list = CreateWindowExW(WS_EX_CLIENTEDGE, L"SysListView32", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP | LVS_REPORT | LVS_SINGLESEL | LVS_SHOWSELALWAYS, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_LIST, wc.hInstance, NULL);
    g_info = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | WS_VSCROLL, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_INFO, wc.hInstance, NULL);
    g_once = CreateWindowExW(0, L"BUTTON", L"Do it now", WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_DISABLED, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_ONCE, wc.hInstance, NULL);
    CreateWindowExW(0, L"BUTTON", L"Everything off", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_OFF, wc.hInstance, NULL);
    CreateWindowExW(0, L"BUTTON", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_CLOSE, wc.hInstance, NULL);
    g_note = CreateWindowExW(0, L"STATIC", L"Switches work at once while you play. Save your game first.", WS_CHILD | WS_VISIBLE, 0, 0, 10, 10, g_win, (HMENU)(UINT_PTR)IDC_NOTE, wc.hInstance, NULL);
    for (HWND c = GetWindow(g_win, GW_CHILD); c; c = GetWindow(c, GW_HWNDNEXT)) set_font(c);
    ListView_SetExtendedListViewStyle(g_list, LVS_EX_CHECKBOXES | LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER);
    LVCOLUMNW col; memset(&col, 0, sizeof col); col.mask = LVCF_TEXT | LVCF_WIDTH;
    col.pszText = (LPWSTR)L"Cheat"; col.cx = 380; SendMessageW(g_list, LVM_INSERTCOLUMNW, 0, (LPARAM)&col);
    col.pszText = (LPWSTR)L"Works with friends / notes"; col.cx = 280; SendMessageW(g_list, LVM_INSERTCOLUMNW, 1, (LPARAM)&col);
    for (int i = 0; i < g_npg; i++) {
        int has = 0; for (int k = 0; k < g_ne && !has; k++) has = strcmp(g_e[k].kind, "blocked") && (!strcmp(g_e[k].cat, g_pg[i]) || !strcmp(g_e[k].also, g_pg[i]));
        if (!has) continue;
        char title[200]; size_t tl = 0;                      /* a tab shows "&" as an underline: double it */
        for (const char* c = g_pg[i]; *c && tl < sizeof title - 3; c++) { title[tl++] = *c; if (*c == '&') title[tl++] = '&'; }
        title[tl] = 0;
        wchar_t* w = wide(title);
        TCITEMW ti; memset(&ti, 0, sizeof ti); ti.mask = TCIF_TEXT | TCIF_PARAM; ti.pszText = w; ti.lParam = i;
        SendMessageW(g_tab, TCM_INSERTITEMW, (WPARAM)TabCtrl_GetItemCount(g_tab), (LPARAM)&ti); free(w);
    }
    RECT r; GetClientRect(g_win, &r); layout(r.right, r.bottom);
    fill_page();
    ShowWindow(g_win, SW_SHOWNORMAL); SetForegroundWindow(g_win);
    if (g_test_id[0]) { SetTimer(g_win, 1, 1500, NULL); SetTimer(g_win, 2, 4000, NULL); }
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(g_win, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    return 0;
}

/* NB: the tab's page index is its position, but pages without a visible cheat are left out: map through lParam */
void mod_cheatwin_show(void) {
    if (!g_cs_init) { InitializeCriticalSection(&g_cs); g_cs_init = 1; }
    if (!g_loaded) { load_catalog(); if (g_loaded) { load_state(); seed_defaults(); } }
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
