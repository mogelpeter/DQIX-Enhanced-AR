/* DQIX Enhanced plugins: the whole interface between the game and a plugin.
 *
 * A plugin is a Windows DLL in the game's mods\plugins folder. The game loads every *.dll there when it starts and
 * lists it in the menu bar under Plugins. The DLL exports one function:
 *
 *     __declspec(dllexport) int dqix_plugin_init(const DqixHost* host, DqixPlugin* me);
 *
 * It fills `me` (at least me->name), may add menu items with host->menu_item, keeps `host` for later and returns 1.
 * Returning 0 means "don't load me" (the DLL is unloaded again).
 *
 * Every callback runs on the game's own thread, between two frames: keep it short, or the game stutters.
 * A plugin is native code with the game's rights: only put in DLLs you trust.
 *
 * Playing with friends: while a session runs, on_frame is not called and host->write refuses, because a change
 * on one PC alone makes the session go out of sync. Menu items still work (read-only things are fine).
 *
 * Build (MSYS2 UCRT64, the compiler the game is built with; any 64-bit Windows C compiler works):
 *     gcc -shared -O2 -o myplugin.dll myplugin.c
 * "mods\plugins\Build plugins.bat" builds every mods\plugins\src\<name>\ that way into mods\plugins\<name>.dll.
 */
#ifndef DQIX_PLUGIN_H
#define DQIX_PLUGIN_H
#include <stdint.h>

#define DQIX_PLUGIN_API 1                     /* goes up when something is added; old plugins keep working */

/* Buttons: the bits of `keys` in on_frame (bit set = pressed) */
enum {
    DQIX_KEY_A = 1 << 0, DQIX_KEY_B = 1 << 1, DQIX_KEY_SELECT = 1 << 2, DQIX_KEY_START = 1 << 3,
    DQIX_KEY_RIGHT = 1 << 4, DQIX_KEY_LEFT = 1 << 5, DQIX_KEY_UP = 1 << 6, DQIX_KEY_DOWN = 1 << 7,
    DQIX_KEY_R = 1 << 8, DQIX_KEY_L = 1 << 9, DQIX_KEY_X = 1 << 10, DQIX_KEY_Y = 1 << 11,
    DQIX_KEY_ALL = 0x0FFF
};

typedef struct DqixHost {
    uint32_t api;                             /* DQIX_PLUGIN_API of the game */
    /* The DS's main RAM (0x02000000-0x023FFFFF, the addresses of Action Replay codes). 1 = done, 0 = outside RAM
     * (or, for write, refused because a session runs). */
    int (*read)(uint32_t addr, void* out, uint32_t n);
    int (*write)(uint32_t addr, const void* in, uint32_t n);
    /* A line in mods\plugins\plugins.log (and on the console). */
    void (*log)(const char* text);
    /* A message box over the game (it waits until closed). */
    void (*message)(const char* title, const char* text);
    /* Only inside dqix_plugin_init: one more entry in this plugin's menu (label: UTF-8, "-" = a separator line).
     * on_click(user) runs when it is chosen. Returns the item's number for menu_check, or -1 (no room left). */
    int (*menu_item)(const char* label, void (*on_click)(void* user), void* user);
    /* A check mark at an item (number from menu_item). */
    void (*menu_check)(int item, int on);
    /* The frames shown since the game started (60 a second). */
    uint64_t (*frame)(void);
    /* The game folder (UTF-8, the one with BUILD.bat). */
    const char* (*game_dir)(void);
    /* 1 while playing with friends (see above). */
    int (*in_session)(void);
} DqixHost;

typedef struct DqixPlugin {
    const char* name;                         /* shown in the Plugins menu (UTF-8) */
    const char* version;                      /* optional, e.g. "1.0" */
    const char* about;                        /* optional: the text of the plugin's "About" item */
    /* optional: every frame, before the game sees the buttons. Return the buttons the game should see
     * (return keys unchanged to only watch). Not called while a session runs. */
    uint32_t (*on_frame)(uint32_t keys);
    /* optional: the game is closing */
    void (*on_exit)(void);
} DqixPlugin;

typedef int (*DqixPluginInit)(const DqixHost* host, DqixPlugin* me);

#endif
