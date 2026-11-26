/* DQIX Enhanced: the save editor's helper (no window).
 *
 *   dqix-editor.exe <DQIX Enhanced folder> [--editor <tab>]
 *
 * Started by the game's menu bar (Cheats > Save editor...). It serves the DQIX project's browser editor
 * (https://github.com/dqix/editor) on 127.0.0.1, hands it your game save, writes the exported save back (after a copy
 * into mods\system\save-backups), and opens the page in your browser. The language of the page is chosen in the page
 * itself (box at the top right). It leaves by itself when the page has been closed for a few minutes.
 *
 * Built by "Apply.bat" with the C# compiler that comes with Windows (.NET Framework 4): C# 5, no newer syntax.
 */
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace DqixEditor
{
    static class Tr
    {
        public static readonly string[] Codes = { "en", "de", "fr", "es", "it" };
    }

    /* ---- the save editor and treasure map tabs: the DQIX project's browser editor (https://github.com/dqix/editor),
     * fetched from dqix.github.io on first use into mods\system\bin\editor-cache and served from here to the browser. Nothing of it is
     * part of this repo. The host also hands the editor your game save and writes the exported one back (after a backup). ---- */
    class EditorHost : IDisposable
    {
        const string Origin = "https://dqix.github.io";
        readonly string cache, savePath, backupDir;
        readonly Func<bool> gameRunning;
        HttpListener http;
        public int Port;
        public string LastError = "";
        public DateTime LastSeen = DateTime.UtcNow;
        public Action<string> SetLang;                 /* the language box of the page */
        readonly string token = Guid.NewGuid().ToString("N");

        const string Inject = @"<script>(function(){var T='@T@',lastBlob=null,oc=URL.createObjectURL;
URL.createObjectURL=function(b){lastBlob=b;return oc.call(URL,b);};
function note(t,bad){var d=document.getElementById('dqix-note');if(!d){d=document.createElement('div');d.id='dqix-note';
d.style.cssText='position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:99999;padding:9px 16px;border-radius:3px;font:13px sans-serif;color:#fff;box-shadow:0 2px 12px #0008;max-width:80%';document.body.appendChild(d);}
d.style.background=bad?'#a5322d':'#2f6f3e';d.textContent=t;d.style.display='block';clearTimeout(d._t);d._t=setTimeout(function(){d.style.display='none';},bad?15000:7000);}
var ac=HTMLAnchorElement.prototype.click;
function send(b,restart){var x=new XMLHttpRequest();x.open('POST','/__export');x.setRequestHeader('X-Token',T);if(restart)x.setRequestHeader('X-Restart','1');
x.onload=function(){if(x.status==428){if(confirm(x.responseText))send(b,true);return;}
note(x.status==200?x.responseText:(x.responseText||'Could not save.'),x.status!=200);};
x.onerror=function(){note('The editor helper has closed: use Cheats > Save editor in the game again.',true);};x.send(b);}
HTMLAnchorElement.prototype.click=function(){if(this.download&&lastBlob){note('Saving...',false);send(lastBlob,false);return;}
return ac.apply(this,arguments);};
var tab=((location.hash||'').match(/tab=([a-z]+)/)||[])[1],tries=0;
function gotoTab(){if(!tab)return;var t=0;(function w(){var ul=document.querySelector('nav ul');
if(ul&&getComputedStyle(ul).pointerEvents!=='none'){var li=ul.querySelectorAll('li'),ix=['party','items','inn','grottos','records','dlc','misc','hex'].indexOf(tab);if(ix>=0&&li[ix]){li[ix].click();return;}}
if(++t<60)setTimeout(w,200);})();}
function loadSave(){var inp=document.getElementById('file-input');if(!inp){if(++tries<100)setTimeout(loadSave,200);return;}
var x=new XMLHttpRequest();x.open('GET','/__save');x.setRequestHeader('X-Token',T);x.responseType='blob';
x.onload=function(){if(x.status!=200){note('No game save found: choose a file yourself.',true);return;}
var dt=new DataTransfer();dt.items.add(new File([x.response],'dqix.sav'));inp.files=dt.files;inp.dispatchEvent(new Event('change',{bubbles:true}));gotoTab();};x.send();}
var L='@L@',sel=document.createElement('select');sel.title='Language';
sel.style.cssText='position:fixed;right:10px;bottom:10px;z-index:99998;font:12px sans-serif;padding:3px 6px;opacity:.9';
[['en','English'],['de','Deutsch'],['fr','Français'],['es','Español'],['it','Italiano']].forEach(function(p){var o=document.createElement('option');o.value=p[0];o.textContent=p[1];if(p[0]===L)o.selected=true;sel.appendChild(o);});
sel.onchange=function(){var x=new XMLHttpRequest();x.open('POST','/__lang');x.setRequestHeader('X-Token',T);x.onload=function(){location.reload();};x.send(sel.value);};
document.body.appendChild(sel);
setInterval(function(){var x=new XMLHttpRequest();x.open('GET','/__ping');x.setRequestHeader('X-Token',T);x.send();},20000);
loadSave();})();</script>";

        public EditorHost(string cacheDir, string sav, string backups, Func<bool> running)
        {
            cache = cacheDir; savePath = sav; backupDir = backups; gameRunning = running;
            try { ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072 | (SecurityProtocolType)768 | SecurityProtocolType.Tls; } catch (Exception) { }
        }

        public string Base { get { return "http://127.0.0.1:" + Port + "/editor/"; } }

        public bool Start()
        {
            if (http != null) return true;
            for (int p = 47231; p < 47260 && http == null; p++)
            {
                HttpListener h = new HttpListener();
                h.Prefixes.Add("http://127.0.0.1:" + p + "/");
                try { h.Start(); http = h; Port = p; }
                catch (Exception) { try { h.Close(); } catch (Exception) { } }
            }
            if (http == null) { LastError = "No free local port for the editor."; return false; }
            Thread th = new Thread(Loop) { IsBackground = true };
            th.Start();
            return true;
        }

        public void Dispose() { try { if (http != null) http.Close(); } catch (Exception) { } http = null; }

        void Loop()
        {
            while (http != null && http.IsListening)
            {
                HttpListenerContext c;
                try { c = http.GetContext(); } catch (Exception) { return; }
                ThreadPool.QueueUserWorkItem(delegate { Handle(c); });
            }
        }

        static byte[] Get(string url)
        {
            HttpWebRequest r = (HttpWebRequest)WebRequest.Create(url);
            r.Timeout = 15000; r.UserAgent = "dqix-editor";
            using (WebResponse w = r.GetResponse())
            using (Stream s = w.GetResponseStream())
            using (MemoryStream m = new MemoryStream())
            {
                s.CopyTo(m);
                return m.ToArray();
            }
        }

        /* only plain relative names, and only inside the cache folder (no drive letters, no .., no streams) */
        string CachePath(string rel)
        {
            if (rel.Length == 0 || rel.Length > 200 || !Regex.IsMatch(rel, @"\A[A-Za-z0-9_\-][A-Za-z0-9_\-./]*\z") || rel.Contains("..") || rel.Contains("//")) return null;
            string root = Path.GetFullPath(cache).TrimEnd('\\') + "\\";
            string full = Path.GetFullPath(Path.Combine(root, rel.Replace('/', '\\')));
            return full.StartsWith(root, StringComparison.OrdinalIgnoreCase) ? full : null;
        }

        /* a file of the editor, from the cache; the start page is looked up fresh when the internet is there */
        public byte[] FileOf(string rel, bool fresh)
        {
            string f = CachePath(rel);
            if (f == null) { LastError = "Not a file of the editor."; return null; }
            if (File.Exists(f) && !fresh) return File.ReadAllBytes(f);
            try
            {
                byte[] b = Get(Origin + "/editor/" + rel);
                Directory.CreateDirectory(Path.GetDirectoryName(f));
                File.WriteAllBytes(f, b);
                return b;
            }
            catch (Exception ex)
            {
                if (File.Exists(f)) return File.ReadAllBytes(f);
                LastError = "Couldn't download the editor (" + ex.Message + "). It needs the internet once.";
                return null;
            }
        }

        /* before the browser opens: the start page and the files it names */
        public bool Prepare()
        {
            byte[] idx = FileOf("index.html", true);
            if (idx == null) return false;
            foreach (Match m in Regex.Matches(Encoding.UTF8.GetString(idx), "(?:src|href)=\"/editor/([^\"]+)\""))
                if (FileOf(m.Groups[1].Value, false) == null) return false;
            return true;
        }

        static string Mime(string rel)
        {
            switch (Path.GetExtension(rel).ToLowerInvariant())
            {
                case ".html": return "text/html; charset=utf-8";
                case ".js": return "text/javascript; charset=utf-8";
                case ".css": return "text/css; charset=utf-8";
                case ".png": return "image/png";
                case ".ico": return "image/x-icon";
                case ".svg": return "image/svg+xml";
                case ".json": case ".webmanifest": return "application/json";
                case ".woff2": return "font/woff2";
                case ".woff": return "font/woff";
                default: return "application/octet-stream";
            }
        }

        static void Reply(HttpListenerContext c, int code, string type, byte[] body)
        {
            try
            {
                c.Response.StatusCode = code; c.Response.ContentType = type;
                c.Response.ContentLength64 = body.Length;
                c.Response.OutputStream.Write(body, 0, body.Length);
            }
            catch (Exception) { }
            try { c.Response.Close(); } catch (Exception) { }
        }
        static void Say(HttpListenerContext c, int code, string text) { Reply(c, code, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes(text)); }

        bool Allowed(HttpListenerContext c)
        {
            string o = c.Request.Headers["Origin"];
            if (o != null && o != "http://127.0.0.1:" + Port) return false;
            return c.Request.Headers["X-Token"] == token;
        }

        public string Token { get { return token; } }

        /* the editor's item names in the game's own words (read from the ROM into mods/system/lang/rom-itemname-<lang>.tsv) */
        public Func<string> LangOf;

        /* ---- Export while the game runs: the game takes the save (mod_editor_take in mod_menu.c) and starts again ---- */
        public string HandDir;                          /* mods\system\bin: where the game looks for the save */
        public Func<IntPtr> GameWindow;                 /* the game's window, or zero */
        byte[] served;                                  /* the save the page got: the game compares it with its own */
        static readonly object handLock = new object();

        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool PostMessageW(IntPtr h, uint msg, IntPtr w, IntPtr l);
        delegate bool EnumProc(IntPtr h, IntPtr l);
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
        [System.Runtime.InteropServices.DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
        static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);

        /* the game's own window (SDL's window class) of a running dqix.exe */
        public static IntPtr FindGameWindow()
        {
            List<uint> pids = new List<uint>();
            foreach (Process p in Process.GetProcessesByName("dqix")) { pids.Add((uint)p.Id); p.Dispose(); }
            IntPtr found = IntPtr.Zero;
            EnumWindows(delegate (IntPtr h, IntPtr l)
            {
                uint pid; GetWindowThreadProcessId(h, out pid);
                if (!pids.Contains(pid) || !IsWindowVisible(h)) return true;
                StringBuilder s = new StringBuilder(64); GetClassNameW(h, s, 64);
                if (s.ToString() != "SDL_app") return true;
                found = h; return false;
            }, IntPtr.Zero);
            return found;
        }

        int HandOver(IntPtr win, byte[] body, out string said)
        {
            lock (handLock)
            {
                string ed = Path.Combine(HandDir, "editor-export.sav"), loaded = Path.Combine(HandDir, "editor-loaded.sav"), answer = Path.Combine(HandDir, "editor-export.txt");
                Directory.CreateDirectory(HandDir);
                try { File.Delete(answer); } catch (Exception) { }
                File.WriteAllBytes(loaded, served ?? new byte[0]);
                File.WriteAllBytes(ed + ".tmp", body);
                if (File.Exists(ed)) File.Delete(ed);
                File.Move(ed + ".tmp", ed);
                PostMessageW(win, 0x0111 /* WM_COMMAND */, (IntPtr)9364, IntPtr.Zero);
                DateTime t0 = DateTime.UtcNow;
                while (File.Exists(ed) && (DateTime.UtcNow - t0).TotalSeconds < 10) Thread.Sleep(100);
                if (File.Exists(ed))
                {
                    try { File.Delete(ed); File.Delete(loaded); } catch (Exception) { }
                    said = "The game didn't take the save (it may be busy in a menu, or built before this editor). Close the game, then press export again.";
                    return 409;
                }
                string r = null;
                while (r == null && (DateTime.UtcNow - t0).TotalMinutes < 10 && gameRunning())   /* the game may ask first: wait for the answer */
                {
                    Thread.Sleep(150);
                    try { if (File.Exists(answer)) r = File.ReadAllText(answer).Trim(); } catch (Exception) { }
                }
                try { File.Delete(answer); } catch (Exception) { }
                switch (r)
                {
                    case "ok":
                        served = body;
                        said = "Saved: the game starts again with the edited save. The old save is in the save-backups folder next to the game.";
                        return 200;
                    case "cancel": said = "Not saved: you kept the save of the game."; return 409;
                    case "session": said = "Not saved: leave the session first (Wireless menu), then press export again."; return 409;
                    case "bad": said = "Not saved: the game says this isn't a Dragon Quest IX save."; return 400;
                    case "nobackup": said = "Not saved: the game couldn't keep a copy of the current save in save-backups."; return 500;
                    default: said = "The game didn't answer. Check whether it started again with the edited save."; return 504;
                }
            }
        }
        public string LangDir = "";
        readonly Dictionary<string, Dictionary<int, string>> romNames = new Dictionary<string, Dictionary<int, string>>();
        readonly Dictionary<string, byte[]> localized = new Dictionary<string, byte[]>();

        Dictionary<int, string> RomNames(string lang)
        {
            Dictionary<int, string> d;
            if (romNames.TryGetValue(lang, out d)) return d;
            string f = Path.Combine(LangDir, "rom-itemname-" + lang + ".tsv");
            if (File.Exists(f))
            {
                d = new Dictionary<int, string>();
                foreach (string line in File.ReadAllLines(f, Encoding.UTF8))
                {
                    string[] c = line.Split('\t');
                    int id;
                    if (c.Length >= 2 && int.TryParse(c[0], out id)) d[id] = c[1];
                }
            }
            romNames[lang] = d;
            return d;
        }

        static string Norm(string s)
        {
            return Regex.Replace(s.ToLowerInvariant(), "[^a-z0-9]", "");
        }

        /* the editor's own item list has English names; a name is swapped only where the ROM's English name for that id is the same one */
        byte[] Localize(byte[] js, string rel)
        {
            string lang = LangOf != null ? LangOf() : "en";
            if (lang == "en" || LangDir.Length == 0) return js;
            Dictionary<int, string> en = RomNames("en"), loc = RomNames(lang);
            if (en == null || loc == null) return js;
            byte[] done;
            lock (localized) { if (localized.TryGetValue(lang + "|" + rel, out done)) return done; }
            string text = Encoding.UTF8.GetString(js);
            text = Regex.Replace(text, @"\{id:([0-9]+(?:\.[0-9]+)?(?:e[0-9]+)?),([^{}]*?)name:""((?:[^""\\]|\\.)*)""", delegate (Match m)
            {
                double dv;
                if (!double.TryParse(m.Groups[1].Value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out dv)) return m.Value;
                int id = (int)dv;
                string e, l;
                if (!en.TryGetValue(id, out e) || !loc.TryGetValue(id, out l) || l.Length == 0) return m.Value;
                if (Norm(m.Groups[3].Value) != Norm(e)) return m.Value;
                string name = char.ToUpperInvariant(l[0]) + l.Substring(1);
                name = name.Replace("\\", "\\\\").Replace("\"", "\\\"");
                return "{id:" + m.Groups[1].Value + "," + m.Groups[2].Value + "name:\"" + name + "\"";
            });
            done = Encoding.UTF8.GetBytes(text);
            lock (localized) { localized[lang + "|" + rel] = done; }
            return done;
        }


        /* ---- the editor's own texts in the chosen language: ROM glossary (monsters, vocations, accolades, menu words...) + mods\system\lang\editor.tsv ---- */
        const string TranslatorJs = @"<script>(function(){var D=window.__DQIX_TR;if(!D)return;
