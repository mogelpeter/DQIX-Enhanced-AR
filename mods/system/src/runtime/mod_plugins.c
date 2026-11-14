/* DQIX Enhanced mods: plugins (menu bar: Plugins).
 *
 * Loads every DLL in the game's mods\plugins folder when the menu bar is built, gives it the interface in
 * dqix_plugin.h (RAM, buttons, menu items, a log) and lists it under Plugins with its own items.
 *
 *   mod_plugins_menu(HMENU)   menu_win32.c, once: loads the plugins and fills the Plugins tab
 *   mod_plugins_command(id)   frontend_sdl.c: an item of the tab (ids MP_FIRST..MP_LAST)
 *   mod_plugins_frame(keys)   mod_cheats.c, every frame: the plugins' on_frame (not in a session)
 *
 * Put into runtime/ by mods/system/tools/apply_runtime_mod.py (with dqix_plugin.h from mods/plugins/sdk).
 * The copies of other players' consoles (dqixcore.dll) never build a menu, so they never load a plugin.
 * DQIX_PLUGINS_TEST=1 loads them without a menu (headless tests); DQIX_PLUGINS_OFF=1 loads none;
 * DQIX_PLUGINS_DIR=<folder> loads from there instead of mods\plugins.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nds.h"
#include "session.h"
#include "dqix_plugin.h"

#define MP_FIRST   400                        /* the plugins' own items */
#define MP_LAST    469
#define MP_FOLDER  470
#define MP_HELP    471
#define MP_ABOUT   472                        /* + plugin: its About box (up to 503) */
#define MP_MAX     32                         /* plugins */
#define MP_ITEMS   (MP_LAST - MP_FIRST + 1)

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

const char* update_project_dir(void);         /* update.c: the folder with BUILD.bat, or NULL */

typedef struct { HMODULE dll; DqixPlugin p; char file[MAX_PATH]; HMENU menu; } MpPlugin;
typedef struct { int plugin; char label[128]; void (*click)(void*); void* user; int checked; } MpItem;

static MpPlugin g_pl[MP_MAX]; static int g_npl;
static MpItem g_it[MP_ITEMS]; static int g_nit;
static int g_loaded, g_cur = -1;              /* g_cur: the plugin whose init runs now (menu_item belongs to it) */
static FILE* g_log;

static void mp_log(const char* t) {
    fprintf(stderr, "plugin: %s\n", t);
    if (g_log) { fprintf(g_log, "%s\n", t); fflush(g_log); }
}
static void mp_logf(const char* fmt, const char* a, const char* b) {
    char t[700]; snprintf(t, sizeof t, fmt, a, b); mp_log(t);
}

static int mp_ram(uint32_t a, uint32_t n) {
    a &= 0x0FFFFFFFu;
    return a >= 0x02000000u && n <= MAIN_RAM_SIZE && a - 0x02000000u <= MAIN_RAM_SIZE - n;
}
static int h_read(uint32_t a, void* out, uint32_t n) {
    if (!out || !mp_ram(a, n)) return 0;
    memcpy(out, &g_main_ram[(a & 0x0FFFFFFFu) - 0x02000000u], n); return 1;
}
static int h_write(uint32_t a, const void* in, uint32_t n) {
    if (!in || !mp_ram(a, n) || session_running()) return 0;      /* one PC alone changing RAM breaks a session */
    memcpy(&g_main_ram[(a & 0x0FFFFFFFu) - 0x02000000u], in, n); return 1;
}
static void h_log(const char* t) {
    const char* who = "?";                                         /* during its init (g_cur == g_npl) the name may not be set yet */
    if (g_cur >= 0 && g_cur <= g_npl && g_cur < MP_MAX) who = g_pl[g_cur].p.name && g_pl[g_cur].p.name[0] ? g_pl[g_cur].p.name : g_pl[g_cur].file;
    char b[700]; snprintf(b, sizeof b, "%s: %s", who, t ? t : ""); mp_log(b);
}
static void wide(const char* s, wchar_t* w, int n) { if (!MultiByteToWideChar(CP_UTF8, 0, s ? s : "", -1, w, n)) w[0] = 0; }
static void h_message(const char* title, const char* text) {
    static wchar_t wt[256], wx[4096];
    wide(title, wt, 256); wide(text, wx, 4096);
    MessageBoxW(GetActiveWindow(), wx, wt, MB_OK | MB_ICONINFORMATION);
}
static int h_menu_item(const char* label, void (*click)(void*), void* user) {
    if (!g_loaded || g_cur < 0 || g_nit >= MP_ITEMS || !label) return -1;     /* only inside dqix_plugin_init */
    MpItem* it = &g_it[g_nit];
    it->plugin = g_cur; it->click = click; it->user = user; it->checked = 0;
    snprintf(it->label, sizeof it->label, "%s", label);
    return g_nit++;
}
static void h_menu_check(int item, int on) {
    if (item < 0 || item >= g_nit) return;
    g_it[item].checked = on != 0;
    HMENU m = g_pl[g_it[item].plugin].menu;
    if (m) CheckMenuItem(m, (UINT)(MP_FIRST + item), MF_BYCOMMAND | (on ? MF_CHECKED : MF_UNCHECKED));
}
static uint64_t h_frame(void) { return g_frame; }
static const char* h_game_dir(void) { const char* r = update_project_dir(); return r ? r : "."; }
static int h_in_session(void) { return session_running(); }

