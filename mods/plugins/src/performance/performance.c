/* Performance plugin: makes Windows run the game smoothly ("mods\plugins\Build plugins.bat" -> mods\plugins\performance.dll).
 *
 * The game is one thread that has to finish a frame every 16.7 ms. It does not need more speed than a PC has; what
 * makes it stutter is Windows giving that thread less than it needs at the wrong moment. Three switches, all on at first:
 *
 *   Higher priority             the game's process gets "above normal" priority, so background work (updates,
 *                               indexing, the browser) waits for it instead of the other way round. Not "high":
 *                               that can starve the sound and input of other programs.
 *   No power throttling         Windows 11 slows down programs it thinks are in the background (EcoQoS: slower cores,
 *                               lower clock) and ignores their 1 ms timer when the window is covered or on another
 *                               screen. The game opts out of both (also in sessions, where it often isn't in front).
 *   Game thread scheduling      the game's thread joins the "Games" class of the Multimedia Class Scheduler (MMCSS),
 *                               as games and audio programs do: it gets the CPU on time even when the PC is busy.
 *
 *   Frame times...              how evenly the frames came since the last reset: average, slowest 1 %, late frames.
 *                               Lets you see what the switches do on your PC (switch, reset, play a minute, look).
 *
 * The switches don't touch the game itself (same frames, same RAM), so they are fine while playing with friends.
 * They are kept in performance.ini next to the DLL.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dqix_plugin.h"                      /* mods/plugins/sdk */

static const DqixHost* host;

enum { S_PRIORITY, S_THROTTLE, S_MMCSS, S_N };
static const char* const KEY[S_N] = { "priority", "no_throttling", "mmcss" };
static const char* const LABEL[S_N] = { "Higher &priority", "No power &throttling", "Game thread &scheduling (MMCSS)" };
static int on[S_N] = { 1, 1, 1 }, item[S_N], applied[S_N];
static wchar_t ini[MAX_PATH];

/* ---- the switches ---- */

/* the Windows 8+ / 11 call, looked up so the plugin also loads on older Windows */
typedef struct { ULONG Version, ControlMask, StateMask; } PowerThrottling;
#define PT_EXECUTION_SPEED 0x1
#define PT_IGNORE_TIMER    0x4                /* Windows 11: keep the 1 ms timer when the window isn't visible */
static int set_throttling(int off) {
    typedef BOOL (WINAPI* Fn)(HANDLE, int, LPVOID, DWORD);
    Fn f = (Fn)(void*)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "SetProcessInformation");
    if (!f) return 0;
    PowerThrottling s = { 1, 0, 0 };
    if (off) s.ControlMask = PT_EXECUTION_SPEED | PT_IGNORE_TIMER;    /* control them, state 0 = never throttle */
    if (f(GetCurrentProcess(), 4 /* ProcessPowerThrottling */, &s, sizeof s)) return 1;
    s.ControlMask &= ~(ULONG)PT_IGNORE_TIMER;                         /* Windows 10 doesn't know the timer flag */
    return f(GetCurrentProcess(), 4, &s, sizeof s) != 0;
}

static HANDLE mm_task; static DWORD mm_thread;
static int set_mmcss(int want) {
    static HMODULE avrt;
    typedef HANDLE (WINAPI* SetFn)(LPCWSTR, LPDWORD);
    typedef BOOL (WINAPI* RevFn)(HANDLE);
    if (!avrt) avrt = LoadLibraryW(L"avrt.dll");
    if (!avrt) return 0;
    SetFn set = (SetFn)(void*)GetProcAddress(avrt, "AvSetMmThreadCharacteristicsW");
    RevFn rev = (RevFn)(void*)GetProcAddress(avrt, "AvRevertMmThreadCharacteristics");
    if (mm_task && rev) { rev(mm_task); mm_task = NULL; }
    if (!want) return 1;
    DWORD idx = 0;
    if (set) mm_task = set(L"Games", &idx);
    mm_thread = GetCurrentThreadId();
    return mm_task != NULL;
}

static void apply(int s, int quiet) {
    int ok = 0;
    switch (s) {
    case S_PRIORITY: ok = SetPriorityClass(GetCurrentProcess(), on[s] ? ABOVE_NORMAL_PRIORITY_CLASS : NORMAL_PRIORITY_CLASS) != 0; break;
    case S_THROTTLE: ok = set_throttling(on[s]); break;
    case S_MMCSS:    ok = set_mmcss(on[s]); break;
    }
    applied[s] = on[s] && ok;
    char t[160];
    snprintf(t, sizeof t, "%s %s%s", KEY[s], on[s] ? "on" : "off", ok ? "" : " (Windows refused)");
    host->log(t);
    if (!ok && on[s] && !quiet) host->message("Performance", "Windows did not allow this switch here (see mods\\plugins\\plugins.log).");
}

static void load_ini(void) {
    for (int s = 0; s < S_N; s++) {
        wchar_t k[32]; MultiByteToWideChar(CP_UTF8, 0, KEY[s], -1, k, 32);
        on[s] = GetPrivateProfileIntW(L"performance", k, 1, ini) != 0;
    }
}
static void save_ini(void) {
    for (int s = 0; s < S_N; s++) {
        wchar_t k[32]; MultiByteToWideChar(CP_UTF8, 0, KEY[s], -1, k, 32);
        WritePrivateProfileStringW(L"performance", k, on[s] ? L"1" : L"0", ini);
    }
}

