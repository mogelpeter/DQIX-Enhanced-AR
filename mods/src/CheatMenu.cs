/* DQIX Enhanced: the cheat menu.
 *
 *   dqix-cheat-menu.exe [DQIX Enhanced folder]
 *
 * A window with every code of the cheat list (mods\bin\catalog.txt, made by
 * mods\tools\catalog.py from the R4 database for your ROM and your own files):
 * switches for the ones that are on or off, a choice for the ones of which
 * only one can be on (experience x2 / x4 / ...), "Once" for one-shot ones.
 *
 * It never touches the game's program. Live cheats go into the game's own
 * mailbox (mods\src\mod_cheats.c) and the game carries them out itself, at a
 * safe point of each frame, the same on every PC of a session. Code mods are
 * only written down here (mods\menu-state.txt, the "enabled" line of a file
 * in mods\code); "Play with mods.bat apply" builds them in, after catalog.py
 * found each instruction in your ROM. A game without the mailbox (built with
 * "sync_cheats = no") gets live cheats written into its DS memory from outside,
 * as the old cheat window did.
 *
 * Built by "Play with mods.bat" with the C# compiler that comes with Windows
 * (.NET Framework 4), so it stays C# 5: no newer syntax.
 */
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Net;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Threading;

namespace DqixMenu
{
    class Entry
    {
        public string Id = "", Cat = "", Group = "", Kind = "", Status = "", Name = "", Option = "", Note = "", Reason = "";
        public string Mode = "", Keys = "", File = "", Env = "";
        public int Combos, Index;
        public bool FileOn;
        public uint[] Ops = new uint[0];                    /* address, value, address, value... */
        public List<KeyValuePair<string, uint>> Patch = new List<KeyValuePair<string, uint>>();   /* "module:address" -> word */
    }

    class Group
    {
        public string Id = "", Cat = "", Title = "", Note = "", Kind = "";
        public List<Entry> Items = new List<Entry>();
    }

    /* ---- Action Replay, as in ar_engine.h (only used when the game has no mailbox) ---- */
    static class Ar
    {
        public const int KeysAll = -1;
        const uint Budget = 400000;
        public delegate bool Io(uint addr, byte[] buf, int n);

        static bool IsRam(uint a) { return (a >> 24) == 0x02; }
        static bool IsKeyReg(uint a) { return a == 0x04000130 || a == 0x04000136 || (a & 0x0FFFFFFF) == 0x027FFFA8; }
        static uint KeyReg(uint a, int keys)
        {
            if (a == 0x04000130) return ~(uint)keys & 0x3FF;
            if (a == 0x04000136) return 0x7F & ~((uint)keys >> 10 & 3);
            return 0x2C00 & ~((((uint)keys >> 10) & 3) << 10);
        }
        static uint R(Io rd, uint a, int n)
        {
            if (!IsRam(a)) return 0;
            byte[] b = new byte[4];
            if (!rd(a, b, n)) return 0;
            return BitConverter.ToUInt32(b, 0);
        }
        static void W(Io wr, uint a, uint v, int n)
        {
            if (!IsRam(a)) return;
            wr(a, BitConverter.GetBytes(v), n);
        }

        public static void Run(Io rd, Io wr, uint[] ops, int keys)
        {
            uint offset = 0, data = 0, budget = Budget;
            int skip = 0, loopStart = -1, n = ops.Length / 2;
            uint loopLeft = 0;
            for (int pc = 0; pc < n; pc++)
            {
                uint a = ops[pc * 2], b = ops[pc * 2 + 1];
                uint t = a >> 28, top = a >> 24, addr = a & 0x0FFFFFFF;
                if (budget-- == 0) return;
                if (skip > 0)
                {
                    if (t >= 3 && t <= 0xA) skip++;
                    else if (top == 0xD0) skip--;
                    else if (top == 0xD1 || top == 0xD2)
                    {
                        skip = 0;
                        if (top == 0xD2 && loopStart < 0) { offset = 0; data = 0; }
                        if (loopStart >= 0)
                        {
                            if (loopLeft > 0) { loopLeft--; pc = loopStart; continue; }
                            loopStart = -1;
                            if (top == 0xD2) { offset = 0; data = 0; }
                        }
                    }
                    else if (t == 0xE) pc += (int)((b + 7) / 8);
                    continue;
                }
                if (t <= 2) addr += offset;
                else if (t <= 0xB && addr == 0) addr = offset;
                switch (t)
                {
                    case 0: W(wr, addr, b, 4); break;
                    case 1: W(wr, addr, b, 2); break;
                    case 2: W(wr, addr, b, 1); break;
                    case 3: case 4: case 5: case 6:
                        {
                            if (IsKeyReg(addr) && keys == KeysAll) break;
                            uint v = IsKeyReg(addr) ? KeyReg(addr, keys) : R(rd, addr, 4);
                            bool ok = t == 3 ? b > v : t == 4 ? b < v : t == 5 ? b == v : b != v;
                            if (!ok) skip = 1;
                            break;
                        }
                    case 7: case 8: case 9: case 0xA:
                        {
                            if (IsKeyReg(addr) && keys == KeysAll) break;
                            uint v = (IsKeyReg(addr) ? KeyReg(addr, keys) : R(rd, addr, 2)) & ~(b >> 16) & 0xFFFF, y = b & 0xFFFF;
                            bool ok = t == 7 ? y > v : t == 8 ? y < v : t == 9 ? y == v : y != v;
                            if (!ok) skip = 1;
                            break;
                        }
                    case 0xB: offset = R(rd, addr, 4); break;
                    case 0xC:
                        if (top == 0xC0) { loopStart = pc; loopLeft = b; }
                        break;
                    case 0xD:
                        switch (top)
                        {
                            case 0xD1:
                            case 0xD2:
                                if (loopStart >= 0)
                                {
                                    if (loopLeft > 0) { loopLeft--; pc = loopStart; break; }
                                    loopStart = -1;
                                }
                                if (top == 0xD2) { offset = 0; data = 0; }
                                break;
                            case 0xD3: offset = b; break;
                            case 0xD4: data += b; break;
                            case 0xD5: data = b; break;
                            case 0xD6: W(wr, b + offset, data, 4); offset += 4; break;
                            case 0xD7: W(wr, b + offset, data, 2); offset += 2; break;
                            case 0xD8: W(wr, b + offset, data, 1); offset += 1; break;
                            case 0xD9: data = R(rd, b + offset, 4); break;
                            case 0xDA: data = R(rd, b + offset, 2); break;
                            case 0xDB: data = R(rd, b + offset, 1); break;
                            case 0xDC: offset += b; break;
                        }
                        break;
                    case 0xE:
                        {
                            uint dst = addr + offset, i = 0;
                            for (int l = pc + 1; l < n && i < b; l++)
                            {
                                if (budget < 8) return;
                                budget -= 8;
                                for (int k = 0; k < 2 && i < b; k++)
                                    for (int s = 0; s < 4 && i < b; s++, i++) W(wr, dst + i, (ops[l * 2 + k] >> (8 * s)) & 0xFF, 1);
                            }
                            pc += (int)((b + 7) / 8);
                            break;
                        }
                    case 0xF:
                        if (b > budget) return;
                        budget -= b;
                        for (uint i = 0; i < b; i++) W(wr, addr + i, R(rd, offset + i, 1), 1);
                        break;
                }
            }
        }
    }

    /* ---- the running game ---- */
    class GameLink : IDisposable
    {
        const uint Magic = 0x43584451;                      /* "DQXC", as in mod_cheats.c */
        const int Ring = 8192, RingAt = 32;
        const uint RamSize = 0x400000, HeaderAt = 0x3FFE00;
        const int HeaderMatch = 0x40;