static const DqixHost g_host = { DQIX_PLUGIN_API, h_read, h_write, h_log, h_message, h_menu_item, h_menu_check,
                                 h_frame, h_game_dir, h_in_session };

static void mp_exit(void) {
    for (int i = 0; i < g_npl; i++) if (g_pl[i].p.on_exit) { g_cur = i; g_pl[i].p.on_exit(); }
    if (g_log) fclose(g_log), g_log = NULL;
}

static int mp_folder(wchar_t* w, int n) {
    const char* over = getenv("DQIX_PLUGINS_DIR");                 /* tests: a folder of their own */
    if (over && over[0]) return MultiByteToWideChar(CP_UTF8, 0, over, -1, w, n) > 0;
    const char* root = update_project_dir();
    wchar_t r[MAX_PATH];
    if (!root || !MultiByteToWideChar(CP_UTF8, 0, root, -1, r, MAX_PATH)) return 0;
    _snwprintf(w, n, L"%ls\\mods\\plugins", r); w[n - 1] = 0;
    return 1;
}

static void mp_load(void) {
    if (g_loaded) return;
    g_loaded = 1;
    if (getenv("DQIX_PLUGINS_OFF")) return;
    wchar_t dir[MAX_PATH], pat[MAX_PATH + 8], path[MAX_PATH * 2];
    if (!mp_folder(dir, MAX_PATH)) return;
    CreateDirectoryW(dir, NULL);
    _snwprintf(path, MAX_PATH * 2, L"%ls\\plugins.log", dir); path[MAX_PATH * 2 - 1] = 0;
    g_log = _wfopen(path, L"w");
    _snwprintf(pat, MAX_PATH + 8, L"%ls\\*.dll", dir); pat[MAX_PATH + 7] = 0;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) { mp_log("no plugins in mods\\plugins"); return; }
    SetDllDirectoryW(dir);                                         /* a plugin's own DLLs can sit next to it */
    do {
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        char name[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, fd.cFileName, -1, name, MAX_PATH, NULL, NULL);
        if (g_npl >= MP_MAX) { mp_logf("%s: not loaded (more than 32 plugins)%s", name, ""); continue; }
        _snwprintf(path, MAX_PATH * 2, L"%ls\\%ls", dir, fd.cFileName); path[MAX_PATH * 2 - 1] = 0;
        HMODULE dll = LoadLibraryW(path);
        if (!dll) { mp_logf("%s: not loaded (not a 64-bit DLL, or a DLL it needs is missing)%s", name, ""); continue; }
        DqixPluginInit init = (DqixPluginInit)(void*)GetProcAddress(dll, "dqix_plugin_init");
        if (!init) { mp_logf("%s: not loaded (no dqix_plugin_init)%s", name, ""); FreeLibrary(dll); continue; }
        MpPlugin* p = &g_pl[g_npl];
        memset(p, 0, sizeof *p);
        p->dll = dll; snprintf(p->file, sizeof p->file, "%s", name);
        int items = g_nit;
        g_cur = g_npl;
        int ok = init(&g_host, &p->p);
        g_cur = -1;
        if (!ok || !p->p.name || !p->p.name[0]) {
            mp_logf("%s: not loaded (%s)", name, ok ? "it has no name" : "it said no");
            g_nit = items; FreeLibrary(dll); continue;
        }
        g_npl++;
        mp_logf("loaded %s from %s", p->p.name, name);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    SetDllDirectoryW(NULL);
    atexit(mp_exit);
}