function nk(s){var a=s.toLowerCase().replace(/[^a-z0-9]/g,'');return a?a+(/:\s*$/.test(s)?':':''):'';}
function has(k){return Object.prototype.hasOwnProperty.call(D,k);}
function one(s){var k=nk(s);if(!k)return null;if(has(k))return D[k];
if(k.slice(-1)===':'&&has(k.slice(0,-1)))return D[k.slice(0,-1)]+':';
if(k.slice(-1)!==':'&&has(k+':'))return D[k+':'].replace(/\s*:\s*$/,'');
var m=s.match(/^(.*?)(\s+L?\d+)$/);if(m){k=nk(m[1]);if(k&&Object.prototype.hasOwnProperty.call(D,k))return D[k]+m[2];}return null;}
function tr(s){var m=s.match(/^(\s*)([\s\S]*?)(\s*)$/),t=m[2];if(!t||!/[A-Za-z]{2}/.test(t)||/^[^A-Za-z]*[A-Z]{2,4}$/.test(t))return s;var r=one(t);
if(r===null&&/ - |\(/.test(t)){var p=t.split(/( - |\(|\)| \/ )/),ch=false;for(var i=0;i<p.length;i+=2){if(p[i]){var q=one(p[i]);if(q!==null){p[i]=q;ch=true;}}}if(ch)r=p.join('');}
return r===null?s:m[1]+r+m[3];}
var AT=['placeholder','title','alt','aria-label'];
function walk(n){if(n.nodeType===3){var v=n.nodeValue;if(n.__t===v)return;var w=tr(v);if(w!==v)n.nodeValue=w;n.__t=n.nodeValue;return;}
if(n.nodeType!==1)return;var g=n.tagName;if(g==='SCRIPT'||g==='STYLE'||g==='TEXTAREA')return;
for(var i=0;i<AT.length;i++){var a=n.getAttribute(AT[i]);if(a){var b=tr(a);if(b!==a)n.setAttribute(AT[i],b);}}
for(var c=n.firstChild;c;c=c.nextSibling)walk(c);}
new MutationObserver(function(ms){for(var i=0;i<ms.length;i++){var m=ms[i];if(m.type==='characterData')walk(m.target);else for(var j=0;j<m.addedNodes.length;j++)walk(m.addedNodes[j]);}})
.observe(document.documentElement,{childList:true,subtree:true,characterData:true});
walk(document.documentElement);})();</script>";

        /* the editor's boxes and tabs are sized for English words: in another language let headings wrap, cards grow,
         * tab rows wrap instead of running off the edge, labels get the room they need */
        const string FixCss = @"<style>