        [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool ReadProcessMemory(IntPtr p, IntPtr addr, byte[] buf, IntPtr n, out IntPtr got);
        [DllImport("kernel32.dll", SetLastError = true)] static extern bool WriteProcessMemory(IntPtr p, IntPtr addr, byte[] buf, IntPtr n, out IntPtr put);
        [StructLayout(LayoutKind.Sequential)]
        struct MBI { public IntPtr BaseAddress, AllocationBase; public uint AllocationProtect; public IntPtr RegionSize; public uint State, Protect, Type; }
        [DllImport("kernel32.dll")] static extern IntPtr VirtualQueryEx(IntPtr p, IntPtr addr, out MBI mbi, IntPtr len);

        public string GameDir;
        public Process Proc;
        MemoryMappedFile mmf;
        MemoryMappedViewAccessor box;
        IntPtr hproc = IntPtr.Zero;
        long ram;
        readonly Queue<ushort[]> queue = new Queue<ushort[]>();
        uint gen;
        bool needSync;
        DateTime nextTry = DateTime.MinValue;
        public Func<IEnumerable<Entry>> LiveOn;             /* the cheats that are switched on */

        public bool Running { get { return Proc != null; } }
        public bool Inside { get { return box != null; } }
        public bool Outside { get { return hproc != IntPtr.Zero && ram != 0; } }
        public bool Connected { get { return Inside || Outside; } }
        public uint Version { get { return box != null ? box.ReadUInt32(4) : 0; } }
        public bool Session { get { try { return box != null && box.ReadUInt32(20) != 0; } catch { return false; } } }
        public bool Busy { get { try { return box != null && (queue.Count > 0 || box.ReadUInt32(8) != box.ReadUInt32(12)); } catch { return false; } } }

        public void Dispose() { Detach(); }

        void Detach()
        {
            try { if (box != null) box.Dispose(); } catch { }
            try { if (mmf != null) mmf.Dispose(); } catch { }
            if (hproc != IntPtr.Zero) CloseHandle(hproc);
            try { if (Proc != null) Proc.Dispose(); } catch { }
            box = null; mmf = null; hproc = IntPtr.Zero; ram = 0; Proc = null;
            queue.Clear();
        }

        /* once a frame or so */
        public void Tick()
        {
            try
            {
                if (Proc != null)
                {
                    bool gone;
                    try { gone = Proc.HasExited; } catch { gone = true; }
                    if (gone) Detach();
                }
                if (Proc == null || !Connected)
                {
                    if (DateTime.UtcNow < nextTry) return;
                    nextTry = DateTime.UtcNow.AddSeconds(1);
                    Attach();
                    if (!Connected) return;
                }
                if (box != null)
                {
                    if (needSync || box.ReadUInt32(16) != gen) Resync();
                    Pump();
                }
                else if (LiveOn != null)
                {
                    foreach (Entry e in LiveOn()) Ar.Run(MemRead, MemWrite, e.Ops, 0);
                }
            }
            catch (Exception) { Detach(); }                 /* the game went away in the middle: look again */
        }

        void Attach()
        {
            if (Proc == null)
            {
                Process[] all = Process.GetProcessesByName("dqix");
                if (all.Length == 0) return;
                Proc = all[0];
                for (int i = 1; i < all.Length; i++) all[i].Dispose();
            }
            int pid = Proc.Id;
            if (Environment.GetEnvironmentVariable("DQIX_CHEATS_OUTSIDE") != null) { AttachOutside(pid); return; }   /* tests: the other way */
            try
            {
                mmf = MemoryMappedFile.OpenExisting("Local\\dqix-mod-cheats-" + pid, MemoryMappedFileRights.ReadWrite);
                box = mmf.CreateViewAccessor(0, RingAt + Ring * 2, MemoryMappedFileAccess.ReadWrite);
                if (box.ReadUInt32(0) == Magic) { needSync = true; return; }
            }
            catch (Exception) { }
            try { if (box != null) box.Dispose(); } catch { }
            try { if (mmf != null) mmf.Dispose(); } catch { }
            box = null; mmf = null;
            AttachOutside(pid);
        }

        /* A game without the mailbox: its DS memory is a static array in dqix.exe, found by the
         * cartridge header the game copies to DS address 0x027FFE00 when it starts. */
        void AttachOutside(int pid)
        {
            byte[] hdr = new byte[HeaderMatch];
            try
            {
                using (FileStream f = File.OpenRead(Path.Combine(GameDir, "data", "dqix.nds")))
                    if (f.Read(hdr, 0, HeaderMatch) != HeaderMatch) return;
            }
            catch (Exception) { return; }
            /* the header alone can be in the program more than once (the cartridge's own copy): the
             * DS memory is the place that also has the game's program where a DS has it */
            const int ProbeAt = 0x4000, ProbeLen = 64;
            byte[] probe = null;
            try
            {
                using (FileStream f = File.OpenRead(Path.Combine(GameDir, "data", "code", "arm9", "arm9.bin")))
                {
                    byte[] b = new byte[ProbeLen];
                    f.Seek(ProbeAt, SeekOrigin.Begin);
                    if (f.Read(b, 0, ProbeLen) == ProbeLen) probe = b;
                }
            }
            catch (Exception) { }
            long lo, hi;
            try { ProcessModule m = Proc.MainModule; lo = m.BaseAddress.ToInt64(); hi = lo + m.ModuleMemorySize; }
            catch (Exception) { return; }
            IntPtr p = OpenProcess(0x0010 | 0x0020 | 0x0008 | 0x0400, false, pid);      /* read, write, operation, query */
            if (p == IntPtr.Zero) return;
            long found = 0;
            const int chunk = 1 << 20;
            byte[] buf = new byte[chunk + HeaderMatch];
            for (long a = lo; a < hi && found == 0;)
            {
                MBI mbi;
                if (VirtualQueryEx(p, new IntPtr(a), out mbi, new IntPtr(Marshal.SizeOf(typeof(MBI)))) == IntPtr.Zero) break;
                long rend = mbi.BaseAddress.ToInt64() + mbi.RegionSize.ToInt64();
                if (rend > hi) rend = hi;
                bool readable = mbi.State == 0x1000 && (mbi.Protect & (0x01 | 0x100)) == 0 && (mbi.Protect & (0x04 | 0x08 | 0x40)) != 0;
                if (readable)
                    for (long c = a; c < rend && found == 0; c += chunk)
                    {
                        long want = Math.Min(rend - c, chunk + HeaderMatch);
                        IntPtr got;
                        if (!ReadProcessMemory(p, new IntPtr(c), buf, new IntPtr(want), out got)) continue;
                        int g = (int)got.ToInt64();
                        for (int i = 0; i + HeaderMatch <= g; i += 4)
                        {
                            if (buf[i] != hdr[0]) continue;
                            int k = 0;
                            while (k < HeaderMatch && buf[i + k] == hdr[k]) k++;
                            if (k < HeaderMatch) continue;
                            long b = c + i - HeaderAt;
                            if (b < lo || b + RamSize > hi) continue;
                            if (probe != null)
                            {
                                byte[] there = new byte[ProbeLen];
                                IntPtr got2;
                                if (!ReadProcessMemory(p, new IntPtr(b + ProbeAt), there, new IntPtr(ProbeLen), out got2) || !there.SequenceEqual(probe)) continue;
                            }
                            found = b; break;
                        }
                    }
                if (rend <= a) break;
                a = rend;
            }
            if (found == 0) { CloseHandle(p); return; }
            hproc = p; ram = found;
        }

        bool MemRead(uint a, byte[] buf, int n)
        {
            a &= RamSize - 1;
            if (hproc == IntPtr.Zero || a + n > RamSize) return false;
            IntPtr got;
            return ReadProcessMemory(hproc, new IntPtr(ram + a), buf, new IntPtr(n), out got) && got.ToInt64() == n;
        }
        bool MemWrite(uint a, byte[] buf, int n)
        {
            a &= RamSize - 1;
            if (hproc == IntPtr.Zero || a + n > RamSize) return false;
            IntPtr put;
            return WriteProcessMemory(hproc, new IntPtr(ram + a), buf, new IntPtr(n), out put) && put.ToInt64() == n;
        }

        /* ---- messages to the game: header (type << 12 | words that follow), then as in mod_cheats.c ---- */
        static ushort[] Message(int type, int id, uint[] ops)
        {
            int len = (id >= 0 ? 1 : 0) + (ops != null ? ops.Length * 2 : 0);
            if (len > 0xFFF) return null;
            ushort[] m = new ushort[len + 1];
            int k = 0;
            m[k++] = (ushort)(type << 12 | len);
            if (id >= 0) m[k++] = (ushort)id;
            if (ops != null) foreach (uint v in ops) { m[k++] = (ushort)v; m[k++] = (ushort)(v >> 16); }
            return m;
        }

        void Pump()
        {
            while (queue.Count > 0)
            {
                ushort[] m = queue.Peek();
                uint w = box.ReadUInt32(8), r = box.ReadUInt32(12);
                if (w - r + (uint)m.Length + 1 > Ring) return;                /* the game is still sending the last ones */
                foreach (ushort v in m) { box.Write(RingAt + (long)(w % Ring) * 2, v); w++; }
                box.Write(8, w);                                              /* the game sees a message only when it is whole */
                queue.Dequeue();
            }
        }

        /* the game has no cheats (it just started, a session began...): all that are on, from scratch */
        void Resync()
        {
            gen = box.ReadUInt32(16);
            needSync = false;
            queue.Clear();
            queue.Enqueue(Message(4, -1, null));
            if (LiveOn != null)
                foreach (Entry e in LiveOn())
                {
                    ushort[] m = Message(2, e.Index, e.Ops);
                    if (m != null) queue.Enqueue(m);
                }
        }

        public void Set(Entry e, bool on)
        {
            if (box == null) return;                         /* outside: Tick runs whatever is on */
            ushort[] m = on ? Message(2, e.Index, e.Ops) : Message(3, e.Index, null);
            if (m != null) queue.Enqueue(m);
        }

        public bool Once(Entry e)
        {
            if (box != null)
            {
                ushort[] m = Message(1, -1, e.Ops);
                if (m == null) return false;
                queue.Enqueue(m);
                return true;
            }
            if (!Outside) return false;
            Ar.Run(MemRead, MemWrite, e.Ops, Ar.KeysAll);
            return true;
        }

        public void ClearAll() { needSync = true; }
    }

    /* ---- translations: mods\lang\ui.tsv has one line per English text and a column per language (de fr es it) ---- */
    static class Tr
    {
        public static string Lang = "en";
        static readonly Dictionary<string, string> map = new Dictionary<string, string>();
        public static readonly string[] Codes = { "en", "de", "fr", "es", "it" };
        public static readonly string[] Names = { "English", "Deutsch", "Fran\u00e7ais", "Espa\u00f1ol", "Italiano" };

        public static string Detect()
        {
            string two = System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName;
            return Array.IndexOf(Codes, two) >= 0 ? two : "en";
        }

        public static void Load(string dir, string lang)
        {
            Lang = lang; map.Clear();
            int col = Array.IndexOf(Codes, lang);
            string f = Path.Combine(dir, "ui.tsv");
            if (col < 1 || !File.Exists(f)) return;
            foreach (string line in File.ReadAllLines(f, Encoding.UTF8))
            {
                if (line.Length == 0 || line[0] == '#') continue;
                string[] c = line.Split('\t');
                if (c.Length > col && c[col].Length > 0) map[Un(c[0])] = Un(c[col]);
            }
        }
        static string Un(string s) { return s.Replace("\\n", "\n"); }
        public static string T(string s) { string v; return s != null && map.TryGetValue(s, out v) ? v : s; }
        public static string F(string fmt, params object[] a) { return string.Format(T(fmt), a); }
    }

    /* ---- the save editor and treasure map tabs: the DQIX project's browser editor (https://github.com/dqix/editor),
     * fetched from dqix.github.io on first use into mods\bin\editor-cache and served from here to the browser. Nothing of it is
     * part of this repo. The host also hands the editor your game save and writes the exported one back (after a backup). ---- */
    class EditorHost : IDisposable
    {
        const string Origin = "https://dqix.github.io";
        readonly string cache, savePath, backupDir;
        readonly Func<bool> gameRunning;
        HttpListener http;
        public int Port;
        public string LastError = "";
        readonly string token = Guid.NewGuid().ToString("N");

        const string Inject = @"<script>(function(){var T='@T@',lastBlob=null,oc=URL.createObjectURL;
URL.createObjectURL=function(b){lastBlob=b;return oc.call(URL,b);};
function note(t,bad){var d=document.getElementById('dqix-note');if(!d){d=document.createElement('div');d.id='dqix-note';
d.style.cssText='position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:99999;padding:9px 16px;border-radius:3px;font:13px sans-serif;color:#fff;box-shadow:0 2px 12px #0008;max-width:80%';document.body.appendChild(d);}
d.style.background=bad?'#a5322d':'#2f6f3e';d.textContent=t;d.style.display='block';clearTimeout(d._t);d._t=setTimeout(function(){d.style.display='none';},bad?15000:7000);}
var ac=HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click=function(){if(this.download&&lastBlob){var x=new XMLHttpRequest();x.open('POST','/__export');x.setRequestHeader('X-Token',T);
x.onload=function(){note(x.status==200?'Saved into your game save. The old one is in mods/save-backups.':(x.responseText||'Could not save.'),x.status!=200);};
x.onerror=function(){note('The cheat menu is not reachable any more.',true);};x.send(lastBlob);return;}
return ac.apply(this,arguments);};
var tab=((location.hash||'').match(/tab=([a-z]+)/)||[])[1],tries=0;
function gotoTab(){if(!tab)return;var t=0;(function w(){var ul=document.querySelector('nav ul');
if(ul&&getComputedStyle(ul).pointerEvents!=='none'){var li=ul.querySelectorAll('li'),ix=['party','items','inn','grottos','records','dlc','misc','hex'].indexOf(tab);if(ix>=0&&li[ix]){li[ix].click();return;}}
if(++t<60)setTimeout(w,200);})();}
function loadSave(){var inp=document.getElementById('file-input');if(!inp){if(++tries<100)setTimeout(loadSave,200);return;}
var x=new XMLHttpRequest();x.open('GET','/__save');x.setRequestHeader('X-Token',T);x.responseType='blob';
x.onload=function(){if(x.status!=200){note('No game save found: choose a file yourself.',true);return;}
var dt=new DataTransfer();dt.items.add(new File([x.response],'dqix.sav'));inp.files=dt.files;inp.dispatchEvent(new Event('change',{bubbles:true}));gotoTab();};x.send();}
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
            r.Timeout = 15000; r.UserAgent = "dqix-cheat-menu";
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

        /* the editor's item names in the game's own words (read from the ROM into mods/lang/rom-itemname-<lang>.tsv) */
        public Func<string> LangOf;
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


        /* ---- the editor's own texts in the chosen language: ROM glossary (monsters, vocations, accolades, menu words...) + mods\lang\editor.tsv ---- */
        const string TranslatorJs = @"<script>(function(){var D=window.__DQIX_TR;if(!D)return;
function nk(s){var a=s.toLowerCase().replace(/[^a-z0-9]/g,'');return a?a+(/:\s*$/.test(s)?':':''):'';}
function one(s){var k=nk(s);if(!k)return null;if(Object.prototype.hasOwnProperty.call(D,k))return D[k];
var m=s.match(/^(.*?)(\s+L?\d+)$/);if(m){k=nk(m[1]);if(k&&Object.prototype.hasOwnProperty.call(D,k))return D[k]+m[2];}return null;}
function tr(s){var m=s.match(/^(\s*)([\s\S]*?)(\s*)$/),t=m[2];if(!t||!/[A-Za-z]{2}/.test(t))return s;var r=one(t);
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
            return "<script>window.__DQIX_TR=" + json + ";</script>" + TranslatorJs;
        }