/* menu_win32.c: fill the Plugins tab */
void mod_plugins_menu(void* bar_menu) {
    HMENU m = (HMENU)bar_menu;
    wchar_t w[300];
    mp_load();
    for (int i = 0; i < g_npl; i++) {
        MpPlugin* p = &g_pl[i];
        char t[200];
        snprintf(t, sizeof t, "%s%s%s", p->p.name, p->p.version && p->p.version[0] ? " " : "", p->p.version ? p->p.version : "");
        wide(t, w, 300);
        p->menu = CreatePopupMenu();
        AppendMenuW(m, MF_POPUP | MF_STRING, (UINT_PTR)p->menu, w);
        int any = 0;
        for (int k = 0; k < g_nit; k++) {
            if (g_it[k].plugin != i) continue;
            if (!strcmp(g_it[k].label, "-")) { AppendMenuW(p->menu, MF_SEPARATOR, 0, NULL); continue; }
            wide(g_it[k].label, w, 300);
            AppendMenuW(p->menu, MF_STRING | (g_it[k].checked ? MF_CHECKED : 0), (UINT_PTR)(MP_FIRST + k), w);
            any = 1;
        }
        if (any) AppendMenuW(p->menu, MF_SEPARATOR, 0, NULL);
        snprintf(t, sizeof t, "From %s", p->file);
        wide(t, w, 300);
        AppendMenuW(p->menu, MF_STRING | MF_GRAYED, 0, w);
        if (p->p.about && p->p.about[0]) AppendMenuW(p->menu, MF_STRING, (UINT_PTR)(MP_ABOUT + i), L"&About...");
    }
    if (!g_npl) AppendMenuW(m, MF_STRING | MF_GRAYED, 0, L"No plugins yet (put .dll files into mods\\plugins)");
    AppendMenuW(m, MF_SEPARATOR, 0, NULL);
    AppendMenuW(m, MF_STRING, MP_FOLDER, L"&Open plugins folder");
    AppendMenuW(m, MF_STRING, MP_HELP, L"&What is this?");
}

/* frontend_sdl.c: an item of the tab was chosen */
void mod_plugins_command(int id) {
    if (id == MP_FOLDER) {
        wchar_t dir[MAX_PATH];
        typedef HINSTANCE (WINAPI* Fn)(HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT);
        HMODULE sh = LoadLibraryW(L"shell32.dll");
        Fn f = sh ? (Fn)(void*)GetProcAddress(sh, "ShellExecuteW") : NULL;
        if (f && mp_folder(dir, MAX_PATH)) { CreateDirectoryW(dir, NULL); f(NULL, L"open", dir, NULL, NULL, SW_SHOWNORMAL); }
        return;
    }
    if (id == MP_HELP) {
        g_cur = -1;
        h_message("Plugins",
            "Plugins change the emulator itself: each one is a .dll file in the mods\\plugins folder, loaded when the game starts. "
            "A plugin can read and change the game's memory, watch and press the buttons, and add its own items to this menu.\n\n"
            "To add one: put its .dll into mods\\plugins (Open plugins folder) and start the game again. "
            "To remove one: delete its .dll. What happened at start is in mods\\plugins\\plugins.log.\n\n"
            "A plugin is a program with all the game's rights: only use plugins you trust.\n\n"
            "While you play with friends, plugins can't change the game (that would put the session out of sync).\n\n"
            "Making one: mods\\plugins\\sdk\\dqix_plugin.h, the plugins in mods\\plugins\\src, and Build plugins.bat.");
        return;
    }
    if (id >= MP_ABOUT && id < MP_ABOUT + g_npl) {
        MpPlugin* p = &g_pl[id - MP_ABOUT];
        h_message(p->p.name, p->p.about);
        return;
    }
    int k = id - MP_FIRST;
    if (k < 0 || k >= g_nit || !g_it[k].click) return;
    g_cur = g_it[k].plugin;
    g_it[k].click(g_it[k].user);
    g_cur = -1;
}

/* mod_cheats.c, every frame: `keys` the buttons this frame (bits 0-11); returns what the game sees */
uint32_t mod_plugins_frame(uint32_t keys) {
    if (!g_loaded && getenv("DQIX_PLUGINS_TEST")) mp_load();
    if (!g_npl || session_running() || session_hidden() || rt_hosted()) return keys;
    for (int i = 0; i < g_npl; i++) {
        if (!g_pl[i].p.on_frame) continue;
        g_cur = i;
        keys = g_pl[i].p.on_frame(keys & DQIX_KEY_ALL) & DQIX_KEY_ALL;
    }
    g_cur = -1;
    return keys;
}
#else
void mod_plugins_menu(void* bar_menu) { (void)bar_menu; }
void mod_plugins_command(int id) { (void)id; }
uint32_t mod_plugins_frame(uint32_t keys) { return keys; }
#endif
