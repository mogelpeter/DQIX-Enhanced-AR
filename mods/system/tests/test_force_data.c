/* Host test for every "Battle any monster you want" launcher: mod_data.c is compiled as it is, the ROM's own encounter
 * tables are read, and for each monster number given every roamer / companion of every zone must carry exactly that
 * monster, with the weights (upper bits) and every other byte of the two tables untouched.
 *   gcc -I <game>/runtime -o t.exe test_force_data.c   (run from anywhere)   t.exe <rom.nds> n [n ...]
 */
#include "../src/runtime/mod_data.c"

uint8_t* g_rom; size_t g_rom_size;
char* rt_getenv(const char* n) { (void)n; return NULL; }   /* the runtime's getenv wrapper: no settings needed here */

static uint8_t* orig[2]; static uint32_t osz[2];


int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: t rom.nds n...\n"); return 2; }
    FILE* f = fopen(argv[1], "rb"); if (!f) { perror("rom"); return 2; }
    fseek(f, 0, SEEK_END); g_rom_size = (size_t)ftell(f); fseek(f, 0, SEEK_SET);
    g_rom = (uint8_t*)malloc(g_rom_size); if (fread(g_rom, 1, g_rom_size, f) != g_rom_size) return 2; fclose(f);
    for (int i = 0; i < 2; i++) {
        uint32_t s, z; if (!lookup(g_f[i].name, &s, &z)) { printf("FAIL: %s not in the ROM\n", g_f[i].name); return 1; }
        orig[i] = (uint8_t*)malloc(z); memcpy(orig[i], g_rom + s, z); osz[i] = z;
    }
    int fails = 0;
    for (int a = 2; a < argc; a++) {
        int n = atoi(argv[a]);
        build(0x10000u | (uint32_t)n);
        if (g_ready != 1) { printf("FAIL n=%d: build failed\n", n); fails++; continue; }
        int bad = 0, changed_words = 0, roamers = 0;
        for (int i = 0; i < 2; i++) {
            if (g_f[i].size != osz[i]) { printf("FAIL n=%d: size of %s changed\n", n, g_f[i].name); bad++; continue; }
            /* every byte that differs must be inside the low 12 bits of a word that holds monster n now */
            for (uint32_t p = 0; p + 4 <= osz[i]; p += 4) {
                uint32_t o = rd32(orig[i] + p), w = rd32(g_f[i].data + p);
                if (o == w) continue;
                changed_words++;
                if ((o & ~0xFFFu) != (w & ~0xFFFu) || (w & 0xFFF) != (uint32_t)n) { bad++; if (bad < 4) printf("  n=%d %s @%u: %08x -> %08x\n", n, g_f[i].name, p, o, w); }
            }
        }
        /* and every roamer slot of the tables is monster n: walk the records again like the patcher does */
        Zone z1; memset(&z1, 0, sizeof z1); z1.roam_tag = 0x67; z1.comp_tag = -1; z1.force = 0;
        for (int i = 0; i < 2; i++) {
            const uint8_t* b = g_f[i].data; uint32_t size = g_f[i].size, stab = rd32(b + 4), p = 16;
            if (stab > size) stab = size;
            int roam_tag = i == 0 ? 0x67 : 0x66;
            while (p + 4 <= stab) {
                if (rd32(b + p) == 0xFFFFFFFFu) { p += 4; continue; }
                uint16_t tag = (uint16_t)(b[p] | b[p + 1] << 8); int cnt = b[p + 2];
                uint32_t tb = (uint32_t)(cnt * 2 + 7) / 8, hdr = ((3 + tb + 3) / 4) * 4;
                if (p + hdr + 4u * (uint32_t)cnt > stab) break;
                if (cnt >= 1 && tag == roam_tag) { roamers++; if ((rd32(b + p + hdr) & 0xFFF) != (uint32_t)n) { bad++; } }
                p += hdr + 4u * (uint32_t)cnt;
            }
        }
        if (!roamers) { printf("FAIL n=%d: no roamer slots found\n", n); bad++; }
        if (!changed_words && n > 0) { printf("FAIL n=%d: nothing changed\n", n); bad++; }
        if (bad) fails++;
        else if (a == 2 || a == argc - 1) printf("ok n=%d: %d words changed, %d roamer slots all monster %d\n", n, changed_words, roamers, n);
    }
    printf("%d numbers checked, %d failed\n", argc - 2, fails);
    return fails ? 1 : 0;
}
