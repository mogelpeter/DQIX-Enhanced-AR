/* The "Cheats" tab of the window's menu (put into runtime/ by mods/system/tools/apply_runtime_mod.py).
 * "Cheats enabled..." closes the game and opens the cheat menu (mods\Play with mods.bat); its Play
 * button builds the mods in if needed and starts the game again. */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

const char* update_project_dir(void);                 /* update.c: the folder with BUILD.bat, or NULL */

static int play_bat(wchar_t* out, size_t n) {
    const char* root = update_project_dir();
    wchar_t w[MAX_PATH];
    if (!root || !MultiByteToWideChar(CP_UTF8, 0, root, -1, w, MAX_PATH)) return 0;
    swprintf(out, n, L"%ls\\mods\\Play with mods.bat", w);
    return GetFileAttributesW(out) != INVALID_FILE_ATTRIBUTES;
}

int mod_menu_available(void) { wchar_t p[MAX_PATH + 64]; return play_bat(p, MAX_PATH + 64); }

/* start the cheat menu (a window of its own); 1 if it was started */
int mod_menu_launch(void) {
    wchar_t bat[MAX_PATH + 64], cmd[MAX_PATH + 128], dir[MAX_PATH + 64];
    if (!play_bat(bat, MAX_PATH + 64)) return 0;
    wcsncpy(dir, bat, MAX_PATH + 63); dir[MAX_PATH + 63] = 0;
    wchar_t* s = wcsrchr(dir, L'\\'); if (s) *s = 0;      /* ...\mods */
    s = wcsrchr(dir, L'\\'); if (s) *s = 0;               /* the project folder */
    swprintf(cmd, MAX_PATH + 128, L"cmd.exe /c \"\"%ls\"\"", bat);
    STARTUPINFOW si; memset(&si, 0, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NEW_CONSOLE, NULL, dir, &si, &pi)) return 0;
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 1;
}

/* the save editor: the cheat menu program in its "--editor <tab>" mode serves the editor and opens it in the browser;
 * the game keeps running (the editor refuses to export while it does). 1 if it was started */
int mod_editor_launch(const char* tab) {
    const char* root = update_project_dir();
    wchar_t w[MAX_PATH], cmd[MAX_PATH * 2 + 128], exe[MAX_PATH + 64], wtab[64];
    if (!root || !MultiByteToWideChar(CP_UTF8, 0, root, -1, w, MAX_PATH) || !MultiByteToWideChar(CP_UTF8, 0, tab, -1, wtab, 64)) return 0;
    swprintf(exe, MAX_PATH + 64, L"%ls\\mods\\system\\bin\\dqix-cheat-menu.exe", w);
    if (GetFileAttributesW(exe) == INVALID_FILE_ATTRIBUTES) return 0;
    swprintf(cmd, MAX_PATH * 2 + 128, L"\"%ls\" \"%ls\" --editor %ls", exe, w, wtab);
    STARTUPINFOW si; memset(&si, 0, sizeof si); si.cb = sizeof si;
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, 0, NULL, w, &si, &pi)) return 0;
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 1;
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
int mod_menu_available(void) { return 0; }
int mod_editor_launch(const char* tab) { (void)tab; return 0; }
int mod_open_url(const char* url) { (void)url; return 0; }
int mod_menu_launch(void) { return 0; }
#endif
