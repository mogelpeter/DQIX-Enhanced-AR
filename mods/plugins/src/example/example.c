/* An example plugin ("mods\plugins\Build plugins.bat" makes mods\plugins\example.dll from it).
 *
 *   Plugins > Example > Turbo A      while on, holding A presses it on and off by itself (fast talking, menus)
 *   Plugins > Example > Show gold    reads the party's gold from the game's RAM
 */
#include <stdio.h>
#include <stdlib.h>
#include "dqix_plugin.h"                      /* mods/plugins/sdk */

static const DqixHost* host;
static int turbo, turbo_item;

#define GOLD 0x020F6D48u                      /* the party's gold, 32 bits (US/EU) */

static void toggle_turbo(void* user) {
    (void)user;
    turbo = !turbo;
    host->menu_check(turbo_item, turbo);
    host->log(turbo ? "turbo A on" : "turbo A off");
}

static void show_gold(void* user) {
    uint32_t g = 0;
    char t[80];
    (void)user;
    if (host->read(GOLD, &g, 4)) snprintf(t, sizeof t, "The party has %u gold.", (unsigned)g);
    else snprintf(t, sizeof t, "The gold couldn't be read.");
    host->message("Example plugin", t);
}

static uint32_t on_frame(uint32_t keys) {
    static int test = -1;
    if (test < 0) test = getenv("DQIX_PLUGIN_EXAMPLE_TEST") != NULL;
    if (test && host->frame() >= 600) {       /* the test (mods/system/tests/test_plugins.py) looks for this word */
        uint32_t mark = 0x504C5547u;          /* "PLUG" */
        host->write(0x02340000u, &mark, 4);
    }
    if (turbo && (keys & DQIX_KEY_A) && (host->frame() & 2)) keys &= ~(uint32_t)DQIX_KEY_A;   /* A: 2 frames down, 2 up */
    return keys;
}

__declspec(dllexport) int dqix_plugin_init(const DqixHost* h, DqixPlugin* me) {
    if (h->api < 1) return 0;
    host = h;
    me->name = "Example";
    me->version = "1.0";
    me->about = "The example plugin (mods\\plugins\\src\\example).\n\nTurbo A: while on, holding A presses it again and again.\nShow gold: the party's gold, read from the game's memory.";
    me->on_frame = on_frame;
    turbo_item = h->menu_item("&Turbo A", toggle_turbo, NULL);
    h->menu_item("Show &gold", show_gold, NULL);
    if (getenv("DQIX_PLUGIN_EXAMPLE_TEST")) { turbo = 1; h->menu_check(turbo_item, 1); }
    h->log("ready");
    return 1;
}