static void toggle(void* user) {
    int s = (int)(intptr_t)user;
    on[s] = !on[s];
    apply(s, 0);
    host->menu_check(item[s], on[s]);
    save_ini();
}

/* ---- frame times ---- */

#define BINS 400                              /* 0.25 ms each: 0-100 ms */
static LARGE_INTEGER freq, last;
static unsigned long long n, hist[BINS + 1];
static double sum, worst;
static unsigned long long late, dropped;      /* > 20 ms (a frame shown twice is near), > 33.4 ms (one skipped) */

static void reset(void* user) {
    (void)user;
    n = late = dropped = 0; sum = worst = 0; last.QuadPart = 0;
    memset(hist, 0, sizeof hist);
    host->log("frame times reset");
}

static uint32_t on_frame(uint32_t keys) {
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    if (on[S_MMCSS] && mm_thread != GetCurrentThreadId()) set_mmcss(1);    /* the frames run on another thread than init */
    if (last.QuadPart) {
        double ms = (double)(now.QuadPart - last.QuadPart) * 1000.0 / (double)freq.QuadPart;
        if (ms < 500) {                       /* longer: paused, a menu or a box was open - not a frame time */
            n++; sum += ms;
            if (ms > worst) worst = ms;
            if (ms > 20.0) late++;
            if (ms > 33.4) dropped++;
            int b = (int)(ms * 4); hist[b < BINS ? b : BINS]++;
        }
    }
    last = now;
    return keys;
}

static double slowest_1pct(void) {           /* the frame time that 99 % of the frames beat */
    unsigned long long want = n / 100, seen = 0;
    for (int b = BINS; b >= 0; b--) { seen += hist[b]; if (seen > want) return (b + 1) / 4.0; }
    return 0;
}

static void summary(char* t, size_t sz) {
    if (n < 30) { snprintf(t, sz, "Not enough frames measured yet (play a little, then look again).\n\nFrames are not measured while playing with friends."); return; }
    double avg = sum / (double)n;
    snprintf(t, sz,
        "Frames measured: %llu (%.0f s)\n"
        "Average: %.2f ms (%.1f frames a second; the DS shows 59.8)\n"
        "Slowest 1%%: %.2f ms or less\n"
        "Slowest frame: %.1f ms\n"
        "Late (over 20 ms): %llu (%.2f%%)\n"
        "Skipped a frame (over 33 ms): %llu\n\n"
        "Now: priority %s, power throttling %s, MMCSS %s.\n"
        "Compare: switch one, Reset frame times, play a minute the same way, look again.",
        n, sum / 1000.0, avg, 1000.0 / avg, slowest_1pct(), worst, late, 100.0 * (double)late / (double)n, dropped,
        applied[S_PRIORITY] ? "above normal" : "normal", applied[S_THROTTLE] ? "off" : "as Windows likes",
        applied[S_MMCSS] ? "Games" : "off");
}

static void report(void* user) {
    char t[900]; (void)user;
    summary(t, sizeof t);
    host->message("Frame times", t);
}

static void on_exit(void) {
    char t[900], *p;
    summary(t, sizeof t);
    for (p = t; *p; p++) if (*p == '\n') *p = ' ';
    host->log(t);
    if (mm_task) set_mmcss(0);
}

__declspec(dllexport) int dqix_plugin_init(const DqixHost* h, DqixPlugin* me) {
    if (h->api < 1) return 0;
    host = h;
    QueryPerformanceFrequency(&freq);
    HMODULE self = NULL;                      /* performance.ini next to this DLL */
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)(void*)&dqix_plugin_init, &self);
    GetModuleFileNameW(self, ini, MAX_PATH);
    wchar_t* dot = wcsrchr(ini, L'.');
    if (dot) wcscpy(dot, L".ini");
    load_ini();
    if (getenv("DQIX_PERF_OFF")) for (int s = 0; s < S_N; s++) on[s] = 0;   /* measuring without the switches */

    me->name = "Performance";
    me->version = "1.0";
    me->about =
        "Makes Windows run the game smoothly. The game needs little, but on time every 16.7 ms; stutter comes from Windows "
        "giving it less at the wrong moment.\n\n"
        "Higher priority: background programs wait for the game.\n"
        "No power throttling: Windows 11 doesn't slow the game down when its window isn't in front.\n"
        "Game thread scheduling (MMCSS): the game's thread is scheduled like a game or an audio program.\n\n"
        "Frame times... shows how evenly the frames come, to compare with a switch on and off.\n\n"
        "None of this changes the game itself, so it is fine while playing with friends.";
    me->on_frame = on_frame;
    me->on_exit = on_exit;
    for (int s = 0; s < S_N; s++) {
        item[s] = h->menu_item(LABEL[s], toggle, (void*)(intptr_t)s);
        h->menu_check(item[s], on[s]);
        apply(s, 1);
    }
    h->menu_item("-", NULL, NULL);
    h->menu_item("&Frame times...", report, NULL);
    h->menu_item("&Reset frame times", reset, NULL);
    return 1;
}