        void Handle(HttpListenerContext c)
        {
            try
            {
                string path = c.Request.Url.AbsolutePath;
                if (path == "/") { c.Response.Redirect("/editor/"); c.Response.Close(); return; }
                if (path == "/__save" && c.Request.HttpMethod == "GET")
                {
                    if (!Allowed(c)) { Say(c, 403, "No."); return; }
                    if (!File.Exists(savePath)) { Say(c, 404, "No save."); return; }
                    byte[] sav;
                    using (FileStream fs = new FileStream(savePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    using (MemoryStream m = new MemoryStream()) { fs.CopyTo(m); sav = m.ToArray(); }
                    Reply(c, 200, "application/octet-stream", sav);
                    return;
                }
                if (path == "/__export" && c.Request.HttpMethod == "POST")
                {
                    if (!Allowed(c)) { Say(c, 403, "No."); return; }
                    if (gameRunning()) { Say(c, 409, "The game is running. Close it first, then press export again: a save written under a running game is lost."); return; }
                    byte[] body;
                    using (MemoryStream m = new MemoryStream()) { c.Request.InputStream.CopyTo(m); body = m.ToArray(); }
                    long want = File.Exists(savePath) ? new FileInfo(savePath).Length : 65536;
                    if (body.Length != want) { Say(c, 400, "That isn't a save of this size (" + body.Length + " bytes, expected " + want + "). Nothing was written."); return; }
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
                        string inj = Inject.Replace("@T@", token) + TrScript(LangOf != null ? LangOf() : "en");
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

    class MainWindow : Window
    {
        const string Xaml = @"
<Grid xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'
      TextElement.FontFamily='Segoe UI, Segoe UI Symbol' TextElement.Foreground='#D2D2D6' TextOptions.TextFormattingMode='Display' UseLayoutRounding='True'>
  <Grid.Resources>
    <SolidColorBrush x:Key='Dim' Color='#8C8C92'/>
    <SolidColorBrush x:Key='Gold' Color='#C8413B'/>
    <Style x:Key='Switch' TargetType='CheckBox'>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='Focusable' Value='True'/>
      <Setter Property='FocusVisualStyle' Value='{x:Null}'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='CheckBox'>
            <Border x:Name='track' Width='32' Height='16' CornerRadius='2' Background='#121214' BorderBrush='#34343A' BorderThickness='1'>
              <Border x:Name='knob' CornerRadius='1' Width='10' Height='10' Margin='3,0,3,0' Background='#6E6E75' HorizontalAlignment='Left'/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsChecked' Value='True'>
                <Setter TargetName='track' Property='Background' Value='#C8413B'/>
                <Setter TargetName='track' Property='BorderBrush' Value='#C8413B'/>
                <Setter TargetName='knob' Property='Background' Value='#FFFFFF'/>
                <Setter TargetName='knob' Property='HorizontalAlignment' Value='Right'/>
              </Trigger>
              <Trigger Property='IsMouseOver' Value='True'>
                <Setter TargetName='track' Property='BorderBrush' Value='#C8413B'/>
              </Trigger>
              <Trigger Property='IsKeyboardFocused' Value='True'>
                <Setter TargetName='track' Property='BorderBrush' Value='#FFFFFF'/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style x:Key='Btn' TargetType='Button'>
      <Setter Property='Foreground' Value='#D2D2D6'/>
      <Setter Property='FontSize' Value='11'/>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='Padding' Value='14,7'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='Button'>
            <Border x:Name='b' Background='#202024' BorderBrush='#2E2E33' BorderThickness='1' CornerRadius='2' Padding='{TemplateBinding Padding}'>
              <ContentPresenter HorizontalAlignment='Center' VerticalAlignment='Center'/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='BorderBrush' Value='#C8413B'/><Setter TargetName='b' Property='Background' Value='#2B2B30'/></Trigger>
              <Trigger Property='IsPressed' Value='True'><Setter TargetName='b' Property='Background' Value='#101012'/></Trigger>
              <Trigger Property='IsEnabled' Value='False'><Setter TargetName='b' Property='Opacity' Value='0.45'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style x:Key='Primary' TargetType='Button' BasedOn='{StaticResource Btn}'>
      <Setter Property='Foreground' Value='#FFFFFF'/>
      <Setter Property='FontWeight' Value='SemiBold'/>
      <Setter Property='FontSize' Value='12'/>
      <Setter Property='Padding' Value='22,9'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='Button'>
            <Border x:Name='b' CornerRadius='2' Padding='{TemplateBinding Padding}' BorderBrush='#C8413B' BorderThickness='1'>
              <Border.Background><SolidColorBrush Color='#B63A34'/></Border.Background>
              <ContentPresenter HorizontalAlignment='Center' VerticalAlignment='Center'/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='BorderBrush' Value='#FFFFFF'/></Trigger>
              <Trigger Property='IsPressed' Value='True'><Setter TargetName='b' Property='Opacity' Value='0.8'/></Trigger>
              <Trigger Property='IsEnabled' Value='False'><Setter TargetName='b' Property='Opacity' Value='0.4'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style TargetType='ComboBoxItem'>
      <Setter Property='Foreground' Value='#D2D2D6'/>
      <Setter Property='FontSize' Value='11'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='ComboBoxItem'>
            <Border x:Name='b' Padding='10,7' CornerRadius='2' Background='Transparent'>
              <ContentPresenter/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsHighlighted' Value='True'><Setter TargetName='b' Property='Background' Value='#26262B'/></Trigger>
              <Trigger Property='IsSelected' Value='True'><Setter Property='Foreground' Value='#C8413B'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style TargetType='ComboBox'>
      <Setter Property='Foreground' Value='#D2D2D6'/>
      <Setter Property='FontSize' Value='11'/>
      <Setter Property='Width' Value='180'/>
      <Setter Property='Height' Value='28'/>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='FocusVisualStyle' Value='{x:Null}'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='ComboBox'>
            <Grid>
              <ToggleButton Focusable='False' ClickMode='Press' IsChecked='{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}'>
                <ToggleButton.Template>
                  <ControlTemplate TargetType='ToggleButton'>
                    <Border x:Name='b' Background='#121214' BorderBrush='#2E2E33' BorderThickness='1.5' CornerRadius='2'>
                      <Path HorizontalAlignment='Right' VerticalAlignment='Center' Margin='0,0,12,0' Data='M0,0 L5,5 L10,0' Stroke='#C8413B' StrokeThickness='2'/>
                    </Border>
                    <ControlTemplate.Triggers>
                      <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='BorderBrush' Value='#C8413B'/></Trigger>
                    </ControlTemplate.Triggers>
                  </ControlTemplate>
                </ToggleButton.Template>
              </ToggleButton>
              <ContentPresenter IsHitTestVisible='False' Margin='12,0,30,0' VerticalAlignment='Center' Content='{TemplateBinding SelectionBoxItem}'/>
              <Popup x:Name='PART_Popup' IsOpen='{Binding IsDropDownOpen, RelativeSource={RelativeSource TemplatedParent}}' Placement='Bottom' AllowsTransparency='True' Focusable='False' PopupAnimation='Fade'>
                <Border MinWidth='{TemplateBinding ActualWidth}' MaxHeight='330' Background='#17171A' BorderBrush='#C8413B' BorderThickness='1' CornerRadius='2' Margin='0,4,0,8' Padding='4'>
                  <ScrollViewer VerticalScrollBarVisibility='Auto'><ItemsPresenter/></ScrollViewer>
                </Border>
              </Popup>
            </Grid>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style TargetType='ScrollBar'>
      <Setter Property='Width' Value='10'/>
      <Setter Property='Background' Value='Transparent'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='ScrollBar'>
            <Track x:Name='PART_Track' IsDirectionReversed='True'>
              <Track.Thumb>
                <Thumb>
                  <Thumb.Template>
                    <ControlTemplate TargetType='Thumb'><Border Background='#2E2E33' CornerRadius='4' Margin='2,0,2,0'/></ControlTemplate>
                  </Thumb.Template>
                </Thumb>
              </Track.Thumb>
            </Track>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style x:Key='Nav' TargetType='ListBoxItem'>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='FocusVisualStyle' Value='{x:Null}'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='ListBoxItem'>
            <Border x:Name='b' CornerRadius='0' Padding='10,5' Margin='0,0' Background='Transparent' BorderThickness='2,0,0,0' BorderBrush='Transparent'>
              <ContentPresenter/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='Background' Value='#1D1D21'/></Trigger>
              <Trigger Property='IsSelected' Value='True'><Setter TargetName='b' Property='Background' Value='#1D1D21'/><Setter TargetName='b' Property='BorderBrush' Value='#C8413B'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
  </Grid.Resources>
  <Grid.Background>
    <LinearGradientBrush StartPoint='0,0' EndPoint='1,1'><GradientStop Color='#0E0E10' Offset='0'/><GradientStop Color='#1B1B1F' Offset='1'/></LinearGradientBrush>
  </Grid.Background>
  <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='*'/><RowDefinition Height='Auto'/></Grid.RowDefinitions>

  <Border Grid.Row='0' Padding='16,9,16,8' BorderBrush='#26262B' BorderThickness='0,0,0,1'>
    <Grid>
      <StackPanel Margin='0,0,330,0'>
        <TextBlock FontSize='14' FontWeight='SemiBold'><Run Text='Dragon Quest IX'/><Run x:Name='TitleSub' Foreground='#8C8C92' FontWeight='Normal' Text='  /  cheats'/></TextBlock>
        <TextBlock x:Name='Sub' Visibility='Collapsed' Margin='0,3,0,0' FontSize='10' Foreground='{StaticResource Dim}' TextTrimming='CharacterEllipsis'/>
      </StackPanel>
      <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Center'>
      <Border x:Name='Pill' VerticalAlignment='Center' CornerRadius='0' Padding='0' Margin='0,0,14,0'>
        <StackPanel Orientation='Horizontal'>
          <Ellipse x:Name='Dot' Width='9' Height='9' Fill='#6E6E75' VerticalAlignment='Center' Margin='0,0,8,0'/>
          <TextBlock x:Name='PillText' FontSize='10.5' Text='The game is not running'/>
        </StackPanel>
      </Border>
      <ComboBox x:Name='LangBox' Width='112' Height='26' FontSize='10.5' VerticalAlignment='Center'/>
      </StackPanel>
    </Grid>
  </Border>

  <Grid Grid.Row='1'>
    <Grid.ColumnDefinitions><ColumnDefinition Width='200'/><ColumnDefinition Width='*'/></Grid.ColumnDefinitions>
    <Border Grid.Column='0' BorderBrush='#26262B' BorderThickness='0,0,1,0' Padding='10,10,6,6'>
      <DockPanel>
        <Border DockPanel.Dock='Top' Background='#121214' BorderBrush='#2E2E33' BorderThickness='1.5' CornerRadius='2' Margin='0,0,4,10'>
          <Grid>
            <TextBlock x:Name='SearchHint' Text='Search all cheats' Foreground='#6E6E75' Margin='11,0,0,0' VerticalAlignment='Center' IsHitTestVisible='False' FontSize='11'/>
            <TextBox x:Name='Search' Background='Transparent' BorderThickness='0' Foreground='#D2D2D6' CaretBrush='#C8413B' Padding='8,7' FontSize='11'/>
          </Grid>
        </Border>
        <ListBox x:Name='Nav' Margin='0,0,2,0' Background='Transparent' BorderThickness='0' ItemContainerStyle='{StaticResource Nav}' ScrollViewer.HorizontalScrollBarVisibility='Disabled' Foreground='#D2D2D6'/>
      </DockPanel>
    </Border>
    <Grid Grid.Column='1'>
      <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='*'/></Grid.RowDefinitions>
      <Border x:Name='Banner' Grid.Row='0' Margin='14,10,14,0' Padding='10,7' CornerRadius='4' Background='#2B1618' BorderBrush='#C8413B' BorderThickness='1' Visibility='Collapsed'>
        <DockPanel>
          <Button x:Name='ApplyBtn' DockPanel.Dock='Right' Style='{StaticResource Btn}' Content='Rebuild now' Margin='12,0,0,0' VerticalAlignment='Center'/>
          <TextBlock x:Name='BannerText' TextWrapping='Wrap' VerticalAlignment='Center' FontSize='11'/>
        </DockPanel>
      </Border>
      <ScrollViewer x:Name='Scroll' Grid.Row='1' VerticalScrollBarVisibility='Auto' Padding='14,8,8,8' Focusable='False'>
        <StackPanel x:Name='Rows'/>
      </ScrollViewer>
    </Grid>
  </Grid>

  <Border Grid.Row='2' Padding='16,7' BorderBrush='#26262B' BorderThickness='0,1,0,0' Background='#0E0E10'>
    <DockPanel>
      <StackPanel DockPanel.Dock='Right' Orientation='Horizontal'>
        <Button x:Name='OffBtn' Style='{StaticResource Btn}' Content='Everything off' Margin='0,0,8,0'/>
        <Button x:Name='ReloadBtn' Style='{StaticResource Btn}' Content='Reload list' Margin='0,0,14,0'/>
        <Button x:Name='PlayBtn' Style='{StaticResource Primary}' Content='Play'/>
      </StackPanel>
      <TextBlock x:Name='Status' VerticalAlignment='Center' TextWrapping='Wrap' FontSize='11' Foreground='{StaticResource Dim}' Margin='0,0,16,0'/>
    </DockPanel>
  </Border>

  <Grid x:Name='Overlay' Grid.RowSpan='3' Background='#E6000000' Visibility='Collapsed'>
    <Border Width='620' MaxHeight='460' Padding='16' CornerRadius='2' Background='#1B1B1F' BorderBrush='#C8413B' BorderThickness='1.5' VerticalAlignment='Center'>
      <DockPanel>
        <TextBlock x:Name='OverTitle' DockPanel.Dock='Top' FontSize='15.5' FontWeight='SemiBold' Text='Getting the game ready'/>
        <TextBlock x:Name='OverSub' DockPanel.Dock='Top' Margin='0,4,0,12' FontSize='11' Foreground='{StaticResource Dim}' TextWrapping='Wrap'/>
        <ProgressBar x:Name='OverBar' DockPanel.Dock='Top' Height='6' IsIndeterminate='True' Foreground='#C8413B' Background='#121214' BorderThickness='0' Margin='0,0,0,12'/>
        <Button x:Name='OverClose' DockPanel.Dock='Bottom' Style='{StaticResource Btn}' Content='Close' HorizontalAlignment='Right' Margin='0,12,0,0' Visibility='Collapsed'/>
        <Border Background='#0E0E10' CornerRadius='2' Padding='10' BorderBrush='#26262B' BorderThickness='1'>
          <ScrollViewer x:Name='OverScroll' VerticalScrollBarVisibility='Auto' Height='220'>
            <TextBlock x:Name='OverLog' FontFamily='@FONT@' FontSize='10.5' Foreground='#A9A9B0' TextWrapping='Wrap'/>
          </ScrollViewer>
        </Border>
      </DockPanel>
    </Border>
  </Grid>
</Grid>";

        readonly string root, mods, gameDir;
        string infoTitle = "", infoGame = "", infoDatabase = "";
        bool infoExact;
        List<Entry> entries = new List<Entry>();
        List<Group> groups = new List<Group>();
        List<string> pages = new List<string>();
        readonly HashSet<string> liveOn = new HashSet<string>(), codeOn = new HashSet<string>(), launchOn = new HashSet<string>(), flags = new HashSet<string>();
        HashSet<string> built = new HashSet<string>();
        bool builtKnown;
        readonly GameLink link = new GameLink();
        readonly DispatcherTimer timer = new DispatcherTimer();
        bool building, busy;
        string lastPill = "";
        const int MaxLive = 120;

        ComboBox LangBox;
        Run TitleSub;
        TextBlock Sub, PillText, Status, BannerText, SearchHint, OverTitle, OverSub, OverLog;
        System.Windows.Shapes.Ellipse Dot;
        TextBox Search;
        ListBox Nav;
        Border Banner;
        StackPanel Rows;
        ScrollViewer Scroll, OverScroll;
        Button ApplyBtn, OffBtn, ReloadBtn, PlayBtn, OverClose;
        Grid Overlay;
        ProgressBar OverBar;
        FrameworkElement ui;

        static Brush B(string hex) { Brush b = (Brush)new BrushConverter().ConvertFromString(hex); b.Freeze(); return b; }
        static readonly Brush Dim = B("#8C8C92"), Gold = B("#C8413B"), Text = B("#D2D2D6"), Card = B("#18181B"), CardLine = B("#26262B"),
            Green = B("#5CCB7B"), Amber = B("#FFB000"), Blue = B("#5AB4E6"), Grey = B("#6E6E75"), Red = B("#FF5050");

        public MainWindow(string rootDir)
        {
            root = rootDir;
            mods = Path.Combine(root, "mods");
            gameDir = Path.Combine(root, "game");
            Title = "Dragon Quest IX - cheat menu";
            Width = 880; Height = 600; MinWidth = 680; MinHeight = 420;
            Background = B("#0E0E10");
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            try
            {
                string ico = Path.Combine(root, "build", "icon", "dqix.ico");
                if (File.Exists(ico)) Icon = System.Windows.Media.Imaging.BitmapFrame.Create(new Uri(ico));
            }
            catch (Exception) { }

            /* JetBrains Mono from modsonts (falls back to Consolas / symbols if the files are missing) */
            string fontDir = Path.Combine(mods, "fonts");
            string fontName = File.Exists(Path.Combine(fontDir, "JetBrainsMono-Regular.ttf"))
                ? new Uri(fontDir.TrimEnd('\\') + "\\").AbsoluteUri + "#JetBrains Mono, Consolas, Segoe UI Symbol"
                : "Consolas, Segoe UI Symbol";
            try { Mono = new FontFamily(fontName); } catch (Exception) { }
            ui = (FrameworkElement)XamlReader.Parse(Xaml.Replace("@FONT@", fontName));
            Content = ui;
            Sub = F<TextBlock>("Sub"); PillText = F<TextBlock>("PillText"); Status = F<TextBlock>("Status"); BannerText = F<TextBlock>("BannerText");
            SearchHint = F<TextBlock>("SearchHint"); OverTitle = F<TextBlock>("OverTitle"); OverSub = F<TextBlock>("OverSub"); OverLog = F<TextBlock>("OverLog");
            Dot = F<System.Windows.Shapes.Ellipse>("Dot"); Search = F<TextBox>("Search"); Nav = F<ListBox>("Nav"); Banner = F<Border>("Banner");
            Rows = F<StackPanel>("Rows"); Scroll = F<ScrollViewer>("Scroll"); OverScroll = F<ScrollViewer>("OverScroll");
            ApplyBtn = F<Button>("ApplyBtn"); OffBtn = F<Button>("OffBtn"); ReloadBtn = F<Button>("ReloadBtn"); PlayBtn = F<Button>("PlayBtn"); OverClose = F<Button>("OverClose");
            Overlay = F<Grid>("Overlay"); OverBar = F<ProgressBar>("OverBar");
            LangBox = F<ComboBox>("LangBox"); TitleSub = ui.FindName("TitleSub") as Run;
            string langFile = Path.Combine(mods, "menu-lang.txt");
            string lang = Tr.Detect();
            try { if (File.Exists(langFile)) { string l = File.ReadAllText(langFile).Trim(); if (Array.IndexOf(Tr.Codes, l) >= 0) lang = l; } } catch (Exception) { }
            Tr.Load(Path.Combine(mods, "lang"), lang);
            for (int li = 0; li < Tr.Codes.Length; li++) { ComboBoxItem ci = new ComboBoxItem { Content = Tr.Names[li], Tag = Tr.Codes[li] }; LangBox.Items.Add(ci); if (Tr.Codes[li] == lang) LangBox.SelectedItem = ci; }
            LangBox.SelectionChanged += delegate
            {
                ComboBoxItem it = LangBox.SelectedItem as ComboBoxItem;
                if (it == null || (string)it.Tag == Tr.Lang) return;
                Tr.Load(Path.Combine(mods, "lang"), (string)it.Tag);
                try { File.WriteAllText(langFile, (string)it.Tag); } catch (Exception) { }
                ApplyLang();
                LoadAll();
            };
            ApplyLang();

            Search.TextChanged += delegate { SearchHint.Visibility = Search.Text.Length > 0 ? Visibility.Collapsed : Visibility.Visible; ShowPage(); };
            Nav.SelectionChanged += delegate { if (!building) { if (Search.Text.Length > 0 && Nav.SelectedIndex >= 0) { building = true; Search.Text = ""; building = false; SearchHint.Visibility = Visibility.Visible; } ShowPage(); } };
            PlayBtn.Click += delegate { Play(); };
            ApplyBtn.Click += delegate { RunApply(false); };
            ReloadBtn.Click += delegate { RunCatalog(); };
            OffBtn.Click += delegate { EverythingOff(); };
            OverClose.Click += delegate { Overlay.Visibility = Visibility.Collapsed; };

            link.GameDir = gameDir;
            link.LiveOn = delegate { return entries.Where(e => e.Kind == "live" && liveOn.Contains(e.Id)); };
            LoadAll();
            timer.Interval = TimeSpan.FromMilliseconds(16);
            timer.Tick += delegate { link.Tick(); UpdatePill(); };
            timer.Start();
            Closed += delegate { timer.Stop(); link.Dispose(); if (editor != null) editor.Dispose(); };
        }

        void ApplyLang()
        {
            Title = "Dragon Quest IX - " + Tr.T("cheat menu");
            if (TitleSub != null) TitleSub.Text = "  /  " + Tr.T("cheats");
            SearchHint.Text = Tr.T("Search all cheats");
            OffBtn.Content = Tr.T("Everything off"); ReloadBtn.Content = Tr.T("Reload list"); ApplyBtn.Content = Tr.T("Rebuild now"); OverClose.Content = Tr.T("Close");
            PlayBtn.Content = Tr.T(link.Running ? "Game is running" : "Play");
            lastPill = "";
        }

        /* tests: DQIX_MENU_STATE points at another state file, so the user's own is never touched */
        string StatePath() { string o = Environment.GetEnvironmentVariable("DQIX_MENU_STATE"); return !string.IsNullOrEmpty(o) ? o : Path.Combine(mods, "menu-state.txt"); }

        T F<T>(string name) where T : class { return ui.FindName(name) as T; }

        /* ---------------------------------------------------------------- the list and what is on */
        static Dictionary<string, string> Fields(string line, out string kind)
        {
            string[] p = line.Split('\t');
            kind = p[0];
            Dictionary<string, string> d = new Dictionary<string, string>();
            for (int i = 1; i < p.Length; i++)
            {
                int eq = p[i].IndexOf('=');
                if (eq > 0) d[p[i].Substring(0, eq)] = p[i].Substring(eq + 1);
            }
            return d;
        }
        static string G(Dictionary<string, string> d, string k) { string v; return d.TryGetValue(k, out v) ? v : ""; }

        void LoadAll()
        {
            entries = new List<Entry>(); groups = new List<Group>(); pages = new List<string>();
            string path = Path.Combine(mods, "bin", "catalog.txt");
            if (File.Exists(path))
                foreach (string line in File.ReadAllLines(path, Encoding.UTF8))
                {
                    string kind;
                    Dictionary<string, string> d = Fields(line, out kind);
                    if (kind == "info") { infoTitle = G(d, "title"); infoGame = G(d, "game"); infoDatabase = G(d, "database"); infoExact = G(d, "exact") == "1"; }
                    else if (kind == "page") pages.Add(G(d, "title"));
                    else if (kind == "group") groups.Add(new Group { Id = G(d, "id"), Cat = G(d, "cat"), Title = G(d, "title"), Note = G(d, "note"), Kind = G(d, "kind") });
                    else if (kind == "entry")
                    {
                        Entry e = new Entry
                        {
                            Id = G(d, "id"), Cat = G(d, "cat"), Group = G(d, "group"), Kind = G(d, "kind"), Status = G(d, "status"), Name = G(d, "name"),
                            Option = G(d, "option"), Note = G(d, "note"), Reason = G(d, "reason"), Mode = G(d, "mode"), Keys = G(d, "keys"),
                            File = G(d, "file"), Env = G(d, "env"), FileOn = G(d, "on") == "1", Index = entries.Count
                        };
                        int.TryParse(G(d, "combos"), out e.Combos);
                        try
                        {
                            string ops = G(d, "ops");
                            if (ops.Length > 0)
                            {
                                string[] parts = ops.Split(',');
                                e.Ops = new uint[parts.Length * 2];
                                for (int i = 0; i < parts.Length; i++)
                                {
                                    string[] ab = parts[i].Split(':');
                                    e.Ops[i * 2] = Convert.ToUInt32(ab[0], 16); e.Ops[i * 2 + 1] = Convert.ToUInt32(ab[1], 16);
                                }
                            }
                            foreach (string pt in G(d, "patch").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
                            {
                                string[] f = pt.Split(':');
                                e.Patch.Add(new KeyValuePair<string, uint>(f[0] + ":" + f[1], Convert.ToUInt32(f[2], 16)));
                            }
                        }
                        catch (Exception) { e.Kind = "blocked"; e.Status = "blocked"; e.Reason = "The cheat list has a line for it that can't be read."; }
                        if (e.Option.Length == 0) e.Option = e.Name;
                        entries.Add(e);
                    }
                }
            foreach (Group g in groups) g.Items = entries.Where(e => e.Group == g.Id).ToList();
            groups = groups.Where(g => g.Items.Count > 0).ToList();

            liveOn.Clear(); codeOn.Clear(); launchOn.Clear(); flags.Clear();
            string st = StatePath();
            if (File.Exists(st))
            {
                foreach (string line in File.ReadAllLines(st, Encoding.UTF8))
                {
                    string[] p = line.Split(new[] { ' ' }, 2);
                    if (p.Length < 2) continue;
                    string v = p[1].Trim();
                    if (p[0] == "live") liveOn.Add(v); else if (p[0] == "code") codeOn.Add(v); else if (p[0] == "launch") launchOn.Add(v); else if (p[0] == "flag") flags.Add(v);
                }
            }
            else
            {
                /* the old cheat window kept what was on in mods\cheats\on.txt */
                string old = Path.Combine(mods, "cheats", "on.txt");
                if (File.Exists(old))
                    foreach (string line in File.ReadAllLines(old))
                        if (line.Trim().Length > 0 && !line.StartsWith("#")) liveOn.Add("file:cheats/" + line.Trim());
            }
            HashSet<string> known = new HashSet<string>(entries.Select(e => e.Id));
            liveOn.RemoveWhere(id => !entries.Any(e => e.Id == id && e.Kind == "live" && e.Mode != "once"));
            codeOn.RemoveWhere(id => !entries.Any(e => e.Id == id && e.Kind == "code" && e.File.Length == 0));
            launchOn.RemoveWhere(id => !known.Contains(id));
            /* of a choice, only one */
            foreach (Group g in groups)
            {
                bool one = false;
                foreach (Entry e in g.Items)
                    if (IsOn(e)) { if (one) Store(e, false); one = true; }
            }
            ReadBuilt();

            int nNo = entries.Count(e => e.Kind == "blocked");
            ShowSub();
            if (entries.Count == 0) Say(Tr.T("No cheat list yet: start with \"Play with mods.bat\" (it makes the list from your ROM)."));

            building = true;
            string was = Nav.SelectedItem is ListBoxItem ? (string)((ListBoxItem)Nav.SelectedItem).Tag : "page:" + (pages.Count > 0 ? pages[0] : "");
            Nav.Items.Clear();
            AddNav("on", Tr.T("Switched on"), 0);
            foreach (string p in pages) AddNav("page:" + p, p, RowCount(e => e.Cat == p && e.Kind != "blocked"));
            AddNav("all", Tr.T("All cheats"), RowCount(e => e.Kind != "blocked"));
            AddNav("blocked", Tr.T("Not available"), nNo);
            AddNav("tool:save", Tr.T("Save editor"), 0);
            AddNav("tool:maps", Tr.T("Treasure maps"), 0);
            foreach (ListBoxItem it in Nav.Items) if ((string)it.Tag == was) Nav.SelectedItem = it;
            if (Nav.SelectedIndex < 0 && Nav.Items.Count > 1) Nav.SelectedIndex = 1;
            building = false;
            ShowPage();
            UpdateBanner();
            link.ClearAll();
        }

        /* a choice is one row */
        int RowCount(Func<Entry, bool> fits)
        {
            return entries.Where(fits).Select(e => e.Group.Length > 0 ? e.Group : e.Id).Distinct().Count();
        }

        void AddNav(string tag, string title, int count)
        {
            DockPanel d = new DockPanel();
            if (count > 0)
            {
                TextBlock c = new TextBlock { Text = count.ToString(), Foreground = Grey, FontSize = 10, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(4, 0, 0, 0) };
                DockPanel.SetDock(c, Dock.Right);
                d.Children.Add(c);
            }
            d.Children.Add(new TextBlock { Text = Tr.T(title), FontSize = 11, TextTrimming = TextTrimming.CharacterEllipsis, Foreground = tag == "on" ? Gold : Text });
            Nav.Items.Add(new ListBoxItem { Content = d, Tag = tag });
        }

        /* a short name for what is built into the game: friends compare it ("we both have set 3F2A") */
        string SetCode()
        {
            uint h = 2166136261;
            foreach (string id in built.OrderBy(x => x, StringComparer.Ordinal))
                foreach (char c in id + "\n") { h ^= c; h *= 16777619; }
            return ((h >> 16) ^ (h & 0xFFFF)).ToString("X4");
        }

        void ShowSub()
        {
            int nLive = entries.Count(e => e.Kind == "live"), nCode = entries.Count(e => e.Kind == "code"), nNo = entries.Count(e => e.Kind == "blocked");
            Sub.Text = (infoTitle.Length > 0 ? infoTitle : "Your own cheats") + "   ·   " + nLive + " live  ·  " + nCode + " built into the game  ·  " + nNo + " not available"
                + (infoDatabase.Length > 0 && !infoExact ? "   ·   list for " + infoGame + " (another dump of it)" : "")
                + (built.Count > 0 ? "   ·   built-in set " + SetCode() + " (friends need the same)" : "");
        }

        bool CardGuard()
        {
            try { return File.ReadAllText(Path.Combine(root, "runtime", "card.c")).Contains(">>> mods: instant loading"); }
            catch (Exception) { return false; }
        }

        void ReadBuilt()
        {
            built = new HashSet<string>(); builtKnown = false;
            string p = Path.Combine(mods, "bin", "built.txt");
            if (!File.Exists(p)) return;
            builtKnown = true;
            foreach (string line in File.ReadAllLines(p))
                if (line.StartsWith("code ")) built.Add(line.Substring(5).Trim());
        }

        void SaveState()
        {
            try
            {
                StringBuilder sb = new StringBuilder("# What is switched on in the cheat menu (written by it; apply_code_mods.py reads the \"code\" lines)\n");
                foreach (string id in liveOn.OrderBy(s => s)) sb.Append("live ").Append(id).Append('\n');
                foreach (string id in codeOn.OrderBy(s => s)) sb.Append("code ").Append(id).Append('\n');
                foreach (string id in launchOn.OrderBy(s => s)) sb.Append("launch ").Append(id).Append('\n');
                foreach (string id in flags.OrderBy(s => s)) sb.Append("flag ").Append(id).Append('\n');
                string path = StatePath(), tmp = path + ".tmp";
                File.WriteAllText(tmp, sb.ToString(), new UTF8Encoding(false));
                if (File.Exists(path)) File.Replace(tmp, path, null); else File.Move(tmp, path);
            }
            catch (Exception ex) { Say(Tr.F("Couldn't save what is on: {0}", ex.Message)); }
        }

        bool IsOn(Entry e)
        {
            if (e.Kind == "live") return liveOn.Contains(e.Id);
            if (e.Kind == "code") return e.File.Length > 0 ? e.FileOn : codeOn.Contains(e.Id);
            if (e.Kind == "launch") return launchOn.Contains(e.Id);
            return false;
        }

        /* only writes it down */
        bool Store(Entry e, bool on)
        {
            if (e.Kind == "live") { if (on) liveOn.Add(e.Id); else liveOn.Remove(e.Id); }
            else if (e.Kind == "launch") { if (on) launchOn.Add(e.Id); else launchOn.Remove(e.Id); }
            else if (e.Kind == "code")
            {
                if (e.File.Length == 0) { if (on) codeOn.Add(e.Id); else codeOn.Remove(e.Id); }
                else
                {
                    /* a file in mods\code says itself whether it is on */
                    try
                    {
                        string path = Path.Combine(mods, e.File.Replace('/', Path.DirectorySeparatorChar));
                        string text = File.ReadAllText(path);
                        Regex rx = new Regex(@"^(#\s*enabled\s*:\s*)\S+", RegexOptions.IgnoreCase | RegexOptions.Multiline);
                        string now = rx.IsMatch(text) ? rx.Replace(text, "${1}" + (on ? "yes" : "no"), 1) : "# enabled: " + (on ? "yes" : "no") + "\r\n" + text;
                        if (now != text) File.WriteAllText(path, now, new UTF8Encoding(false));
                        e.FileOn = on;
                    }
                    catch (Exception ex) { Say(Tr.F("Couldn't change {0}: {1}", e.File, ex.Message)); return false; }
                }
            }
            return true;
        }

        void WarnOnce(Entry e)
        {
            if (e.Status != "untested" || flags.Contains("warned")) return;
            flags.Add("warned");
            SaveState();
            MessageBox.Show(this,
                Tr.F("\"{0}\" comes from the R4 cheat list and hasn't been tried in this version of the game.", Tr.T(e.Name)) + "\n\n" +
                Tr.T("Such codes were checked as far as a program can check them, but a code that changes the wrong data can still spoil a save. A copy of your save is kept each time you press Play here (mods\\save-backups).") + "\n\n" + Tr.T("This is only said once."),
                Tr.T("Untested cheats"), MessageBoxButton.OK, MessageBoxImage.Information);
        }

        /* a switch was flipped */
        void Turn(Entry e, bool on)
        {
            if (IsOn(e) == on) return;
            if (on && e.Kind == "live" && liveOn.Count >= MaxLive) { Say(Tr.F("That is the most live cheats that can be on at once ({0}). Switch one off first.", MaxLive)); ShowPage(); return; }
            if (on) WarnOnce(e);
            bool redraw = false;
            if (on && e.Kind == "code")
            {
                /* two mods can't change the same instruction in different ways */
                foreach (Entry o in entries)
                {
                    if (o == e || o.Kind != "code" || !IsOn(o)) continue;
                    bool clash = false;
                    foreach (KeyValuePair<string, uint> a in e.Patch)
                        foreach (KeyValuePair<string, uint> b in o.Patch)
                            if (a.Key == b.Key && a.Value != b.Value) clash = true;
                    if (clash) { Store(o, false); redraw = true; Say(Tr.F("\"{0}\" was switched off: it changes the same place in the game as \"{1}\".", Tr.T(o.Name), Tr.T(e.Name))); }
                }
            }
            if (!Store(e, on)) { ShowPage(); return; }
            if (e.Kind == "live") link.Set(e, on);
            SaveState();
            UpdateBanner();
            if (!redraw)
            {
                if (e.Kind == "live") Say(Tr.T(e.Name) + ": " + Tr.T(on ? (link.Connected ? "on" : "on (starts with the game)") : "off"));
                else if (e.Kind == "launch") Say(Tr.F("{0}: {1} from the next time the game starts.", Tr.T(e.Name), Tr.T(on ? "on" : "off")));
                else Say(Tr.F("{0}: {1} once the game is rebuilt.", Tr.T(e.Name), Tr.T(on ? "on" : "off")));
            }
            if (redraw || CurrentTag() == "on") ShowPage();
        }

        void EverythingOff()
        {
            int n = entries.Count(e => IsOn(e));
            if (n == 0) { Say(Tr.T("Nothing is on.")); return; }
            bool hasCode = entries.Any(e => e.Kind == "code" && IsOn(e));
            if (MessageBox.Show(this, Tr.F("Switch all {0} off?", n) + (hasCode ? "\n\n" + Tr.T("The ones built into the game go away with the next rebuild.") : ""), Tr.T("Everything off"),
                    MessageBoxButton.OKCancel, MessageBoxImage.Question) != MessageBoxResult.OK) return;
            foreach (Entry e in entries) if (IsOn(e)) Store(e, false);
            link.ClearAll();
            SaveState();
            ShowPage();
            UpdateBanner();
            Say(Tr.T("Everything is off."));
        }

        HashSet<string> WantedCode() { return new HashSet<string>(entries.Where(e => e.Kind == "code" && IsOn(e)).Select(e => e.Id)); }
        bool Pending() { return !builtKnown ? WantedCode().Count > 0 : !WantedCode().SetEquals(built); }

        void UpdateBanner()
        {
            if (!Pending()) { Banner.Visibility = Visibility.Collapsed; return; }
            HashSet<string> want = WantedCode();
            int add = want.Count(id => !built.Contains(id)), del = built.Count(id => !want.Contains(id));
            BannerText.Inlines.Clear();
            BannerText.Inlines.Add(new Run(Tr.T("The game has to be rebuilt")) { FontWeight = FontWeights.SemiBold, Foreground = Gold });
            BannerText.Inlines.Add(new Run("  " + Tr.T("(a few minutes)") + "  —  " + (add > 0 ? Tr.F("{0} to put in", add) : "") + (add > 0 && del > 0 ? ", " : "") + (del > 0 ? Tr.F("{0} to take out", del) : "")
                + ". " + Tr.T("Play does it by itself.") + (link.Running ? "  " + Tr.T("Save and close the game first.") : "")));
            Banner.Visibility = Visibility.Visible;
        }

        /* ---------------------------------------------------------------- drawing */
        string CurrentTag() { return Nav.SelectedItem is ListBoxItem ? (string)((ListBoxItem)Nav.SelectedItem).Tag : "all"; }

        /* ---------------------------------------------------------------- save editor and treasure maps */
        EditorHost editor;

        void ShowTool(string tag)
        {
            bool save = tag == "tool:save";
            StackPanel hp = new StackPanel { Margin = new Thickness(2, 2, 0, 10) };
            hp.Children.Add(new TextBlock { Text = save ? Tr.T("Save editor") : Tr.T("Treasure maps"), FontSize = 14, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 5) });
            hp.Children.Add(new Border { Height = 1, Background = B("#8E2B27") });
            Rows.Children.Add(hp);

            StackPanel body = new StackPanel();
            body.Children.Add(new TextBlock
            {
                Text = save
                    ? Tr.T("Edit your save: party, items, inn, records, DLC and more. The editor opens in your browser with your game save already loaded.")
                    : Tr.T("The treasure maps (grottos) in your save: the list, their treasures and where they are. Adding, removing and the map preview are not finished in this editor yet, so check the result in the game and keep the backup."),
                Foreground = Dim, FontSize = 10.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12)
            });
            TextBlock status = new TextBlock { Foreground = Dim, FontSize = 10.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 0) };
            StackPanel buttons = new StackPanel { Orientation = Orientation.Horizontal };
            Button open = new Button { Content = save ? Tr.T("Open the save editor") : Tr.T("Open the treasure map editor"), Style = (Style)ui.FindResource("Primary") };
            string tab = save ? "party" : "grottos";
            open.Click += delegate { OpenTool(tab, null, status); };
            buttons.Children.Add(open);
            if (!save)
            {
                Button find = new Button { Content = Tr.T("Search all maps (website)"), Style = (Style)ui.FindResource("Btn"), Margin = new Thickness(10, 0, 0, 0) };
                find.Click += delegate { OpenTool(null, "https://dqix.github.io/Grotto-Searcher/", status); };
                buttons.Children.Add(find);
            }
            body.Children.Add(buttons);
            body.Children.Add(status);
            Rows.Children.Add(new Border { Background = Card, BorderBrush = CardLine, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(2), Padding = new Thickness(14, 11, 14, 12), Margin = new Thickness(0, 0, 6, 8), Child = body });

            string notes = Tr.T("How it works: press \"export\" in the editor to write the changes back; the old save is copied to mods\\save-backups first. Close the game before you export: a save written under a running game is lost.")
                + "\n" + Tr.T("The editor is the DQIX project's (github.com/dqix/editor, no license given). It is downloaded from dqix.github.io once, kept in mods\\bin\\editor-cache, and not part of this repo.")
                + (save ? "" : "\n" + Tr.T("The map search is the DQIX project's Grotto Searcher (CC BY-NC-SA), a separate website."));
            Rows.Children.Add(new TextBlock { Text = notes, Foreground = Grey, FontSize = 10, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(2, 0, 6, 0) });
        }

        void OpenTool(string tab, string url, TextBlock status)
        {
            if (url != null)
            {
                try { Process.Start(url); } catch (Exception ex) { status.Text = ex.Message; }
                return;
            }
            if (editor == null)
                editor = new EditorHost(Path.Combine(mods, "bin", "editor-cache"), Path.Combine(gameDir, "dqix.sav"), Path.Combine(mods, "save-backups"),
                    delegate { return Process.GetProcessesByName("dqix").Length > 0; });
            EditorHost host = editor;
            host.LangDir = Path.Combine(mods, "lang"); host.LangOf = delegate { return Tr.Lang; };
            status.Text = Tr.T("Getting the editor ready...");
            ThreadPool.QueueUserWorkItem(delegate
            {
                bool ok = host.Start() && host.Prepare();
                Dispatcher.BeginInvoke(new Action(delegate
                {
                    if (!ok) { status.Text = host.LastError; return; }
                    status.Text = Tr.T("Opened in your browser.");
                    try { Process.Start(host.Base + "#tab=" + tab); } catch (Exception ex) { status.Text = ex.Message; }
                }));
            });
        }

        void ShowPage()
        {
            if (building) return;
            building = true;
            Rows.Children.Clear();
            string tag = CurrentTag(), q = Search.Text.Trim().ToLowerInvariant();
            if (q.Length == 0 && tag.StartsWith("tool:")) { ShowTool(tag); Scroll.ScrollToTop(); building = false; return; }
            Func<Entry, bool> fits;
            string heading, sub = "";
            if (q.Length > 0)
            {
                string[] words = q.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                fits = delegate (Entry e)
                {
                    Group g = groups.FirstOrDefault(x => x.Id == e.Group);
                    string hay = (Tr.T(e.Name) + " " + e.Name + " " + e.Note + " " + e.Cat + " " + e.Keys + " " + e.Option + " " + (g != null ? g.Title : "")).ToLowerInvariant();
                    return words.All(w => hay.Contains(w));
                };
                heading = Tr.T("Search") + ": " + Search.Text.Trim();
            }
            else if (tag == "on") { fits = e => IsOn(e); heading = Tr.T("Switched on"); sub = Tr.T("Everything that is on now."); }
            else if (tag == "blocked") { fits = e => e.Kind == "blocked"; heading = Tr.T("Not available"); sub = Tr.T("Codes of the list that can't work in this version of the game, or can't be checked. They stay off, so they can't break anything."); }
            else if (tag == "all") { fits = e => e.Kind != "blocked"; heading = Tr.T("All cheats"); }
            else { string p = tag.Substring(5); fits = e => e.Cat == p; heading = p; }

            { StackPanel hp = new StackPanel { Margin = new Thickness(2, 2, 0, sub.Length > 0 ? 6 : 12) };
              hp.Children.Add(new TextBlock { Text = Tr.T(heading), FontSize = 14, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 5) });
              hp.Children.Add(new Border { Height = 1, Background = B("#8E2B27"), HorizontalAlignment = HorizontalAlignment.Stretch });
              Rows.Children.Add(hp); }
            if (sub.Length > 0) Rows.Children.Add(new TextBlock { Text = Tr.T(sub), Foreground = Dim, FontSize = 11, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(2, 0, 0, 10) });

            HashSet<string> doneGroups = new HashSet<string>();
            int shown = 0;
            List<Entry> late = new List<Entry>();
            foreach (Entry e in entries)
            {
                if (!fits(e)) continue;
                if (e.Kind == "blocked" && tag != "blocked") { late.Add(e); continue; }
                if (e.Group.Length > 0)
                {
                    if (!doneGroups.Add(e.Group)) continue;
                    Group g = groups.FirstOrDefault(x => x.Id == e.Group);
                    if (g != null) { Rows.Children.Add(GroupRow(g)); shown++; continue; }
                }
                Rows.Children.Add(EntryRow(e)); shown++;
            }
            if (late.Count > 0)
            {
                Rows.Children.Add(new TextBlock { Text = Tr.T("Not available here"), Foreground = Grey, FontSize = 10.5, FontWeight = FontWeights.SemiBold, Margin = new Thickness(2, 14, 0, 6) });
                foreach (Entry e in late) { Rows.Children.Add(EntryRow(e)); shown++; }
            }
            if (shown == 0)
                Rows.Children.Add(new TextBlock { Text = tag == "on" && q.Length == 0 ? Tr.T("Nothing is on. Pick a page on the left and flip a switch.") : Tr.T("Nothing here."), Foreground = Dim, FontSize = 11.5, Margin = new Thickness(2, 12, 0, 0) });
            Scroll.ScrollToTop();
            building = false;
        }

        static Border Chip(string text, Brush color, string tip)
        {
            Border b = new Border
            {
                Margin = new Thickness(0, 0, 8, 0), VerticalAlignment = VerticalAlignment.Center, Background = Brushes.Transparent,
                Child = new TextBlock { Text = text, Foreground = color, FontSize = 9.5, Opacity = 0.85 }
            };
            if (tip != null) { b.ToolTip = tip; ToolTipService.SetShowDuration(b, 30000); }
            return b;
        }

        static void StatusChips(Panel into, string kind, string status)
        {
            if (kind == "code") into.Children.Add(Chip(Tr.T("BUILT IN"), Blue, Tr.T("Changes how the game works, so it is built into the game: switching it takes a rebuild (a few minutes).\nEvery instruction it changes was found in your ROM first.")));
            if (kind == "launch") into.Children.Add(Chip(Tr.T("NEXT START"), Blue, Tr.T("Takes effect the next time the game starts from this menu.")));
            if (kind == "live") into.Children.Add(Chip(Tr.T("ONE PLAYER"), Dim, MpLive));
            else if (kind == "code") into.Children.Add(Chip(Tr.T("ALL PLAYERS"), Dim, MpCode));
            else if (kind == "launch") into.Children.Add(Chip(Tr.T("OWN PC"), Dim, MpLaunch));
            if (status == "tested") into.Children.Add(Chip(Tr.T("TRIED OUT"), Green, Tr.T("Tried in this version of the game.")));
            else if (status == "untested") into.Children.Add(Chip(Tr.T("UNTESTED"), Amber, Tr.T("From the R4 cheat list for your ROM. Checked as far as a program can, but not tried in this version: save first.")));
        }

        /* ---- hover info: what it is, how to use it, and when it works ---- */
        static FontFamily Mono = new FontFamily("Consolas");
        static string WarnBuilt { get { return Tr.T("Works only after a full rebuild and a restart of the game."); } }
        static string WarnNext { get { return Tr.T("Works after the next start of the game from this menu."); } }
        static string MpLive { get { return Tr.T("Multiplayer: one player switching it on is enough. It is sent to every PC of the session and runs for everyone. Every player needs the mods folder installed in their game."); } }
        static string MpCode { get { return Tr.T("Multiplayer: every player must have this built into their game, the same ones on every PC (the set code in the menu must match), or the session goes out of sync."); } }
        static string MpLaunch { get { return Tr.T("Multiplayer: only changes your own PC; nobody else has to do anything."); } }

        static ToolTip MakeTip(string title, IEnumerable<string> lines, string warn)
        {
            StackPanel p = new StackPanel { MaxWidth = 400 };
            p.Children.Add(new TextBlock { Text = Tr.T(title), FontWeight = FontWeights.Bold, Foreground = Gold, FontSize = 11.5, TextWrapping = TextWrapping.Wrap });
            foreach (string l in lines)
                if (l != null && l.Length > 0) p.Children.Add(new TextBlock { Text = Tr.T(l), Foreground = Text, FontSize = 10.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) });
            if (warn != null)
                p.Children.Add(new TextBlock { Text = "! " + Tr.T(warn), Foreground = Amber, FontSize = 10.5, FontWeight = FontWeights.Normal, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 6, 0, 0) });
            return new ToolTip { Content = p, Background = B("#0E0E10"), BorderBrush = B("#3A3A40"), BorderThickness = new Thickness(1), Padding = new Thickness(9, 7, 9, 8), FontFamily = Mono, HasDropShadow = false };
        }

        static string WarnFor(Entry e)
        {
            if (e.Kind == "code") return WarnBuilt;
            if (e.Kind == "launch") return WarnNext;
            return null;
        }

        static void Hover(FrameworkElement el, ToolTip tip)
        {
            el.ToolTip = tip;
            ToolTipService.SetInitialShowDelay(el, 350);
            ToolTipService.SetShowDuration(el, 60000);
        }

        ToolTip TipOf(Entry e)
        {
            List<string> l = new List<string>();
            if (e.Kind == "live")
            {
                if (e.Mode == "once") l.Add(Tr.T("Press \"Do it\": the game carries it out one time, right now."));
                else if (e.Mode == "both") l.Add("Switch it on" + (e.Keys.Length > 0 ? " and hold " + e.Keys + " in the game" : "") + ", or press \"Once\" to do it right away.");
                else l.Add(Tr.T("Switch it on: it works every frame until you switch it off."));
                l.Add(MpLive);
            }
            else if (e.Kind == "code") { l.Add(Tr.T("Switch it on, press Rebuild, then restart the game.")); l.Add(MpCode); }
            else if (e.Kind == "launch") { l.Add(Tr.T("Applied each time the game is started from this menu.")); l.Add(MpLaunch); }
            string warn = null;
            if (e.Kind == "code" && IsOn(e) && !built.Contains(e.Id)) warn = Tr.T("Switched on but not built into the game yet: press Rebuild, then restart the game.");
            return MakeTip(e.Name, l, warn);
        }

        /* the warning that stays visible on the card, not only on hover */
        static void AddWarn(StackPanel left, string text) { AddWarn(left, text, true); }
        static void AddWarn(StackPanel left, string text, bool warning)
        {
            left.Children.Add(new TextBlock { Text = (warning ? "! " : "") + Tr.T(text), Foreground = warning ? Amber : Green, FontSize = 10, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 3, 0, 0) });
        }

