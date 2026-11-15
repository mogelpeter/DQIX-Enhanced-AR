"""The update notice inside the game (mod_cheatwin.c, upd_thread), headless game, Windows only.
   test_update_notice.py <project root> <work dir> [frames]

   A small local server plays GitHub (DQIX_AR_UPDATE_HOST, answers {"tag_name": "v9.9.9"}), DQIX_AR_UPDATE_TEST=1 makes the game print
   "update: ..." instead of asking. Checked:
     1  installed 1.0.0, newest 9.9.9, not turned down  -> "update: v9.9.9 is available (installed 1.0.0)"
     2  the same, but update-declined.txt says v9.9.9      -> nothing
     3  installed 9.9.9 (up to date)                       -> nothing
     4  no version.txt (a development folder)              -> nothing
   mods\\system\\version.txt and update-declined.txt of the project are put back afterwards."""
import http.server, json, os, shutil, subprocess, sys, threading

root, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
FRAMES = int(sys.argv[3]) if len(sys.argv) > 3 else 240
exe = os.environ.get("TEST_EXE", os.path.join(root, "game", "dqix.exe"))
save = os.environ.get("TEST_SAVE", os.path.join(root, "game", "dqix.sav"))
sysdir = os.path.join(root, "mods", "system")
VER, NO = os.path.join(sysdir, "version.txt"), os.path.join(sysdir, "update-declined.txt")
os.makedirs(work, exist_ok=True)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"tag_name": "v9.9.9", "assets": []}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, format, *args):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]


def keep(p):
    return open(p, "rb").read() if os.path.exists(p) else None


def put(p, data):
    if data is None:
        if os.path.exists(p): os.remove(p)
    else:
        open(p, "wb").write(data)


def run(tag, ver, declined):
    put(VER, None if ver is None else (ver + "\r\n").encode()); put(NO, None if declined is None else (declined + "\r\n").encode())
    d = os.path.join(work, tag)
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    shutil.copy(save, os.path.join(d, "test.sav"))
    env = dict(os.environ); env.pop("NoDefaultCurrentDirectoryInExePath", None)
    env.update(DQIX_NOWINDOW="1", SDL_AUDIODRIVER="dummy", DQIX_NO_SETTINGS="1", DQIX_NO_UPNP="1", DQIX_NO_RELAY="1",
               DQIX_AR_UPDATE_TEST="1", DQIX_AR_UPDATE_HOST="127.0.0.1:%d" % port)
    p = subprocess.run([exe, os.path.join(root, "game", "data", "dqix.nds"), os.path.join(root, "game", "data", "code"), str(FRAMES), "1", "test.sav"],
                       cwd=d, env=env, capture_output=True, timeout=900)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


old_ver, old_no = keep(VER), keep(NO)
ok = True
try:
    rc, t = run("a", "1.0.0", None)
    s1 = "update: v9.9.9 is available (installed 1.0.0)" in t
    print("1  newer release found:", s1, "| exit", rc, flush=True); ok &= s1 and rc == 0
    rc, t = run("b", "1.0.0", "v9.9.9")
    print("2  turned down before, not announced:", "update:" not in t, flush=True); ok &= "update:" not in t
    rc, t = run("c", "9.9.9", None)
    print("3  up to date, not announced:", "update:" not in t, flush=True); ok &= "update:" not in t
    rc, t = run("d", None, None)
    print("4  no version.txt, not announced:", "update:" not in t, flush=True); ok &= "update:" not in t
finally:
    put(VER, old_ver); put(NO, old_no); srv.shutdown()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