.card>.card-label{height:auto;min-height:36px;overflow-wrap:anywhere}
.misc-root,.dlc-root{grid-template-rows:none;grid-auto-rows:minmax(204px,auto)}
.misc-root>div,.dlc-root>div{aspect-ratio:auto;min-height:204px}
.records-root .records .tab-header{height:auto;flex-wrap:wrap;justify-content:center;gap:0 1.4em}
.records-root .records .tab-header>*{white-space:nowrap}
nav ul li,nav ul li a{white-space:nowrap}
.misc-root .save-location label span{width:auto;min-width:10%}
.misc-root .profile-card>div>label>span,.profile-card>div>label>span{width:auto;min-width:25%;padding-right:.4em}
.misc-root .profile-card>div>label>input,.misc-root .profile-card>div>label>select,.profile-card>div>label>input,.profile-card>div>label>select{width:auto;flex:1}
button{white-space:normal}
</style>";

        readonly Dictionary<string, string> trJson = new Dictionary<string, string>();

        static string NormKey(string s)
        {
            StringBuilder b = new StringBuilder();
            foreach (char c in s.ToLowerInvariant()) if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) b.Append(c);
            if (b.Length > 0 && s.TrimEnd().EndsWith(":")) b.Append(':');
            return b.ToString();
        }

        static void JsonStr(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                if (c == '"') sb.Append("\\\"");
                else if (c == '\\') sb.Append("\\\\");
                else if (c < ' ' || c == (char)8232 || c == (char)8233) sb.Append("\\u" + ((int)c).ToString("x4"));
                else if (c == '<') sb.Append("\\u003c");
                else sb.Append(c);
            }
            sb.Append('"');
        }

        /* {"normalised english": "translation", ...} for the language; the editor's own file wins over the ROM glossary */
        string TrScript(string lang)
        {
            if (lang == "en" || LangDir.Length == 0) return "";
            int col = Array.IndexOf(Tr.Codes, lang);
            if (col < 1) return "";
            string json;
            lock (trJson)
            {
                if (!trJson.TryGetValue(lang, out json))
                {
                    Dictionary<string, string> d = new Dictionary<string, string>();
                    foreach (string name in new[] { "rom-glossary.tsv", "editor.tsv" })
                    {
                        string f = Path.Combine(LangDir, name);
                        if (!File.Exists(f)) continue;
                        foreach (string line in File.ReadAllLines(f, Encoding.UTF8))
                        {
                            if (line.Length == 0 || line[0] == '#') continue;
                            string[] c = line.Split('\t');
                            if (c.Length <= col || c[col].Length == 0) continue;
                            string k = NormKey(c[0]);
                            if (k.Length > 1) d[k] = c[col];
                        }
                    }
                    StringBuilder sb = new StringBuilder("{");
                    bool first = true;
                    foreach (KeyValuePair<string, string> kv in d)
                    {
                        if (!first) sb.Append(','); first = false;
                        JsonStr(sb, kv.Key); sb.Append(':'); JsonStr(sb, kv.Value);
                    }
                    sb.Append('}');
                    json = sb.ToString();
                    trJson[lang] = json;
                }
            }
            return "<script>window.__DQIX_TR=" + json + ";</script>" + FixCss + TranslatorJs;
        }

        void Handle(HttpListenerContext c)
        {
            try
            {
                string path = c.Request.Url.AbsolutePath;
                LastSeen = DateTime.UtcNow;
                if (path == "/__ping") { Say(c, Allowed(c) ? 200 : 403, "ok"); return; }
                if (path == "/__lang" && c.Request.HttpMethod == "POST")
                {
                    if (!Allowed(c)) { Say(c, 403, "No."); return; }
                    string l;
                    using (StreamReader r = new StreamReader(c.Request.InputStream, Encoding.UTF8)) l = r.ReadToEnd().Trim();
                    if (Array.IndexOf(Tr.Codes, l) < 0 || SetLang == null) { Say(c, 400, "Unknown language."); return; }
                    SetLang(l); Say(c, 200, "ok");
                    return;
                }
                if (path == "/") { c.Response.Redirect("/editor/"); c.Response.Close(); return; }
                if (path == "/__save" && c.Request.HttpMethod == "GET")
                {
                    if (!Allowed(c)) { Say(c, 403, "No."); return; }
                    if (!File.Exists(savePath)) { Say(c, 404, "No save."); return; }
                    byte[] sav;
                    using (FileStream fs = new FileStream(savePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    using (MemoryStream m = new MemoryStream()) { fs.CopyTo(m); sav = m.ToArray(); }
                    served = sav;
                    Reply(c, 200, "application/octet-stream", sav);
                    return;
                }
                if (path == "/__export" && c.Request.HttpMethod == "POST")
                {
                    if (!Allowed(c)) { Say(c, 403, "No."); return; }
                    byte[] body;
                    using (MemoryStream m = new MemoryStream()) { c.Request.InputStream.CopyTo(m); body = m.ToArray(); }
                    long want = File.Exists(savePath) ? new FileInfo(savePath).Length : 65536;
                    if (body.Length != want) { Say(c, 400, "That isn't a save of this size (" + body.Length + " bytes, expected " + want + "). Nothing was written."); return; }
                    if (gameRunning())
                    {
                        /* a save written under the running game would be overwritten by it: the game takes the save itself and starts again */
                        IntPtr win = GameWindow != null ? GameWindow() : IntPtr.Zero;
                        if (win == IntPtr.Zero || HandDir == null) { Say(c, 409, "The game is running. Close it first, then press export again: a save written under a running game is lost."); return; }
                        if (c.Request.Headers["X-Restart"] != "1")
                        {
                            Say(c, 428, "The game starts again with the edited save.\n\nAnything since you last saved in the game is lost. Go on?");
                            return;
                        }
                        string said;
                        int code = HandOver(win, body, out said);
                        Say(c, code, said);
                        return;
                    }
                    Directory.CreateDirectory(backupDir);
                    if (File.Exists(savePath)) File.Copy(savePath, Path.Combine(backupDir, "dqix-editor-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".sav"), true);
                    string tmp = savePath + ".tmp";
                    File.WriteAllBytes(tmp, body);
                    if (File.Exists(savePath)) File.Delete(savePath);
                    File.Move(tmp, savePath);
                    Say(c, 200, "ok");
                    return;
                }
                if (path.StartsWith("/editor/") && !path.Contains(".."))
                {
                    string rel = path.Substring(8);
                    if (rel.Length == 0) rel = "index.html";
                    byte[] b = FileOf(rel, false);
                    if (b == null) { Say(c, 404, LastError.Length > 0 ? LastError : "Not found."); return; }
                    if (rel == "index.html")
                    {
                        string html = Encoding.UTF8.GetString(b);
                        string inj = Inject.Replace("@T@", token).Replace("@L@", LangOf != null ? LangOf() : "en") + TrScript(LangOf != null ? LangOf() : "en");
                        int at = html.LastIndexOf("</body>", StringComparison.OrdinalIgnoreCase);
                        html = at >= 0 ? html.Insert(at, inj) : html + inj;
                        b = Encoding.UTF8.GetBytes(html);
                    }
                    if (rel.EndsWith(".js")) b = Localize(b, rel);
                    Reply(c, 200, Mime(rel), b);
                    return;
                }
                Say(c, 404, "Not found.");
            }
            catch (Exception ex) { try { Say(c, 500, ex.Message); } catch (Exception) { } }
        }
    }

    static class Program
    {
        static byte[] Http(string method, string url, string token, byte[] body, List<string> bad, int want)
        {
            HttpWebRequest r = (HttpWebRequest)WebRequest.Create(url);
            r.Method = method; r.Timeout = 15000;
            if (token != null) r.Headers["X-Token"] = token;
            if (body != null) { r.ContentLength = body.Length; using (Stream s = r.GetRequestStream()) s.Write(body, 0, body.Length); }
            HttpWebResponse w;
            try { w = (HttpWebResponse)r.GetResponse(); }
            catch (WebException ex) { w = ex.Response as HttpWebResponse; if (w == null) { bad.Add(method + " " + url + ": " + ex.Message); return new byte[0]; } }
            using (w)
            using (Stream s = w.GetResponseStream())
            using (MemoryStream m = new MemoryStream())
            {
                s.CopyTo(m);
                if ((int)w.StatusCode != want) bad.Add(method + " " + url + " gave " + (int)w.StatusCode + ", wanted " + want);
                return m.ToArray();
            }
        }

        /* tests: "--editor-selftest <result file>" starts the editor host on a scratch save and checks what it serves and refuses */
        static int SelfTest(string root, string result)
        {
            List<string> bad = new List<string>();
            string dir = Path.Combine(Path.GetTempPath(), "dqix-editor-selftest-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            string sav = Path.Combine(dir, "dqix.sav");
            string real = Environment.GetEnvironmentVariable("DQIX_EDITOR_SAV");
            if (!string.IsNullOrEmpty(real)) File.Copy(real, sav); else File.WriteAllBytes(sav, new byte[65536]);
            EditorHost h = new EditorHost(Path.Combine(root, "mods", "system", "bin", "editor-cache"), sav, Path.Combine(dir, "backups"), delegate { return false; });
            string langNow = "en", langSaved = null;
            h.LangOf = delegate { return langNow; };
            h.SetLang = delegate (string l) { langNow = l; langSaved = l; };
            h.LangDir = Path.Combine(root, "mods", "system", "lang");
            try
            {
                if (!h.Start()) bad.Add("start: " + h.LastError);
                else if (!h.Prepare()) bad.Add("prepare: " + h.LastError);
                else
                {
                    string page = Encoding.UTF8.GetString(Http("GET", h.Base, null, null, bad, 200));
                    if (!page.Contains("/__save") || !page.Contains(h.Token)) bad.Add("start page has no hook");
                    if (!page.Contains("/__lang")) bad.Add("start page has no language box");
                    /* the language box: wrong token refused, unknown language refused, a good one is kept */
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__lang", "wrong", Encoding.UTF8.GetBytes("de"), bad, 403);
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__lang", h.Token, Encoding.UTF8.GetBytes("xx"), bad, 400);
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__lang", h.Token, Encoding.UTF8.GetBytes("de"), bad, 200);
                    if (langSaved != "de") bad.Add("language not kept");
                    /* the item names of the editor come out in the game's own German */
                    Match jm = Regex.Match(page, @"/editor/(assets/[^""]+\.js)");
                    string de = null;
                    if (jm.Success && File.Exists(Path.Combine(root, "mods", "system", "lang", "rom-itemname-de.tsv")))
                    {
                        foreach (string line in File.ReadAllLines(Path.Combine(h.LangDir, "rom-itemname-de.tsv"), Encoding.UTF8)) if (line.StartsWith("20004\t")) de = line.Split('\t')[1];
                        string js = Encoding.UTF8.GetString(Http("GET", h.Base + jm.Groups[1].Value, null, null, bad, 200));
                        if (de != null && !js.Contains("name:\"" + char.ToUpperInvariant(de[0]) + de.Substring(1) + "\"")) bad.Add("item names not in German: " + de);
                        if (js.Contains("name:\"Copper sword\"")) bad.Add("English item name left");
                        string page2 = Encoding.UTF8.GetString(Http("GET", h.Base, null, null, bad, 200));
                        if (!page2.Contains("window.__DQIX_TR=") || !page2.Contains("Exportieren")) bad.Add("editor texts not translated");
                    }
                    byte[] got = Http("GET", "http://127.0.0.1:" + h.Port + "/__save", h.Token, null, bad, 200);
                    if (got.Length != 65536) bad.Add("save length " + got.Length);
                    Http("GET", "http://127.0.0.1:" + h.Port + "/__save", "wrong", null, bad, 403);
                    foreach (string evil in new[] { "C:/Windows/win.ini", "%5CWindows/win.ini", "..%5C..%5Cx", "assets/..%2F..%2Fx", "a:b" })
                        Http("GET", "http://127.0.0.1:" + h.Port + "/editor/" + evil, null, null, bad, 404);
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__export", h.Token, new byte[100], bad, 400);
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__export", "wrong", new byte[65536], bad, 403);
                    string hold = Environment.GetEnvironmentVariable("DQIX_EDITOR_HOLD");
                    if (!string.IsNullOrEmpty(hold)) { File.WriteAllText(result + ".url", h.Base + "#tab=items"); Thread.Sleep(int.Parse(hold) * 1000); File.WriteAllBytes(sav + ".after", File.ReadAllBytes(sav)); }
                    byte[] edited = new byte[65536]; edited[7] = 42;
                    Http("POST", "http://127.0.0.1:" + h.Port + "/__export", h.Token, edited, bad, 200);
                    if (File.ReadAllBytes(sav)[7] != 42) bad.Add("export did not write the save");
                    if (!Directory.Exists(Path.Combine(dir, "backups")) || Directory.GetFiles(Path.Combine(dir, "backups")).Length != 1) bad.Add("no backup made");
                }
            }
            catch (Exception ex) { bad.Add(ex.ToString()); }
            h.Dispose();
            try { Directory.Delete(dir, true); } catch (Exception) { }
            File.WriteAllText(result, bad.Count == 0 ? "PASS" : "FAIL " + string.Join("; ", bad.ToArray()));
            return bad.Count == 0 ? 0 : 1;
        }

        static void Complain(string root, string text)
        {
            try { File.AppendAllText(Path.Combine(root, "mods", "system", "bin", "editor-error.log"), DateTime.Now + "\r\n" + text + "\r\n\r\n"); } catch (Exception) { }
            try { System.Windows.Forms.MessageBox.Show(text, "Dragon Quest IX - save editor"); } catch (Exception) { }
        }

        static string Here() { return Path.GetFullPath(Path.Combine(Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location), "..", "..")); }

        static int Main(string[] args)
        {
            if (args.Length > 1 && args[0] == "--editor-selftest") return SelfTest(Here(), args[1]);
            string root = args.Length > 0 && !args[0].StartsWith("--") ? args[0].Trim('"') : Here();
            string tab = "party";
            int ea = Array.IndexOf(args, "--editor");
            if (ea >= 0 && ea + 1 < args.Length) tab = args[ea + 1];
            string mods = Path.Combine(root, "mods"), langFile = Path.Combine(mods, "system", "editor-lang.txt");
            string lang = "en";                                       /* the first time it is English; the box in the page changes it for good */
            try { if (File.Exists(langFile)) { string l = File.ReadAllText(langFile).Trim(); if (Array.IndexOf(Tr.Codes, l) >= 0) lang = l; } } catch (Exception) { }
            string langNow = lang;
            EditorHost host = new EditorHost(Path.Combine(mods, "system", "bin", "editor-cache"), Path.Combine(root, "game", "dqix.sav"), Path.Combine(mods, "system", "save-backups"),
                delegate { return Process.GetProcessesByName("dqix").Length > 0; });
            host.LangDir = Path.Combine(mods, "system", "lang");
            host.HandDir = Path.Combine(mods, "system", "bin");
            host.GameWindow = EditorHost.FindGameWindow;
            host.LangOf = delegate { return langNow; };
            host.SetLang = delegate (string l) { langNow = l; try { File.WriteAllText(langFile, l); } catch (Exception) { } };
            if (!host.Start() || !host.Prepare()) { Complain(root, host.LastError); return 1; }
            try { Process.Start(host.Base + "#tab=" + tab); } catch (Exception ex) { Complain(root, "The browser couldn't be opened: " + ex.Message + "\r\nThe page is " + host.Base); }
            while ((DateTime.UtcNow - host.LastSeen).TotalSeconds < 180) Thread.Sleep(2000);     /* the page pings every 20 s while it is open */
            host.Dispose();
            return 0;
        }
    }
}