        Border CardOf(UIElement left, UIElement right, bool dimmed)
        {
            DockPanel d = new DockPanel { LastChildFill = true };
            if (right != null) { DockPanel.SetDock(right, Dock.Right); d.Children.Add(right); }
            d.Children.Add(left);
            Border card = new Border
            {
                Background = Card, BorderBrush = CardLine, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(2),
                Padding = new Thickness(11, 7, 10, 7), Margin = new Thickness(0, 0, 6, 2), Child = d, Opacity = dimmed ? 0.62 : 1
            };
            if (!dimmed)
            {
                card.MouseEnter += delegate { card.BorderBrush = B("#45454B"); };
                card.MouseLeave += delegate { card.BorderBrush = CardLine; };
            }
            return card;
        }

        static StackPanel TextOf(string name, string note, Action<WrapPanel> chips)
        {
            StackPanel s = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 14, 0) };
            WrapPanel top = new WrapPanel();
            top.Children.Add(new TextBlock { Text = Tr.T(name), FontSize = 12, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 10, 0), VerticalAlignment = VerticalAlignment.Center });
            if (chips != null) chips(top);
            s.Children.Add(top);
            if (note != null && note.Length > 0) s.Children.Add(new TextBlock { Text = Tr.T(note), Foreground = Dim, FontSize = 10.5, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 3, 0, 0) });
            return s;
        }

        UIElement EntryRow(Entry e)
        {
            if (e.Kind == "blocked")
            {
                Border blocked = CardOf(TextOf(e.Name, e.Reason, null), new TextBlock { Text = Tr.T("locked"), FontSize = 10, Foreground = Grey, VerticalAlignment = VerticalAlignment.Center }, true);
                Hover(blocked, MakeTip(e.Name, new[] { Tr.T("Kept out on purpose so it can never crash the game.") }, null));
                return blocked;
            }

            StackPanel left = TextOf(e.Name, e.Note, delegate (WrapPanel w)
            {
                if (e.Keys.Length > 0)
                    foreach (string k in e.Keys.Split(new[] { " / " }, StringSplitOptions.RemoveEmptyEntries))
                        w.Children.Add(Chip(k, Gold, e.Mode == "once" ? "On a DS you press this for it. Here the button does it." :
                            "Works like on a DS: switch it on, then hold these buttons in the game." + (e.Mode == "both" ? "\n\"Once\" does it right away, without the buttons." : "")));
                StatusChips(w, e.Kind, e.Status);
            });
            string warn = WarnFor(e);
            if (e.Kind == "code" && IsOn(e) && built.Contains(e.Id)) AddWarn(left, Tr.T("Built into your game: active from the next start of the game."), false);
            else if (warn != null) AddWarn(left, warn);
            StackPanel right = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            if (e.Kind == "live" && (e.Mode == "once" || e.Mode == "both"))
            {
                Button b = new Button { Content = Tr.T(e.Mode == "once" ? "Do it" : "Once"), Style = (Style)ui.FindResource("Btn"), Margin = new Thickness(0, 0, e.Mode == "both" ? 12 : 0, 0), MinWidth = 64 };
                b.ToolTip = Tr.T("Carries the code out one time, now.");
                b.Click += delegate { Once(e); };
                right.Children.Add(b);
            }
            if (e.Mode != "once")
            {
                CheckBox sw = new CheckBox { Style = (Style)ui.FindResource("Switch"), IsChecked = IsOn(e), VerticalAlignment = VerticalAlignment.Center };
                sw.Checked += delegate { if (!building) { Turn(e, true); if (!IsOn(e)) { building = true; sw.IsChecked = false; building = false; } } };
                sw.Unchecked += delegate { if (!building) Turn(e, false); };
                right.Children.Add(sw);
            }
            Border row = CardOf(left, right, false);
            Hover(row, TipOf(e));
            return row;
        }

        UIElement GroupRow(Group g)
        {
            Entry sel = g.Items.FirstOrDefault(e => IsOn(e));
            bool anyUntested = g.Items.Any(e => e.Status == "untested");
            StackPanel left = TextOf(g.Title, g.Note, delegate (WrapPanel w)
            {
                StatusChips(w, g.Kind, sel != null ? sel.Status : (anyUntested ? "" : "tested"));
            });
            if (g.Kind == "code" || g.Kind == "launch") AddWarn(left, g.Kind == "code" ? WarnBuilt : WarnNext);
            ComboBox cb = new ComboBox { VerticalAlignment = VerticalAlignment.Center };
            cb.Items.Add(new ComboBoxItem { Content = Tr.T("Off"), Tag = null });
            foreach (Entry e in g.Items)
            {
                ComboBoxItem it = new ComboBoxItem { Content = Tr.T(e.Option) + (e.Status == "untested" && !anyUntestedAll(g) ? "  · " + Tr.T("untested") : ""), Tag = e };
                Hover(it, TipOf(e));
                cb.Items.Add(it);
                if (e == sel) cb.SelectedItem = it;
            }
            if (sel == null) cb.SelectedIndex = 0;
            cb.SelectionChanged += delegate
            {
                if (building) return;
                Entry pick = cb.SelectedItem is ComboBoxItem ? ((ComboBoxItem)cb.SelectedItem).Tag as Entry : null;
                foreach (Entry e in g.Items) if (e != pick && IsOn(e)) Turn(e, false);
                if (pick != null) Turn(pick, true);
                if (!building && CurrentTag() != "on") ShowKeepScroll();
            };
            /* the wheel scrolls the page, it doesn't change a choice by accident */
            cb.PreviewMouseWheel += delegate (object s, MouseWheelEventArgs a)
            {
                if (cb.IsDropDownOpen) return;
                a.Handled = true;
                Scroll.ScrollToVerticalOffset(Scroll.VerticalOffset - a.Delta);
            };
            Border grow = CardOf(left, cb, false);
            List<string> gl = new List<string>();
            gl.Add(Tr.T("Only one option can be on. Pick \"Off\" to switch it off."));
            gl.Add(g.Kind == "code" ? MpCode : (g.Kind == "launch" ? MpLaunch : MpLive));
            Hover(grow, MakeTip(g.Title, gl, null));
            return grow;
        }
        static bool anyUntestedAll(Group g) { return g.Items.All(e => e.Status == "untested"); }

        void ShowKeepScroll()
        {
            double at = Scroll.VerticalOffset;
            ShowPage();
            Scroll.ScrollToVerticalOffset(at);
        }

        void Once(Entry e)
        {
            if (!link.Connected) { Say(Tr.F("The game isn't running: \"{0}\" wasn't done. Press Play first.", Tr.T(e.Name))); return; }
            WarnOnce(e);
            if (link.Once(e)) Say(Tr.F("Done: {0}", Tr.T(e.Name)) + (e.Ops.Length / 2 > 40 && link.Inside ? "  " + Tr.T("(a long code: it takes a few seconds to reach the game)") : ""));
            else Say(Tr.F("\"{0}\" couldn't be sent.", Tr.T(e.Name)));
        }

        void Say(string text) { Status.Text = text; }

        void UpdatePill()
        {
            string t; Brush dot;
            if (!link.Running) { t = Tr.T("The game is not running"); dot = Grey; }
            else if (link.Inside && link.Session && built.Count > 0)
            {
                /* built-in mods are part of how the game computes: a friend without the same ones is out of sync at once */
                t = Tr.F("Playing with friends · everyone needs the same built-in mods (set {0})", SetCode()); dot = Amber;
            }
            else if (link.Inside) { t = link.Session ? Tr.T("Playing with friends · cheats travel with your buttons") : (link.Busy ? Tr.T("Sending to the game…") : Tr.T("Connected · cheats are live")); dot = Green; }
            else if (link.Outside) { t = Tr.T("Connected from outside · not for playing with friends"); dot = Amber; }
            else { t = Tr.T("The game is starting…"); dot = Amber; }
            if (t == lastPill) return;
            lastPill = t;
            PillText.Text = t; Dot.Fill = dot;
            PlayBtn.IsEnabled = !link.Running && !busy;
            PlayBtn.Content = Tr.T(link.Running ? "Game is running" : "Play");
            UpdateBanner();
            if (link.Inside && link.Session && built.Count > 0)
                Say(Tr.F("With friends: every player needs exactly these built into their game too, or the session goes OUT OF SYNC: {0}. Their menu must show the same set ({1}).", string.Join(", ", entries.Where(e => built.Contains(e.Id)).Select(e => Tr.T(e.Name)).ToArray()), SetCode()));
            if (link.Inside && link.Version < 2) Say(Tr.T("This game was built with an older version of the mods: close it and press Play here once."));
        }

        /* ---------------------------------------------------------------- getting the game ready, and starting it */
        void OpenOverlay(string title, string sub)
        {
            OverTitle.Text = title; OverSub.Text = sub; OverLog.Text = ""; OverBar.Visibility = Visibility.Visible; OverBar.IsIndeterminate = true;
            OverClose.Visibility = Visibility.Collapsed; Overlay.Visibility = Visibility.Visible;
        }
        void OverlayDone(string title, string sub, bool keepOpen)
        {
            OverBar.Visibility = Visibility.Collapsed;
            if (!keepOpen) { Overlay.Visibility = Visibility.Collapsed; return; }
            OverTitle.Text = title; OverSub.Text = sub; OverClose.Visibility = Visibility.Visible;
        }

        /* "Play with mods.bat" <what>, its output into the window */
        void RunBat(string what, Action<int> then)
        {
            busy = true; PlayBtn.IsEnabled = false; ApplyBtn.IsEnabled = false; ReloadBtn.IsEnabled = false;
            Thread th = new Thread(delegate ()
            {
                int rc = 1;
                try
                {
                    ProcessStartInfo si = new ProcessStartInfo("cmd.exe", "/d /c \"\"" + Path.Combine(mods, "Play with mods.bat") + "\" " + what + "\"")
                    {
                        WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true
                    };
                    si.EnvironmentVariables["DQIX_NOPAUSE"] = "1";
                    using (Process p = new Process { StartInfo = si })
                    {
                        DataReceivedEventHandler h = delegate (object s, DataReceivedEventArgs a) { if (a.Data != null) Dispatcher.BeginInvoke(new Action(delegate { Log(a.Data); })); };
                        p.OutputDataReceived += h; p.ErrorDataReceived += h;
                        p.Start();
                        p.StandardInput.Close();
                        p.BeginOutputReadLine(); p.BeginErrorReadLine();
                        p.WaitForExit();
                        rc = p.ExitCode;
                    }
                }
                catch (Exception ex) { string m = ex.Message; Dispatcher.BeginInvoke(new Action(delegate { Log("Couldn't run \"Play with mods.bat\": " + m); })); }
                Dispatcher.BeginInvoke(new Action(delegate
                {
                    busy = false; ApplyBtn.IsEnabled = true; ReloadBtn.IsEnabled = true; PlayBtn.IsEnabled = !link.Running;
                    then(rc);
                }));
            });
            th.IsBackground = true;
            th.Start();
        }

        void Log(string line)
        {
            string t = OverLog.Text;
            if (t.Length > 60000) t = t.Substring(t.Length - 40000);
            OverLog.Text = t + line + "\n";
            OverScroll.ScrollToEnd();
        }

        void RunCatalog()
        {
            if (busy) return;
            OpenOverlay("Reading the cheat list", "Working every code out against your ROM.");
            RunBat("catalog", delegate (int rc)
            {
                LoadAll();
                OverlayDone("The cheat list couldn't be made", "The text below says why.", rc != 0);
                if (rc == 0) Say(Tr.F("The list was read again: {0} entries.", entries.Count));
            });
        }

        void RunApply(bool thenPlay)
        {
            if (busy) return;
            if (link.Running) { MessageBox.Show(this, Tr.T("The game is still running. Save, close it, then press this again."), "Rebuild", MessageBoxButton.OK, MessageBoxImage.Information); return; }
            SaveState();
            bool pending = Pending();
            OpenOverlay(pending ? "Rebuilding the game with your mods" : "Getting the game ready",
                pending ? "Only the parts that changed are built again. This takes a few minutes; the game starts by itself after." : "Checking that the game has your mods in it.");
            RunBat("apply", delegate (int rc)
            {
                ReadBuilt();
                ShowSub();
                UpdateBanner();
                if (rc != 0)
                {
                    OverlayDone(rc == 3 ? "The game is still running" : "That didn't work",
                        rc == 3 ? "Close the game, then try again." : "The game wasn't changed. The text below says why. To go back to a game without mods, press \"Everything off\", then Play.", true);
                    return;
                }
                OverlayDone("", "", false);
                Say(Tr.T("The game has your mods in it."));
                if (thenPlay) StartGame();
            });
        }

        void Play()
        {
            if (busy || link.Running) return;
            RunApply(true);
        }

        void StartGame()
        {
            string exe = Path.Combine(gameDir, "dqix.exe");
            if (!File.Exists(exe)) { Say(Tr.T("game\\dqix.exe isn't there: run BUILD.bat once.")); return; }
            BackupSave();
            try
            {
                ProcessStartInfo si = new ProcessStartInfo(exe, "data\\dqix.nds data\\code 0 1 dqix.sav") { WorkingDirectory = gameDir, UseShellExecute = false };
                string left = "";
                foreach (Entry e in entries)
                    if (e.Kind == "launch" && IsOn(e) && e.Env.Contains("="))
                    {
                        int eq = e.Env.IndexOf('=');
                        /* instant loading puts a session out of sync unless the game itself keeps it out of
                         * sessions (the mods' change in runtime\card.c): without that, not at all */
                        if (e.Env.StartsWith("DQIX_CARD_INSTANT") && !CardGuard()) { left = e.Name; continue; }
                        si.EnvironmentVariables[e.Env.Substring(0, eq)] = e.Env.Substring(eq + 1);
                    }
                using (Process.Start(si)) { }
                Say(left.Length > 0 ? Tr.F("The game is starting, without \"{0}\": this game can't keep it out of a session with friends (sync_cheats = no, or a newer version of the game).", Tr.T(left))
                    : Tr.T("The game is starting. Switches work while you play; keep this window open."));
            }
            catch (Exception ex) { Say(Tr.F("The game couldn't be started: {0}", ex.Message)); }
        }

        /* tests: show a page ("Party", "on", "search:gold") and draw the window into a picture */
        public void TestPage(string page)
        {
            if (page.StartsWith("search:")) { Search.Text = page.Substring(7); return; }
            foreach (ListBoxItem it in Nav.Items) if ((string)it.Tag == page || (string)it.Tag == "page:" + page) Nav.SelectedItem = it;
        }
        public void Inert() { ui.IsHitTestVisible = false; KeyboardNavigation.SetTabNavigation(ui, KeyboardNavigationMode.None); PreviewKeyDown += delegate (object s, KeyEventArgs a) { a.Handled = true; }; PreviewTextInput += delegate (object s, TextCompositionEventArgs a) { a.Handled = true; }; }
        public void Shot(string file)
        {
            FrameworkElement c = (FrameworkElement)Content;
            System.Windows.Media.Imaging.RenderTargetBitmap bmp = new System.Windows.Media.Imaging.RenderTargetBitmap((int)c.ActualWidth, (int)c.ActualHeight, 96, 96, PixelFormats.Pbgra32);
            bmp.Render(c);
            System.Windows.Media.Imaging.PngBitmapEncoder enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
            enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
            using (FileStream f = File.Create(file)) enc.Save(f);
        }

        /* a copy of the save each time the game starts from here: cheats change saves */
        void BackupSave()
        {
            try
            {
                string sav = Path.Combine(gameDir, "dqix.sav");
                if (!File.Exists(sav)) return;
                string dir = Path.Combine(mods, "save-backups");
                Directory.CreateDirectory(dir);
                string[] old = Directory.GetFiles(dir, "dqix-*.sav").OrderBy(f => f).ToArray();
                if (old.Length > 0 && File.ReadAllBytes(old[old.Length - 1]).SequenceEqual(File.ReadAllBytes(sav))) return;
                File.Copy(sav, Path.Combine(dir, "dqix-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".sav"), true);
                for (int i = 0; i < old.Length - 29; i++) File.Delete(old[i]);
            }
            catch (Exception) { }
        }
    }

    static class Program
    {
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);

        static string logPath = "";
        static void Fail(Exception ex)
        {
            try { File.AppendAllText(logPath, DateTime.Now + "\r\n" + ex + "\r\n\r\n"); } catch (Exception) { }
        }

        /* tests: "--editor-selftest <result file>" starts the editor host on a scratch save and checks what it serves and refuses */
        static int EditorSelfTest(string root, string result)
        {
            List<string> bad = new List<string>();
            string dir = Path.Combine(Path.GetTempPath(), "dqix-editor-selftest-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            string sav = Path.Combine(dir, "dqix.sav");
            string real = Environment.GetEnvironmentVariable("DQIX_EDITOR_SAV");
            if (!string.IsNullOrEmpty(real)) File.Copy(real, sav); else File.WriteAllBytes(sav, new byte[65536]);
            EditorHost h = new EditorHost(Path.Combine(root, "mods", "bin", "editor-cache"), sav, Path.Combine(dir, "backups"), delegate { return false; });
            try
            {
                if (!h.Start()) bad.Add("start: " + h.LastError);
                else if (!h.Prepare()) bad.Add("prepare: " + h.LastError);
                else
                {
                    string page = Encoding.UTF8.GetString(Http("GET", h.Base, null, null, bad, 200));
                    if (!page.Contains("/__save") || !page.Contains(h.Token)) bad.Add("start page has no hook");
                    /* the item names of the editor come out in the game's own German */
                    Match jm = Regex.Match(page, @"/editor/(assets/[^""]+\.js)");
                    string de = null;
                    if (jm.Success && File.Exists(Path.Combine(root, "mods", "lang", "rom-itemname-de.tsv")))
                    {
                        h.LangDir = Path.Combine(root, "mods", "lang"); h.LangOf = delegate { return "de"; };
                        foreach (string line in File.ReadAllLines(Path.Combine(h.LangDir, "rom-itemname-de.tsv"), Encoding.UTF8)) if (line.StartsWith("20004	")) de = line.Split('	')[1];
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

        [STAThread]
        static int Main(string[] args)
        {
            string root;
            if (args.Length > 0 && !args[0].StartsWith("--")) root = args[0].Trim('"');
            else root = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location), "..", ".."));
            logPath = Path.Combine(root, "mods", "bin", "menu-error.log");
            if (args.Length > 1 && args[0] == "--editor-selftest") return EditorSelfTest(root, args[1]);

            bool first;
            using (Mutex one = new Mutex(true, "dqix-cheat-menu-" + root.ToLowerInvariant().GetHashCode().ToString("x"), out first))
            {
                if (!first)
                {
                    /* already open: show that one */
                    Process me = Process.GetCurrentProcess();
                    foreach (Process p in Process.GetProcessesByName(me.ProcessName))
                        if (p.Id != me.Id && p.MainWindowHandle != IntPtr.Zero) { ShowWindow(p.MainWindowHandle, 9); SetForegroundWindow(p.MainWindowHandle); }
                    return 0;
                }
                Application app = new Application();
                /* whatever goes wrong in this window stays in this window: the game is another program */
                app.DispatcherUnhandledException += delegate (object s, DispatcherUnhandledExceptionEventArgs e) { Fail(e.Exception); e.Handled = true; };
                AppDomain.CurrentDomain.UnhandledException += delegate (object s, UnhandledExceptionEventArgs e) { Fail(e.ExceptionObject as Exception); };
                try
                {
                    MainWindow w = new MainWindow(root);
                    if (args.Contains("--shot"))
                    {
                        /* tests: "--shot file page [seconds]" draws the window into a picture (after that long) and leaves */
                        int at = Array.IndexOf(args, "--shot");
                        string file = args[at + 1], page = args.Length > at + 2 ? args[at + 2] : "";
                        double wait = 0.3;
                        if (args.Length > at + 3) double.TryParse(args[at + 3], out wait);
                        /* a picture only: it takes no clicks or keys, and doesn't come to the front */
                        w.ShowActivated = false; w.ShowInTaskbar = false; w.Focusable = false;
                        w.Inert();
                        w.Loaded += delegate
                        {
                            w.TestPage(page);
                            DispatcherTimer t = new DispatcherTimer { Interval = TimeSpan.FromSeconds(wait) };
                            t.Tick += delegate { t.Stop(); w.Shot(file); w.Close(); };
                            t.Start();
                        };
                    }
                    app.Run(w);
                }
                catch (Exception ex)
                {
                    Fail(ex);
                    MessageBox.Show("The cheat menu couldn't open: " + ex.Message + "\n\nThe game itself is fine: start it with game\\play.bat.\n(Details: mods\\bin\\menu-error.log)", "Dragon Quest IX - cheat menu");
                    return 1;
                }
            }
            return 0;
        }
    }
}
