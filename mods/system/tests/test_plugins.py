"""Plugins (mod_plugins.c, menu bar: Plugins), headless game, Windows only.
   test_plugins.py <project root> <work dir> [frame]

   Builds the plugins (mods/plugins/src: example, performance) into a folder of its own (DQIX_PLUGINS_DIR) next to a DLL that
   is no plugin, then runs the game headless with DQIX_PLUGINS_TEST (loads them without a menu):
     - plugins.log: both are loaded, the other DLL is refused with a reason
     - performance: Windows took all three switches, and at exit it wrote its frame-time summary
     - the example's on_frame ran: it wrote "PLUG" to 0x02340000 (unused RAM) from frame 600 on
   Needs the game built with the mods (mod_plugins.c in runtime/) and gcc from MSYS2 (msys2-root.txt). TEST_EXE / TEST_SAVE as in the other tests."""
import os, shutil, subprocess, sys

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAME = int(sys.argv[3]) if len(sys.argv) > 3 else 700
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE", os.path.join(root, "game", "dqix.sav"))
MARK_AT, MARK = 0x02340000 - 0x02000000, 0x504C5547
shutil.rmtree(work, ignore_errors=True)
plugins = os.path.join(work, "plugins")
os.makedirs(plugins)

msys = r"C:\msys64"
try:
    msys = open(os.path.join(root, "mods", "system", "msys2-root.txt"), encoding="utf-8").read().strip() or msys
except OSError:
    pass
gcc = next((p for p in (os.path.join(msys, d, "bin", "gcc.exe") for d in ("ucrt64", "mingw64")) if os.path.isfile(p)), None)
if not gcc:
    print("RESULT: FAIL\nno gcc in", msys); sys.exit(1)
env = dict(os.environ); env["PATH"] = os.path.dirname(gcc) + os.pathsep + env["PATH"]
sdk = os.path.join(root, "mods", "plugins", "sdk")
src = os.path.join(root, "mods", "plugins", "src")
open(os.path.join(work, "noplugin.c"), "w").write("__declspec(dllexport) int something(void) { return 1; }\n")
for c, dll in ((os.path.join(src, "example", "example.c"), "example.dll"), (os.path.join(src, "performance", "performance.c"), "performance.dll"),
               (os.path.join(work, "noplugin.c"), "noplugin.dll")):
    r = subprocess.run([gcc, "-shared", "-O2", "-static-libgcc", "-I" + sdk, "-o", os.path.join(plugins, dll), c], env=env, capture_output=True, text=True)
    if r.returncode:
        print("RESULT: FAIL\nbuilding", dll, r.stderr); sys.exit(1)

d = os.path.join(work, "run"); os.makedirs(d)
shutil.copy(save, os.path.join(d, "test.sav"))
env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1", DQIX_CHEATWIN_OFF="1",
           DQIX_MENU_STATE=os.path.join(d, "state.txt"), DQIX_RAMDUMP=".,%d" % FRAME,
           DQIX_PLUGINS_TEST="1", DQIX_PLUGINS_DIR=plugins, DQIX_PLUGIN_EXAMPLE_TEST="1")
with open(os.path.join(d, "run.log"), "wb") as log:
    p = subprocess.run([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAME + 30), "1", "test.sav"],
                       cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
plog = open(os.path.join(plugins, "plugins.log"), encoding="utf-8").read() if os.path.isfile(os.path.join(plugins, "plugins.log")) else ""
ram = open(os.path.join(d, "ram%06d.bin" % FRAME), "rb").read() if os.path.isfile(os.path.join(d, "ram%06d.bin" % FRAME)) else b""
mark = int.from_bytes(ram[MARK_AT:MARK_AT + 4], "little") if ram else 0
loaded = "loaded Example from example.dll" in plog and "Example: ready" in plog
perf = "loaded Performance from performance.dll" in plog and all("Performance: %s on\n" % k in plog for k in ("priority", "no_throttling", "mmcss"))
perf_exit = "Performance: Frames measured:" in plog
refused = "noplugin.dll: not loaded (no dqix_plugin_init)" in plog
print("plugins.log:\n  " + "\n  ".join(plog.strip().splitlines()))
print("example loaded:", loaded, "| other DLL refused:", refused, "| performance switches on:", perf, "| its summary at exit:", perf_exit, "| on_frame wrote RAM: %#x" % mark, "| exit", p.returncode)
ok = p.returncode == 0 and loaded and refused and perf and perf_exit and mark == MARK
print("RESULT: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
