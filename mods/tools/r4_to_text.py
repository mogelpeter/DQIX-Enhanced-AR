#!/usr/bin/env python3
"""Take one game's codes out of an R4 cheat database (usrcheat.dat) and write
them as a text file for mods/database.

  r4_to_text.py <usrcheat.dat> <game code, e.g. YDQP> <out.txt>

The cheat menu reads mods/database/<game code>.txt (the one for your ROM). The
files that come with the mods were made with this from the community database
(DeadSkullzJr's NDS(i) Cheat Databases). Run it again on a newer usrcheat.dat
to bring a list up to date.

The text format, one thing per line:

    @game YDQP AE7BD3F6 Title         game code, the database's checksum of the ROM header
    @folder Name                      a folder of codes ...
    @one                              ... of which only one can be on at a time
    @note text                        a note for the folder or code just named
    @code Name                        a code; its Action Replay lines follow
    94000130 FFFB0000
    @end                              the end of a folder
"""
import struct
import sys


def clean(s):
    return " ".join(s.replace("\r", "\n").split())


def read_games(path, want):
    d = open(path, "rb").read()
    if d[:12] != b"R4 CheatCode":
        raise SystemExit("not an R4 cheat database (usrcheat.dat): " + path)
    index, p = [], 0x100
    while p + 16 <= len(d):
        gid, crc, off = struct.unpack_from("<4sIQ", d, p)
        if off == 0:
            break
        index.append((gid, crc, off))
        p += 16
    games = []
    for gid, crc, off in index:
        if gid != want:
            continue
        p = off

        def text(align):
            nonlocal p
            e = d.index(b"\0", p)
            t = d[p:e]
            p = e + 1
            if align:
                p = (p + 3) & ~3
            return t.decode("utf-8", "replace")

        title = text(True)
        n_items = struct.unpack_from("<H", d, p)[0]
        p += 4 + 32                       # item count and flags, the master code
        out = [f"@game {gid.decode('ascii', 'replace')} {crc:08X} {clean(title)}"]
        in_folder = 0
        for _ in range(n_items):
            count, flags = struct.unpack_from("<HH", d, p)
            p += 4
            name, note = clean(text(False)), clean(text(True))
            if flags & 0x1000:            # a folder
                if in_folder:
                    out.append("@end")
                out.append("")
                out.append(f"@folder {name or 'Codes'}")
                if flags & 0x0100:
                    out.append("@one")
                if note:
                    out.append(f"@note {note}")
                in_folder = count
                if not count:
                    out.append("@end")
                continue
            n_words = struct.unpack_from("<I", d, p)[0] & 0xFFFFFF
            p += 4
            words = struct.unpack_from(f"<{n_words}I", d, p)
            p += 4 * n_words
            if not in_folder:
                out.append("")
            out.append(f"@code {name or 'Code'}")
            if note and note != name:
                out.append(f"@note {note}")
            for k in range(0, n_words - 1, 2):
                out.append(f"{words[k]:08X} {words[k + 1]:08X}")
            if in_folder:
                in_folder -= 1
                if not in_folder:
                    out.append("@end")
        if in_folder:
            out.append("@end")
        games.append((crc, out))
    return games


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 1
    games = read_games(sys.argv[1], sys.argv[2].encode("ascii"))
    if not games:
        print("no game", sys.argv[2], "in", sys.argv[1])
        return 1
    lines = [f"# Action Replay codes for {sys.argv[2]}, from an R4 cheat database (mods/tools/r4_to_text.py).",
             "# The cheat menu sorts them: which work live, which have to be built into the game,",
             "# and which can't work in this version. Your own codes go in mods/cheats and mods/code.",
             ""]
    for _, out in games:
        lines += out + [""]
    with open(sys.argv[3], "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"{sys.argv[3]}: {sum(1 for g in games for l in g[1] if l.startswith('@code'))} codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
