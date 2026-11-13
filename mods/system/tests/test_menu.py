"""The menu itself against a headless game: is what is switched on in the menu carried out in the game?
   test_menu.py <project root> <work dir> <inside|outside>"""
import os, shutil, subprocess, sys, time

root, work, how = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]), sys.argv[3]
frames = 3000
os.makedirs(work, exist_ok=True)
for f in os.listdir(work):
    if f.endswith(".bin") or f.endswith(".log") or f.endswith(".png"):
        os.remove(os.path.join(work, f))
shutil.copy(os.path.join(root, "game", "dqix.sav"), os.path.join(work, "test.sav"))
env = dict(os.environ)
env.pop("NoDefaultCurrentDirectoryInExePath", None)
env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_CHEATWIN_OFF="1", DQIX_NO_SETTINGS="1", DQIX_RAMDUMP=f".,{frames - 20}")
log = open(os.path.join(work, "run.log"), "wb")
game = subprocess.Popen([os.path.join(root, "game", "dqix.exe"), os.path.join(root, "game", "data", "dqix.nds"),
                         os.path.join(root, "game", "data", "code"), str(frames), "1", "test.sav"], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
menv = dict(os.environ)
state = os.path.join(work, "menu-state.txt")
open(state, "w", encoding="utf-8").write("live file:cheats/max-bank.txt\nlive file:cheats/max-gold.txt\n")
menv["DQIX_MENU_STATE"] = state          # never the user's own menu-state.txt
if how == "outside":
    menv["DQIX_CHEATS_OUTSIDE"] = "1"
time.sleep(4)
shot = os.path.join(work, "menu.png")
menu = subprocess.Popen([os.path.join(root, "mods", "system", "bin", "dqix-cheat-menu.exe"), root, "--shot", shot, "on", "90"], env=menv)
game.wait(timeout=600)
menu.wait(timeout=200)
log.close()
print("game exit", game.returncode, "menu exit", menu.returncode)
with open(os.path.join(work, f"ram{frames - 20:06d}.bin"), "rb") as f:
    f.seek(0xF6D44)
    bank = int.from_bytes(f.read(4), "little"); gold = int.from_bytes(f.read(4), "little")
print("bank", bank, "gold", gold)
print("RESULT:", "PASS" if game.returncode == 0 and bank == 9999999 and gold == 9999999 else "FAIL")
