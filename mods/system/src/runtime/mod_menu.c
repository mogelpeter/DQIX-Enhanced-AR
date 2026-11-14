/* The "Cheats" tab of the window's menu (put into runtime/ by mods/system/tools/apply_runtime_mod.py): what "Save editor..."
 * and the web pages do. (The cheat list itself is mod_cheatwin.c.) */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <stdint.h>

const char* update_project_dir(void);                 /* update.c: the folder with BUILD.bat, or NULL */

/* the save editor: its helper (mods\system\bin\dqix-editor.exe, no window) serves the editor and opens it in the browser;
 * the game keeps running. Export in the editor hands the save to the game (mod_editor_take below). 1 if it was started */
int mod_editor_launch(const char* tab) {
    const char* root = update_project_dir();
    wchar_t w[MAX_PATH], cmd[MAX_PATH * 2 + 128], exe[MAX_PATH + 64], wtab[64];
    if (!root || !MultiByteToWideChar(CP_UTF8, 0, root, -1, w, MAX_PATH) || !MultiByteToWideChar(CP_UTF8, 0, tab, -1, wtab, 64)) return 0;
    swprintf(exe, MAX_PATH + 64, L"%ls\\mods\\system\\bin\\dqix-editor.exe", w);
    if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES) return 0;
    swprintf(cmd, MAX_PATH * 2 + 128, L"\"%ls\" \"%ls\" --editor %ls", exe, w, wtab);
    STARTUPINFOW si; memset(&si, 0, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, w, &si, &pi)) return 0;
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 1;
}

/* Export in the editor while the game runs: the helper puts the edited save in mods\system\bin\editor-export.sav (and the
 * save it handed the editor in editor-loaded.sav), then sends the game's window the menu command 364 (frontend_sdl.c). The
 * game takes the files here (they are gone afterwards) and answers in editor-export.txt: ok, cancel, session, bad, nobackup. */
static int editor_file(const wchar_t* name, wchar_t* out) {
    const char* root = update_project_dir();
    wchar_t w[MAX_PATH];
    if (!root || !MultiByteToWideChar(CP_UTF8, 0, root, -1, w, MAX_PATH)) return 0;
    swprintf(out, MAX_PATH + 64, L"%ls\\mods\\system\\bin\\%ls", w, name);
    return 1;
}
static uint32_t editor_read(const wchar_t* name, uint8_t* buf) {
    wchar_t p[MAX_PATH + 64];
    if (!editor_file(name, p)) return 0;
    FILE* f = _wfopen(p, L"rb");
    if (!f) return 0;
    size_t n = fread(buf, 1, 0x10000, f);
    fclose(f);
    DeleteFileW(p);
    return (uint32_t)n;
}
int mod_editor_take(uint8_t* ed, uint32_t* en, uint8_t* base, uint32_t* bn) {
    *en = editor_read(L"editor-export.sav", ed);
    *bn = editor_read(L"editor-loaded.sav", base);
    return *en != 0;
}
void mod_editor_result(const char* r) {
    wchar_t p[MAX_PATH + 64];
    if (!editor_file(L"editor-export.txt", p)) return;
    FILE* f = _wfopen(p, L"wb");
    if (f) { fputs(r, f); fclose(f); }
}

/* a web page in the browser */
int mod_open_url(const char* url) {
    wchar_t w[512];
    if (!MultiByteToWideChar(CP_UTF8, 0, url, -1, w, 512)) return 0;
    typedef HINSTANCE (WINAPI* Fn)(HWND, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, INT);
    HMODULE sh = LoadLibraryW(L"shell32.dll");
    Fn f = sh ? (Fn)GetProcAddress(sh, "ShellExecuteW") : NULL;
    return f && (INT_PTR)f(NULL, L"open", w, NULL, NULL, SW_SHOWNORMAL) > 32;
}
#else
#include <stdint.h>
int mod_editor_launch(const char* tab) { (void)tab; return 0; }
int mod_editor_take(uint8_t* ed, uint32_t* en, uint8_t* base, uint32_t* bn) { (void)ed; (void)base; *en = *bn = 0; return 0; }
void mod_editor_result(const char* r) { (void)r; }
int mod_open_url(const char* url) { (void)url; return 0; }
#endif
