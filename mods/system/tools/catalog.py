#!/usr/bin/env python3
"""Everything the Cheats window offers, sorted and checked against your ROM.

  catalog.py [project folder]            writes mods/system/bin/catalog.txt (the Cheats window reads it)
  catalog.py [project folder] --report   also says why each code ended up where it did

Where the codes come from:
  mods/system/cheats/r4-<game code>.txt  the whole R4 cheat list for your ROM (r4_to_text.py)
  mods/system/cheats/*.txt        live cheats and code mods made by hand (tried out); a file
                                  with "patch" lines is a code mod, any other a live cheat

An Action Replay code is written for a DS, where it can change anything at any
moment. Here the game's program is compiled PC code, so every code is worked
out first, by running it against a copy of your ROM's own program:

  live     it only changes the game's data: the game carries it out while you play
  code     it changes instructions: those go into the build (patches.txt), after
           each one was found in your ROM where the code says it is
  blocked  it can't work here, or can't be checked: it stays off, with the reason
           (a routine of its own added to the program, DS hardware, an overlay it
           doesn't name, a jump out of the game's code...)

Nothing here changes the game: it only reads. apply_code_mods.py puts the code
mods that are switched on into the build.
"""
import bisect
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_code_mods as acm

KEY_NAMES = ["A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L", "X", "Y"]
BUDGET = 400000

# The database's folders, put into the window's pages: (folder name matches, page, put before each code's name)
PAGES = [
    (r"game enhancer", "Speed & comfort", ""),                  # EU: "Random Game Enhancer", USA: "Game Enhancer Codes & Fun Codes"
    (r"movement speed", "Speed & comfort", ""),
    (r"camera", "Speed & comfort", ""),
    (r"exp(erience)? multiplier|gold multiplier", "Experience & gold", ""),
    (r"hero codes for battle", "Party", "Hero: "),
    (r"infinite hp/mp", "Party", "Never goes down: "),
    (r"job modifier", "Party", ""),
    (r"max exp(erience)? (for )?all jobs", "Party", "Max EXP in every vocation: "),
    (r"max skill", "Party", "Hero max skill: "),                        # USA: "Max Skill Codes - Player 1 (Individual)"
    (r"skill point", "Party", ""),
    (r"battle codes", "Battle", ""),
    (r"enemy hp", "Battle", "Enemy HP 1: "),
    (r"enemy status", "Battle", ""),                                   # USA: "Enemy Status Codes"
    (r"enemy mp", "Battle", "Enemy MP 0: "),
    (r"encounter", "Battle", ""),
    (r"item codes", "Items", "99 of every: "),
    (r"treasure chest", "Items", ""),
    (r"alchemy", "Alchemy", ""),
    (r"daylight", "World", ""),
    (r"grotto", "World", ""),
    (r"unlock", "Unlocks", ""),
    (r"battle records|quest", "Records & quests", ""),
    (r"hide the party|big head|size modif", "Fun", ""),
    (r"miscellaneous", "Miscellaneous", ""),
    (r"backlight|wfc|wi-?fi", "System", ""),
]
PAGE_ORDER = ["Speed & comfort", "Camera", "Experience & gold", "Party", "Battle", "Challenges", "Items", "Treasure maps", "Nuzlocke", "Live battle", "Alchemy", "World",
              "Unlocks", "Records & quests", "Fun", "Miscellaneous"]

# cheats that belong on another page than their folder's (matched against name, shown name and the choice's title)
MOVES = [
    (r"camera", "Camera"),
    (r"bank|gold always|money in hand|unlimited money", "Experience & gold"),
    (r"grotto|treasure map|blue chest", "Treasure maps"),
    (r"regain wings", "Fun"),
    (r"push enem(y|ies) away", "Speed & comfort"),          # it only helps you walk past monsters
]
# big pages in sections the window folds open and shut: (title, pattern), in the order shown. The first pattern that fits
# wins; "." takes what no other section took.
SECTIONS = {
    "Party": [("Whole party", r"whole party|all party members|all players|skill points? never run out|1 skill point added"),
              ("Hero", r"^(?!.*hero max skill)(?=.*(\bhero\b|\(p1\)|player 1\b))"),
              ("Hero skills", r"hero max skill"),
              ("Player 2", r"\bp2\b|player 2"),
              ("Player 3", r"\bp3\b|player 3"),
              ("Player 4", r"\bp4\b|player 4"),
              ("Other", r".")],
    "Nuzlocke": [("Rules", r"permadeath|ends the run|soul link|new run"),
                 ("Punishments", r"lose|penalty"),
                 ("Randomizer", r"random"),
                 ("Seed", r"seed")],
    "Live battle": [("Hero", r"\bp1\b"), ("Player 2", r"\bp2\b"), ("Player 3", r"\bp3\b"), ("Player 4", r"\bp4\b"),
                    ("Enemy 1", r"\be1\b"), ("Enemy 2", r"\be2\b"), ("Enemy 3", r"\be3\b"), ("Enemy 4", r"\be4\b"), ("Enemy 5", r"\be5\b"), ("Enemy 6", r"\be6\b")],
    "Battle": [("Party buffs", r"."),
               ("Enemy debuffs", r"^enemy|enemy in |1 hit kill"),
               ("Monster AI", r"flee|chase"),
               ("Encounters", r"random battles|same monster|animation before|metal slimes|battle any monster|strike first")],
}
# cheats whose changes are put back when they are switched off (mod_cheats.c SET_UNDO): the game itself would keep the big head
# or the hidden party until the next battle or map change
UNDO = r"hide the party|invisible party|disable movement|big head|massive head|head \(hold|size modif|giant pair"


def section_of(page, text):
    rules = SECTIONS.get(page)
    if not rules:
        return ""
    for title, pat in rules:
        if pat != "." and re.search(pat, text, re.I):
            return title
    return next((t for t, pat in rules if pat == "."), "")

REASONS = {
    "hook": "It adds a routine of its own to the game's program. This compiled version can't check such a routine, so it stays off.",
    "jump": "It sends the game's program to a place outside its own code. That can't be checked, so it stays off.",
    "overlay": "It doesn't say which part of the game it changes, so it can't be checked against your ROM.",
    "ovldata": "It changes data inside a part of the program that this version compares with your ROM.",
    "selfmod": "Its new instructions write into the game's program while it runs. That can't be checked, so it stays off.",
    "mixed": "It changes the program and, while you play, data that goes with it. The two can't be kept in step in this version, so it stays off.",
    "hardware": "It works on the DS's own hardware (backlight, wireless chip...), which a PC doesn't have.",
    "nomatch": "Your ROM's program isn't what this code expects, so it would do nothing.",
    "empty": "It has no code lines.",
    "long": "It is too long to send to the game (more than 1023 lines).",
    "piracy": "Not needed: this version already takes the copy protection's trap out.",
    "wfc": "Not needed: choose the server in the game's own Wireless menu instead.",
}

LAUNCH = [
    ("launch:fast", "Always fast forward", "DQIX_FAST=1",
     "The whole game runs as fast as your PC can, from the moment it starts. (While playing, Tab does the same.) No sound while it's fast. Takes effect the next time the game starts.", "Speed & comfort", ""),
    ("launch:card", "Instant loading", "DQIX_CARD_INSTANT=1",
     "Skips the DS cartridge's reading delays. Only while you play alone: in a session with friends the game keeps the real delays by itself, so everyone stays in sync. Takes effect the next time the game starts.", "Speed & comfort", ""),
    ("launch:metal", "Metal slimes only, in the areas that have them", "DQIX_MOD_METAL=1",
     "In every area where metal monsters live, only metal monsters appear. Areas without them stay as they are. The game reads this once when it starts.", "Battle", ""),
]

# The Nuzlocke page (src/runtime/nuzlocke.c). The rules are live cheats (cheats/nuzlocke-*.txt, switch addresses 02F5A5C0 + 4n). The randomizers
# change the cartridge's tables when the game starts, so they are launch options for every PC ("All players"); the seed is one choice.
NZ_STATUS = "untested"
NZ_LAUNCH = [
    ("launch:nz-enc", "Random monsters in the field and in battle", "DQIX_MOD_NZ_ENC=1",
     "Every kind of monster becomes another kind of about the same level (metal monsters stay metal), everywhere: what you see roaming is what you fight. Bosses are not touched. The seed below decides which."),
    ("launch:nz-skills", "Random skill trees", "DQIX_MOD_NZ_SKILLS=1",
     "Which ability a skill line gives is dealt out again: every ability is still learned once, but in another skill line and at another skill point cost."),
    ("launch:nz-spells", "Random spells for every vocation", "DQIX_MOD_NZ_SPELLS=1",
     "Which spell a vocation learns at which level is dealt out again (no vocation gets one twice)."),
    ("launch:nz-growth", "Random stat growth per vocation", "DQIX_MOD_NZ_GROWTH=1",
     "Every stat a vocation gains per level is taken from another vocation's growth (a different one for every stat). The experience you need is not changed."),
    ("launch:nz-drops", "Random monster drops", "DQIX_MOD_NZ_DROPS=1",
     "What ordinary monsters drop is dealt out again: common drops among the common ones, rare drops among the rare ones. Bosses keep theirs."),
    ("launch:nz-shops", "Random shop wares", "DQIX_MOD_NZ_SHOPS=1",
     "The items shops sell are dealt out again among all the shops' shelves."),
]
NZ_SEEDS = 24


# The live battle window (Cheats > Battle cheats...): per party member and per enemy, shown only while that member / enemy is really there. The
# addresses are the same in the USA and the European game (the R4 lists of both write them). A party member's record is at PARTY0 - i * 0x964 (his
# name); during a battle it holds the battle's copy: maximum HP +0x58, maximum MP +0x5A, HP now +0x5C, MP now +0x5E, tension +0x6F / +0x7C, a flag
# byte +0x70 and the Coup de Grace byte +0x93. An enemy's record is at ENEMY0 + n * 0xA4: HP +0, MP +4, status bytes +0x14 and +0x22.
BATTLE_PAGE = "Live battle"
PARTY0, PARTY_STRIDE, ENEMY0, ENEMY_STRIDE = 0x020F54B4, 0x964, 0x022A4638, 0xA4
W32, W16, W8 = 0x00000000, 0x10000000, 0x20000000      # Action Replay write types


FORCE_SWITCH = 0x02F5A5B4                              # "Battle any monster you want": mod_cheats.c MC_SWITCH_FORCE
TENSION_SWITCH = 0x02F5A5B8                            # high tension for the party members of the value's bits 0..3: mod_cheats.c MC_SWITCH_TENSION
RECALC_SWITCH = 0x02F5A620                             # "All buffs" / "All debuffs": the fighter whose stats to work out again (challenges.c)
TOUGH_SWITCH = 0x02F5A610                              # the Challenges page (mod_cheats.c mc_challenges, challenges.c, forcebtl.c): tougher monsters,
NOSPELL_SWITCH = 0x02F5A614                            # the multiplier in halves; no spells; fully random encounters
RANDENC_SWITCH = 0x02F5A618
NOABIL_SWITCH = 0x02F5A628                             # no abilities (challenges.c no_abilities)
RANDBOSS_SWITCH = 0x02F5A61C                           # fully random boss encounters (forcebtl.c)
COMBO_SWITCH = 0x02F5A624                              # "Always 4-hit combo": the party members of the value's bits 0..3 (mod_cheats.c MC_SWITCH_COMBO, challenges.c)
COUP_SWITCH = 0x02F5A5BC                               # Coup de Grace ready for them: mod_cheats.c MC_SWITCH_COUP (the game's own flag, so the menu lights it)
COUP_SKIP_PATCH = [("ov000", 0x0217B2C4, 0xE1A00000)]  # the R4 lists' "Can Always Use Coup de Grace": skips the menu's check, the text stays grey
LEGSTAT_SWITCH = 0x02F5A600                            # its legacy boss levels' stats: mod_cheats.c MC_SWITCH_LEGSTAT (4 words)
LEGACY_LEVELS = (50, 99)


def boss_songs(nds):
    """{monster: song} from data/event/eventbattle.bin, the story's battles (and the grottos' bosses): records of 9 values after an 8-byte header,
    from 0x10: battle, then monster and count three times (-1 = none), then the song (the sound archive's sequence number, BG_<n>), then a check.
    The field plays that song for such a battle instead of 23, the usual battle song (ov017 021b6290 -> main 0209c480). Bosses get 24, the legacy
    bosses each their own (Dragonlord 27 .. Rhapthorne 38, the same for their three forms), Corvus' last battle 26. A monster in more than one
    battle keeps its first one's song."""
    d = nds.read("data/event/eventbattle.bin")
    songs = {}
    for i in range(struct.unpack_from("<I", d, 0)[0]):
        v = struct.unpack_from("<9i", d, 0x10 + 44 * i + 8)
        for mon in (v[1], v[3], v[5]):
            if mon > 0:
                songs.setdefault(mon, v[7])
    return songs


def legacy_bosses(nds):
    """The 13 legacy bosses as the game makes them at a level (forcebtl.c has the how): [(base monster, [3 monsters by level band],
    {level: (monster, [4 switch words])})]. data/tmap/tdata.gp2's last table lists base and band monsters; data/tmap/param.pac (a NARC,
    p_<base>.dat) has a 24-byte row per level: HP u32, MP u32, attack u16, defense u16, agility u16, band u8, EXP u32, gold u32, u8."""
    import rom_text
    t = rom_text.gpc2(nds.read("data/tmap/tdata.gp2"))["tdata_en.pac"]
    p = struct.unpack_from("<I", t, 4 + 4 * 16)[0]
    count = struct.unpack_from("<H", t, p)[0]; p += 2
    bands = {}
    for _ in range(count):
        _id, base, a1, a2, a3, _u, l = struct.unpack_from("<7H", t, p); p += 14 + l
        _u, l = struct.unpack_from("<2H", t, p); p += 4 + l
        bands[base] = [a1, a2, a3]
    d = nds.read("data/tmap/param.pac")
    o = 0x10; assert d[o:o + 4] == b"BTAF"
    size, n = struct.unpack_from("<IH", d, o + 4)
    fat = [struct.unpack_from("<II", d, o + 12 + 8 * i) for i in range(n)]
    o += size; assert d[o:o + 4] == b"BTNF"
    fnt = d[o + 8:o + struct.unpack_from("<I", d, o + 4)[0]]
    img = o + struct.unpack_from("<I", d, o + 4)[0] + 8
    q, names = struct.unpack_from("<I", fnt, 0)[0], []
    while fnt[q]:
        names.append(fnt[q + 1:q + 1 + (fnt[q] & 0x7F)].decode()); q += 1 + (fnt[q] & 0x7F)
    out = []
    for name, (a, b) in zip(names, fat):
        m = re.match(r"p_(\d+)\.dat$", name)
        if not m or int(m.group(1)) not in bands:
            continue
        base, f, lv = int(m.group(1)), d[img + a:img + b], {}
        for level in LEGACY_LEVELS:
            hp, mp, atk, dfn, agi, band = struct.unpack_from("<IIHHHB", f, 24 * (level - 1))
            exp, gold = struct.unpack_from("<II", f, 24 * (level - 1) + 0x0F)
            if not 1 <= band <= 3 or not hp:
                continue
            lv[level] = (bands[base][band - 1], [min(hp, 0xFFFF) | min(mp, 0xFFFF) << 16, atk | dfn << 16, agi | min(gold, 0xFFFF) << 16, exp])
        out.append((base, bands[base], lv))
    return out


def battle_addr_set():
    """the exact RAM bytes the live battle cheats write: the database's own codes for them are replaced (their names differ between the lists)"""
    out = set()
    for i in range(4):
        b = PARTY0 - i * PARTY_STRIDE
        for off in (0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x6F, 0x70, 0x7C, 0x93):
            out.add(b + off)
    for n in range(6):
        b = ENEMY0 + n * ENEMY_STRIDE
        for off in (0, 1, 4, 5, 0x14, 0x22):
            out.add(b + off)
    return out


def effect_ops(st):
    """The effects of a fighter: st is its record of current stats (a party member: record + 0x58; an enemy: its record). Found in a real fight (Buff and
    Insulate cast on the hero), with the layout of a trainer for the same game as a guide: eight effects in this order: attack, defence, agility, charm,
    magical might, magical mending, magic resistance, breath resistance. Effect j has its flag in the status word at st+0x14 (0x400 << j, the last two 0x10000
    and 0x20000), its level (3 bits, +2 = 2, -2 = 6) at st+0x58 (24 bits) and two round counters (the game's code, checked):
      - st+0x6E+j: set to 5 when cast (main 020877c0 and the like). The round tick (ov000 021599f4, table 02182EFC) takes one off each round; while it is
        above 0 the effect can't end. When it gets to 0 the tick puts 4 into
      - st+0x91+j: from then on the end of each round (ov000 0215858c) takes one off it and ends the effect with a chance from table 02182AD4 (62.5% at 3,
        75% at 2, 87.5% at 1, certain at 0). At 0 that check is skipped altogether.
    So a cast lasts 5 rounds, then up to 4 more. Bounce (flag 0x200, counter st+0x61) is not one of them.  -> (lasting, all buffs, all debuffs)"""
    lasting = []
    for j in range(8):
        pos = st + 0x6E + j
        # the first counter 1..5: back to 6 (it never gets to 0, so the second stage never starts); 0 stays 0 (no effect, or one already in the second
        # stage), 6 and up are left alone (our buttons' 255). The second counter is held at 0: an effect already in the second stage stops rolling to end.
        lasting += [(0xA0000000 | pos, 0xFF000000), (0x70000000 | pos, 0xFF000006), (W8 | pos, 6), (0xD0000000, 0), (0xD0000000, 0), (W8 | st + 0x91 + j, 0)]
    def flags():
        out = []
        for byte, bit in [(st + 0x15, 1 << k) for k in range(2, 8)] + [(st + 0x16, 1), (st + 0x16, 2)]:
            # the bit is clear -> add it (there is no OR: read the byte, add the bit, write it back)
            out += [(0x90000000 | byte, (~bit & 0xFFFF) << 16), (0xD3000000, byte), (0xDB000000, 0), (0xD4000000, bit), (0xD8000000, 0), (0xD3000000, 0), (0xD0000000, 0)]   # (D3 0: the offset is back to 0 for the plain writes after it)
        return out
    def recalc():
        # and the switch that has the game work the fighter's stats out again from the new levels at once (mod_cheats.c MC_SWITCH_RECALC, challenges.c)
        return [(RECALC_SWITCH, st)]

    def counters():
        # the whole battle: the first counter at 255 (a round each, so it never gets to 0), the second at 0 (no ending roll); a dispel still ends them
        return [(W8 | st + 0x6E + j, 0xFF) for j in range(8)] + [(W8 | st + 0x91 + j, 0) for j in range(8)]
    buffs = flags() + [(W16 | st + 0x58, 0x2492), (W8 | st + 0x5A, 0x49)] + counters() + recalc() + [(0xD2000000, 0)]
    debuffs = flags() + [(W16 | st + 0x58, 0x6DB6), (W8 | st + 0x5A, 0xDB)] + counters() + recalc() + [(0xD2000000, 0)]
    return lasting, buffs, debuffs


EFFECT_NAMES = "attack, defence, agility, charm, magical might, magical mending, magic resistance and breath resistance"


def buff_entries(who, buffs, debuffs, extra):
    """the "All buffs" / "All debuffs" buttons of one card (effect_ops: every effect at +2 / -2, the most there is, for the rest of the battle)"""
    return [("live:battle:%s:buffs" % who, "All buffs", who, buffs, "once",
             "All eight effects go up two levels, the most there is: " + EFFECT_NAMES + ". They last the whole battle (only a dispel like Disruptive Wave ends them). Bounce is not one of them." + extra),
            ("live:battle:%s:debuffs" % who, "All debuffs", who, debuffs, "once",
             "All eight effects go down two levels, the most there is: " + EFFECT_NAMES + ". They last the whole battle (only a dispel ends them)." + extra)]


def battle_entries():
    """-> the live battle entries: (id, name, who, ops, mode, note)"""
    out = []
    for i in range(4):
        b = PARTY0 - i * PARTY_STRIDE
        who = "p%d" % (i + 1)
        hp, mp = (b + 0x5C, b + 0x58), (b + 0x5E, b + 0x5A)
        copy = lambda cur, mx: [(0xA2000000 | cur, 0), (0xDA000000, cur), (0xD7000000, mx), (0xD2000000, 0)]
        keep = copy(*hp) + copy(*mp) + [(W8 | b + 0x70, 0x40)]     # + the game's invincible flag: a hit bigger than their HP kills before the copy can undo it (checked in a real fight, Dragonlord Lv. 99)
        out += [
            ("live:battle:%s:keep" % who, "Never go down", who, keep, "always", "HP and MP are put back to full every frame and the game's own invincible flag is set, so even one hit that is bigger than their HP can't knock them out."),
            ("live:battle:%s:max" % who, "HP/MP 999", who, [(W16 | b + 0x58, 999), (W16 | b + 0x5C, 999), (W16 | b + 0x5A, 999), (W16 | b + 0x5E, 999)], "once",
             "Their maximum and current HP and MP become 999 for this battle."),
            ("live:battle:%s:revive" % who, "Revive", who, [(0x02F5A5B0, i + 1)], "once", "Brings them back with full HP if they have fallen (does nothing for a member who is up)."),
            # tension and Coup de Grace: the game's own way (mod_cheats.c mc_battle_locks), not the R4 codes' bytes (+0x6F / +0x7C, +0x93 = 0x98)
            ("live:battle:%s:tension" % who, "High tension", who, [(TENSION_SWITCH, 1 << i)], "once", "Their tension goes to the top (100), as Psyche Up does it."),
            ("live:battle:%s:coup" % who, "Coup ready", who, [(COUP_SWITCH, 1 << i)], "once", "Their Coup de Grace is ready, lit up in the menu, for 9 rounds."),
        ]
        la, bu, de = effect_ops(b + 0x58)
        out += [("live:battle:%s:lasting" % who, "Effects last all battle", who, la, "always",
                 "Every buff and debuff on them, cast or from the buttons, lasts the whole battle: none runs out, even one that was about to. Only a dispel like Disruptive Wave ends them. Bounce is not touched.")]
        out += buff_entries(who, bu, de, "")
        out.append(("live:battle:%s:invincible" % who, "Invincible", who, [(W8 | b + 0x70, 0x40)], "once", "The game's own \"invincible\" flag, as the R4 code sets it (the hero's too: the same flag \"Never go down\" sets)."))
    status = [("sleep", "Sleep", [(0x14, 0x10)]), ("poison", "Poison", [(0x14, 0x02), (0x22, 0x02)]),
              ("stun", "Stun", [(0x14, 0x08)]), ("confuse", "Confuse", [(0x14, 0x20)])]
    for n in range(6):
        b = ENEMY0 + n * ENEMY_STRIDE
        who = "e%d" % (n + 1)
        out += [
            ("live:battle:%s:defeat" % who, "Defeat", who, [(W16 | b, 0)], "once", "HP to 0."),
            ("live:battle:%s:hp1" % who, "HP 1", who, [(W16 | b, 1)], "once", ""),
            ("live:battle:%s:mp0" % who, "MP 0", who, [(W16 | b + 4, 0)], "once", ""),
            # the enemy record: HP +0, MP +2, maximum HP +4, maximum MP +6 (not +8 / +10: those are the species' field values): copy the maximums over the current values (DA = load 16 bits, D7 = store them)
            ("live:battle:%s:refill" % who, "Refill HP", who, [(0xDA000000, b + 4), (0xD7000000, b), (0xD2000000, 0)], "once", "Its HP goes back to full, just for fun."),
            ("live:battle:%s:refillmp" % who, "Refill MP", who, [(0xDA000000, b + 6), (0xD7000000, b + 2), (0xD2000000, 0)], "once", "Its MP goes back to full."),
        ]
        la, bu, de = effect_ops(b)
        out += [("live:battle:%s:lasting" % who, "Effects last all battle", who, la, "always", "Every buff and debuff on it, cast or from the buttons, lasts the whole battle: none runs out, even one that was about to. Only a dispel ends them. Untested on enemies.")]
        out += buff_entries(who, bu, de, " Untested on enemies.")
        for sid, sname, writes in status:
            out.append(("live:battle:%s:%s" % (who, sid), sname, who, [(W8 | b + off, v) for off, v in writes], "once", ""))
    return out


def who_of(*texts):
    """"p2".."p4" for what belongs to party member 2..4 (the window shows it only while that member is in the party)"""
    m = re.search(r"\bP([2-4])\b|\bPlayer ([2-4])\b|\b([2-4])(?:nd|rd|th) (?:character|player)", " | ".join(texts))
    return "p" + next(g for g in m.groups() if g) if m else ""


# ---------------------------------------------------------------- your ROM
class Rom:
    def __init__(self, root):
        self.root = root
        extract = os.path.join(root, "build", "extract")
        self.region = "usa"
        try:
            self.region = open(os.path.join(root, "build", "obj", "region.txt")).read().strip() or "usa"
        except OSError:
            pass
        self.shifts = acm.eur_shifts(root) if self.region == "eur" else []
        mods = acm.load_modules(extract)
        self.main = mods[0]
        self.overlays = mods[1:]
        self.by_name = {m.name: m for m in mods}
        with open(os.path.join(extract, "..", "..", "game", "data", "dqix.nds"), "rb") as f:
            head = f.read(0x200)
        self.game = head[12:16].decode("ascii", "replace")
        self.crc = ~zlib.crc32(head) & 0xFFFFFFFF          # what an R4 database calls the ROM's checksum
        # where the instructions are: the recompiler's own list of functions
        self.funcs = {}
        table = os.path.join(root, "build", "recomp", "dispatch_table.c")
        for ovl, addr, size in re.findall(r"\{\s*(-?\d+),\s*0x([0-9a-fA-F]+)u,\s*(\d+),", open(table).read()):
            a, size = int(addr, 16), int(size)
            name = "main" if int(ovl) < 0 else f"ov{int(ovl):03d}"
            if name == "main" and not self.in_image(self.main, a & ~1):
                continue                                    # ITCM
            self.funcs.setdefault(name, []).append((a & ~1, (a & ~1) + size, a & 1))
        for v in self.funcs.values():
            v.sort()

    @staticmethod
    def in_image(m, a):
        return m.base <= a < m.base + len(m.data)

    def func_at(self, m, a):
        """(start, end, thumb) of the function of module m that holds address a, or None."""
        fs = self.funcs.get(m.name, [])
        i = bisect.bisect_right(fs, (a, 1 << 40, 2)) - 1
        while i >= 0 and i >= bisect.bisect_right(fs, (a, 1 << 40, 2)) - 4:    # (secondary entries overlap)
            if fs[i][0] <= a < fs[i][1]:
                return fs[i]
            i -= 1
        return None

    def in_any_overlay(self, a):
        return any(self.in_image(m, a) for m in self.overlays)

    def to_rom(self, a):            # USA main-program address -> this ROM's
        for lo, hi, sh in self.shifts:
            if lo <= a < hi:
                return a + sh
        return a

    def from_rom(self, a):          # and back (patches.txt wants USA addresses)
        for lo, hi, sh in self.shifts:
            if lo + sh <= a < hi + sh:
                return a - sh
        return a


class Mem:
    """The DS's memory as the ROM leaves it: the main program, one overlay (or none), zeros elsewhere."""

    def __init__(self, rom, ctx):
        self.rom, self.ctx, self.w = rom, ctx, {}

    @staticmethod
    def norm(a):
        return 0x02000000 | (a & 0x3FFFFF)

    def is_static(self, a):
        """Is this the program itself (what a "only if the game has this instruction" line looks at)?
        The data sections, the heap and everything else change while the game runs."""
        if (a >> 24) != 2:
            return True
        a = self.norm(a)
        if Rom.in_image(self.rom.main, a):
            return self.rom.func_at(self.rom.main, a) is not None
        return self.rom.in_any_overlay(a)

    def byte(self, a):
        if a in self.w:
            return self.w[a]
        for m in (self.rom.main, self.ctx):
            if m is not None and Rom.in_image(m, a):
                return m.data[a - m.base]
        return 0

    def read(self, a, n):
        if (a >> 24) != 2:
            return 0
        a = self.norm(a)
        return sum(self.byte(a + i) << (8 * i) for i in range(n))

    def write(self, a, n, v):
        if (a >> 24) != 2:
            return
        a = self.norm(a)
        for i in range(n):
            self.w[a + i] = (v >> (8 * i)) & 0xFF


# ---------------------------------------------------------------- Action Replay, as in ar_engine.h
def is_keyreg(a):
    return a in (0x04000130, 0x04000136) or (a & 0x0FFFFFFF) == 0x027FFFA8


def keyreg(a, keys):
    if a == 0x04000130:
        return ~keys & 0x3FF
    if a == 0x04000136:
        return 0x7F & ~(keys >> 10 & 3)
    return 0x2C00 & ~((keys >> 10 & 3) << 10)


def ar_sim(ops, mem, keymode, flags):
    """One pass. keymode: "all" (every key condition holds), "none", or the (a, b) of the one that holds."""
    offset = data = 0
    skip = 0
    loop_start, loop_left = -1, 0
    budget = BUDGET
    n, pc = len(ops), 0
    M = 0xFFFFFFFF
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        budget -= 1
        if budget < 0:
            flags["endless"] = True
            return
        if skip:
            if 3 <= t <= 0xA:
                skip += 1
            elif top == 0xD0:
                skip -= 1
            elif top in (0xD1, 0xD2):
                skip = 0
                if top == 0xD2 and loop_start < 0:
                    offset = data = 0
                if loop_start >= 0:
                    if loop_left > 0:
                        loop_left -= 1
                        pc = loop_start + 1
                        continue
                    loop_start = -1
                    if top == 0xD2:
                        offset = data = 0
            elif t == 0xE:
                pc += (b + 7) // 8
            pc += 1
            continue
        if t <= 2:
            addr = (addr + offset) & M
        elif t <= 0xB and addr == 0:
            addr = offset
        if t == 0:
            mem.write(addr, 4, b)
        elif t == 1:
            mem.write(addr, 2, b)
        elif t == 2:
            mem.write(addr, 1, b)
        elif 3 <= t <= 0xA:
            key = is_keyreg(addr)
            if key and (keymode == "all" or keymode == (a, b)):
                pc += 1
                continue
            if not key and not mem.is_static(addr):
                flags["dynamic"] = True
            if t <= 6:
                v = keyreg(addr, 0) if key else mem.read(addr, 4)
                ok = b > v if t == 3 else b < v if t == 4 else b == v if t == 5 else b != v
            else:
                v = (keyreg(addr, 0) if key else mem.read(addr, 2)) & ~(b >> 16) & 0xFFFF
                y = b & 0xFFFF
                ok = y > v if t == 7 else y < v if t == 8 else y == v if t == 9 else y != v
            if not ok:
                skip = 1
        elif t == 0xB:
            flags["dynamic"] = True
            offset = mem.read(addr, 4)
        elif t == 0xC:
            if top == 0xC0:
                loop_start, loop_left = pc, b
        elif t == 0xD:
            if top in (0xD1, 0xD2):
                if loop_start >= 0 and loop_left > 0:
                    loop_left -= 1
                    pc = loop_start + 1
                    continue
                loop_start = -1 if loop_start >= 0 else loop_start
                if top == 0xD2:
                    offset = data = 0
            elif top == 0xD3:
                offset = b
            elif top == 0xD4:
                data = (data + b) & M
            elif top == 0xD5:
                data = b
            elif top == 0xD6:
                mem.write((b + offset) & M, 4, data)
                offset = (offset + 4) & M
            elif top == 0xD7:
                mem.write((b + offset) & M, 2, data)
                offset = (offset + 2) & M
            elif top == 0xD8:
                mem.write((b + offset) & M, 1, data)
                offset = (offset + 1) & M
            elif top in (0xD9, 0xDA, 0xDB):
                src = (b + offset) & M
                if not mem.is_static(src):
                    flags["dynamic"] = True
                data = mem.read(src, 4 if top == 0xD9 else 2 if top == 0xDA else 1)
            elif top == 0xDC:
                offset = (offset + b) & M
        elif t == 0xE:
            dst = (addr + offset) & M
            i, line = 0, pc + 1
            while line < n and i < b:
                for w in ops[line]:
                    for s in range(4):
                        if i < b:
                            mem.write((dst + i) & M, 1, (w >> (8 * s)) & 0xFF)
                            i += 1
                line += 1
            pc += (b + 7) // 8
        elif t == 0xF:
            if b > budget:
                flags["endless"] = True
                return
            budget -= b
            for i in range(b):
                mem.write((addr + i) & M, 1, mem.read((offset + i) & M, 1))
        pc += 1


def scan(ops):
    """What a code asks of the DS, without running it: its key conditions, and hardware it touches."""
    keys, hardware = [], False
    pc, n = 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        if t == 0xE:
            hardware |= (addr >> 24) >= 3
            pc += 1 + (b + 7) // 8
            continue
        if 3 <= t <= 0xA and is_keyreg(addr):
            if (a, b) not in keys:
                keys.append((a, b))
        elif t <= 0xB or t == 0xF:
            hardware |= (addr >> 24) >= 3
        elif top in (0xD3, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xDB):
            hardware |= 3 <= (b >> 24) < 0x10
        pc += 1
    return keys, hardware


def static_writes(ops):
    """Every place a code can write: [(address, bytes)], and whether it also writes through a pointer."""
    out, pointer, moved = [], False, False
    pc, n = 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, top, addr = a >> 28, a >> 24, a & 0x0FFFFFFF
        if t <= 2 or t == 0xE or t == 0xF:
            size = (4, 2, 1)[t] if t <= 2 else b
            if moved and t != 0xF:
                pointer = True
            else:
                out.append((addr, size))
            if t == 0xE:
                pc += (b + 7) // 8
        elif top in (0xD6, 0xD7, 0xD8):
            if moved:
                pointer = True
            else:
                out.append((b, {0xD6: 4, 0xD7: 2, 0xD8: 1}[top]))
            moved = True                                    # the next one is further on
        elif t == 0xB or top in (0xD3, 0xDC):
            moved = True
        elif top == 0xD2:
            moved = False
        pc += 1
    return out, pointer


def moved_for_rom(rom, ops):
    """The same code with main-program addresses moved from the USA version's to this ROM's."""
    out, pc, n = [], 0, len(ops)
    while pc < n:
        a, b = ops[pc]
        t, addr = a >> 28, a & 0x0FFFFFFF
        if t <= 0xA or t == 0xE:
            if Rom.in_image(rom.main, addr) and rom.func_at(rom.main, rom.to_rom(addr)):
                a = (a & 0xF0000000) | rom.to_rom(addr)
        out.append((a, b))
        if t == 0xE:
            k = (b + 7) // 8
            out += ops[pc + 1:pc + 1 + k]
            pc += k
        pc += 1
    return out


def key_text(cond):
    """"L+R" for 94000130 FCFF0000; "" when it isn't a plain "these are held"."""
    a, b = cond
    t, addr = a >> 28, a & 0x0FFFFFFF
    if t != 9:
        return ""
    look, want = ~(b >> 16) & 0xFFFF, b & 0xFFFF
    if want & look:
        return ""                                           # asks for a key NOT held
    if addr == 0x04000130:
        bits = [i for i in range(10) if look >> i & 1]
    elif addr == 0x04000136:
        bits = [10 + i for i in range(2) if look >> i & 1]
    else:
        bits = [i for i in (10, 11) if look >> i & 1]
    order = [9, 8, 2, 3, 0, 1, 10, 11, 6, 7, 5, 4]          # L R SELECT START A B X Y, then directions
    return "+".join(KEY_NAMES[i] for i in order if i in bits)


def is_branch(w):
    return (w & 0x0E000000) == 0x0A000000


def stores_into_program(w):
    """An ARM instruction that writes to memory at an address counted from itself (str ..., [pc, #n])."""
    if (w >> 28) == 0xF or ((w >> 16) & 0xF) != 15 or (w >> 20) & 1:
        return False
    if (w & 0x0C000000) == 0x04000000:
        return True                                         # str / strb
    return (w & 0x0E000090) == 0x00000090 and (w >> 5) & 3 != 0     # strh and the like


def branch_target(addr, w):
    off = w & 0x00FFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (addr + 8 + (off << 2) + (2 if (w >> 28) == 0xF and (w >> 24) & 1 else 0)) & 0xFFFFFFFF


def classify(rom, ops):
    """-> dict(kind=live|code|blocked, why=..., variants=[(label, [(module, address, word)])], keys=[...])."""
    keys, hardware = scan(ops)
    out = {"keys": keys, "variants": []}
    if not ops:
        return dict(out, kind="blocked", why="empty")
    modes = ["none"] + keys + (["all"] if len(keys) != 1 else [])
    found = {}                      # keymode -> {(module, address): word}
    touched = set()                 # instruction words it writes (also when it puts back what was there)
    mixed = False                   # a run that changes instructions also writes elsewhere
    any_write = dynamic = False
    loose = ovldata = False
    for ctx in [None] + rom.overlays:
        for mode in modes:
            mem, flags = Mem(rom, ctx), {}
            ar_sim(ops, mem, mode, flags)
            dynamic |= bool(flags.get("dynamic"))
            if not mem.w:
                continue
            any_write = True
            code, other = {}, 0
            for a in mem.w:
                m = None
                if Rom.in_image(rom.main, a):
                    m = rom.main if rom.func_at(rom.main, a) else None
                elif ctx is not None and Rom.in_image(ctx, a):
                    if rom.func_at(ctx, a):
                        m = ctx
                    else:
                        ovldata = True
                        continue
                elif rom.in_any_overlay(a):
                    if ctx is None:
                        loose = True                        # written whatever is loaded there
                    continue
                if m is None:
                    other += 1
                    continue
                code[(m.name, a & ~3)] = None
                touched.add(a & ~3)
            for name, wa in list(code):
                m = rom.by_name[name]
                word = sum(mem.byte(wa + i) << (8 * i) for i in range(4))
                if word == m.word(wa):
                    del code[(name, wa)]                    # puts back what is there anyway
                else:
                    code[(name, wa)] = word
            if code:
                if other:
                    mixed = True
                found.setdefault(mode, {}).update(code)
    if found:
        if mixed:
            return dict(out, kind="blocked", why="hook")
        writes, pointer = static_writes(ops)
        if pointer or any((Mem.norm(a + i) & ~3) not in touched for a, size in writes for i in range(0, max(size, 1), 4)):
            return dict(out, kind="blocked", why="mixed")
        for patch in found.values():
            for (name, wa), word in patch.items():
                m = rom.by_name[name]
                fn = rom.func_at(m, wa)
                if fn and not fn[2] and stores_into_program(word):
                    return dict(out, kind="blocked", why="selfmod")
                if fn and not fn[2] and is_branch(word):
                    tgt = branch_target(wa, word)
                    inside = (Rom.in_image(m, tgt) and rom.func_at(m, tgt)) or \
                             (Rom.in_image(rom.main, tgt) and rom.func_at(rom.main, tgt))
                    old = m.word(wa)
                    same = is_branch(old) and branch_target(wa, old) == tgt
                    if not inside and not same:
                        return dict(out, kind="blocked", why="jump")
        variants = []
        if found.get("none"):
            variants.append(("", found["none"]))            # it's on whatever is held: that is the mod
        else:
            seen = []
            for mode in keys + ["all"]:
                p = found.get(mode)
                if p and p not in seen:
                    seen.append(p)
                    variants.append((key_text(mode) if mode != "all" else "", p))
        out["variants"] = [(label, sorted((n, a, w) for (n, a), w in p.items())) for label, p in variants]
        out["held"] = not found.get("none")
        return dict(out, kind="code")
    if loose:
        return dict(out, kind="blocked", why="overlay")
    if ovldata:
        return dict(out, kind="blocked", why="ovldata")
    if hardware:
        return dict(out, kind="blocked", why="hardware")
    if not any_write and not dynamic:
        return dict(out, kind="blocked", why="nomatch")
    if len(ops) > 1023:
        return dict(out, kind="blocked", why="long")
    return dict(out, kind="live")


# ---------------------------------------------------------------- the files
def clean(s):
    return " ".join(str(s).replace("\t", " ").split())


def strip_keys(name):
    """"[SEL]All shield" -> "All shield": the window shows the keys by itself."""
    rest = re.sub(r"^\s*\[(?:[A-Za-z/]+)(?:\s*\+\s*[A-Za-z/]+)*(?:\s+On/Off)?\]\s*", "", name).strip()
    return rest if rest and (rest[0].isupper() or rest[0].isdigit()) else name


def read_database(path):
    """-> (game code, crc, title, [folder]) with folder = dict(name, note, one, codes=[dict(name, note, ops)])."""
    game = crc = title = None
    folders, top, cur, last = [], None, None, None
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@game"):
            p = s.split(None, 3)
            game, crc, title = p[1], int(p[2], 16), p[3] if len(p) > 3 else p[1]
        elif s.startswith("@folder"):
            cur = {"name": s[7:].strip(), "note": "", "one": False, "codes": []}
            folders.append(cur)
            last = cur
        elif s == "@one":
            if cur is not None:
                cur["one"] = True
        elif s == "@end":
            cur = None
        elif s.startswith("@note"):
            if last is not None:
                last["note"] = s[5:].strip()
        elif s.startswith("@code"):
            last = {"name": s[5:].strip(), "note": "", "ops": []}
            if cur is None:
                if top is None:
                    top = {"name": "", "note": "", "one": False, "codes": []}
                    folders.append(top)
                top["codes"].append(last)
            else:
                cur["codes"].append(last)
        else:
            p = s.split()
            if len(p) == 2 and last is not None and "ops" in last:
                try:
                    last["ops"].append((int(p[0], 16), int(p[1], 16)))
                except ValueError:
                    pass
    return game, crc, title, folders


def read_cheat_file(path):
    name, about, mode, cat, ops = os.path.basename(path)[:-4], "", "always", "", []
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if s.startswith("#"):
            m = re.match(r"#\s*(\w+)\s*:\s*(.*)", s)
            if m:
                k, v = m.group(1).lower(), m.group(2).strip()
                if k == "name":
                    name = v
                elif k == "about":
                    about = (about + " " + v).strip()
                elif k == "mode":
                    mode = v.lower() if v.lower() in ("once", "toggle") else "always"       # toggle: a button that is switched on and off (Vanish)
                elif k == "category":
                    cat = v
            continue
        p = s.split()
        if len(p) == 2:
            try:
                ops.append((int(p[0], 16), int(p[1], 16)))
            except ValueError:
                pass
    return name, about, mode, cat, ops


def file_header(path, key):
    """the value of "# key: ..." in a file; several "# about:" lines are one text"""
    out = []
    for line in open(path, encoding="utf-8-sig"):
        m = re.match(r"#\s*(\w+)\s*:\s*(.*)", line.strip())
        if m and m.group(1).lower() == key:
            out.append(m.group(2).strip())
            if key != "about":
                break
    return " ".join(out)


def fit_code_file(rom, checks, patches, tags=None):
    """A hand-made code mod's instructions in this ROM: [(module, address, word)], or None.
    tags ({address: module name}, see apply_code_mods.mod_tags): lines that name their module are looked for there only, and every
    module the file names has to fit; the untagged lines are found in whichever one module fits them all."""
    tags = tags or {}
    out = []
    groups = {}
    for a, w in checks:
        groups.setdefault(tags.get(a), ([], []))[0].append((a, w))
    for a, w in patches:
        groups.setdefault(tags.get(a), ([], []))[1].append((a, w))
    for tag, (cks, pts) in groups.items():
        found = False
        for m in [rom.main] + rom.overlays:
            if tag and m.name != tag:
                continue
            ways = [rom.to_rom, lambda a: a] if m is rom.main else [lambda a: a]
            for ra in ways:
                if all(m.word(ra(a)) == w for a, w in cks) and all(m.word(ra(a)) is not None for a, _ in pts):
                    out += [(m.name, ra(a), w) for a, w in pts]
                    found = True
                    break
            if found:
                break
        if not found:
            return None
    return sorted(set(out)) or None


def page_of(folder):
    for pat, page, prefix in PAGES:
        if re.search(pat, folder, re.I):
            return page, prefix
    return (strip_keys(folder) or "Miscellaneous"), ""


def db_id(folder, name, ops):
    text = folder + "\0" + name + "\0" + ",".join(f"{a:08X}{b:08X}" for a, b in ops)
    return f"db:{zlib.crc32(text.encode('utf-8')) & 0xFFFFFFFF:08x}"


LP_BASE = 0x02F60000        # a write here is "instruction site #n is patched" (mod_cheats.c / livepatch.c), not memory


def read_livepatch(root):
    """{(module, address): site number} of the instruction sites the built game can patch while it runs."""
    out = {}
    try:
        for line in open(os.path.join(root, "mods", "system", "bin", "livepatch.txt"), encoding="utf-8"):
            w = line.split()
            if len(w) >= 3 and not line.startswith("#"):
                out[(w[1], int(w[2], 16))] = int(w[0])
    except OSError:
        pass
    return out


# ---- curated by hand (see NOTES.md 2026-11-14): (page, name in the R4 list) -> what the window shows
RENAME_GROUPS = {
    ("Alchemy", "Always"): "Alchemiracle (great success in the Krak Pot)",
    ("Alchemy", "Every time / Never"): "Alchemiracle (great success in the Krak Pot)",     # (the two files alchemiracle-*.txt)
}
RENAME_OPTIONS = {
    ("Alchemy", "Always Success v2"): "Every time",      # sets the Alchemiracle chance to 100% (ov006 0215e720)
    ("Alchemy", "Always Fail"): "Never",                 # ... to 0%
}
# the R4 list has two "Unlock All Extra Quests V1" and two "V2": the second pair writes 8s instead of 9s and its note says
# "do not go on Nintendo Wifi", i.e. it also opens the quests that came over Wi-Fi. By id, the names being the same.
RENAME_IDS = {
    "db:0a4a78a6": "Unlock All Extra Quests V1",
    "db:d1dfd609": "Unlock All Extra Quests V2",
    "db:3c7d9957": "Unlock All Extra Quests V1, with the Wi-Fi quests",
    "db:e7e837f8": "Unlock All Extra Quests V2, with the Wi-Fi quests",
}
# the R4 list's names, as the window shows them: typos and unclear names fixed (the hover texts in about.tsv are found by
# the old name as well). Group titles lose a trailing "Code"/"Codes" by themselves.
# The R4 list is written in Title Case; the window uses sentence case ("Fight 3 of the same monster"). Words that are names stay.
KEEP_CAPS = {"HP", "MP", "EXP", "ATK", "DEF", "AGI", "Zoom", "Coup", "Grace", "Wi-Fi", "Stornway", "Observatory", "Angel", "Falls", "Alchenomicon",
             "Alchemenu", "Alchemiracle", "Krak", "Pot", "Quester's", "Rest", "Soul", "Asylum", "Wings", "Hero", "Player", "Start", "Select", "Up", "Down",
             "Left", "Right"}


# cheats that stay a switch although their code has one button: they are not a one-time effect (the encounter counter is held at 0, the push is
# in the middle of a spell...)
KEEP_SWITCH = r"no random battles|push enemy away|zoom then push|grotto|re-zoom|walk through a door"


def tidy(s):
    out, start = [], True
    for w in s.split(" "):
        m = re.match(r"^([(\[\"']*)(.*?)([)\]\"',.:;]*)$", w)
        pre, core, post = m.groups()
        if start or not core or core in KEEP_CAPS:
            out.append(w)
        else:
            parts = ["/".join(p[:1].lower() + p[1:] if p[:1].isupper() and p[1:].islower() and p not in KEEP_CAPS else p for p in core.split("/"))]
            out.append(pre + parts[0] + post)
        start = post.endswith(":")
    return " ".join(out)


LABELS = {
    "Hold [A] To Walkthrough Walls": "Walk through walls",           # always on while switched on: nothing to hold
    "Highlight an item in the bag": "99 of the bag item under the cursor",
    "All Boot and Shoe": "All Boots and Shoes",
    "All shield": "All Shields",
    "Hero Size Modifer": "Hero Size Modifier",
    "Hide The Party": "Hide the Party",
    "All Charaters All Stats 999": "All Characters All Stats 999",
    "Alchemy Recipies - Not Forged": "Alchemy Recipes: all discovered, none made yet",
    "Alchemy Recipies - Forged": "Alchemy Recipes: all discovered and made",
    "Palladin": "Paladin",
    "360 Camera Angle WorldMap": "360 Camera Angle World Map",
    "Fill in All ? ? ? of Extra Quest": "Fill in All ??? of Extra Quests",
    "All Member in Party Skill Points x500": "All Party Members Skill Points x500",
    "Battle Won Max": "Battles Won Max",
    "Quest Completed Max": "Quests Completed Max",
    "Treasure Hunted Max": "Treasures Hunted Max",
    "Max WiFi Time": "Max Wi-Fi Time",
    "Hero MAX ATK/DEF/AGIL": "Hero Max ATK/DEF/AGI",
    "Hold [L/R] Walkthrough A Door/Stairs to Go Observatory/Stornway": "Hold [L/R] Walk Through a Door/Stairs to Go to the Observatory/Stornway",
    "To View Character Animation Before A Battle": "View Character Animation Before a Battle",
    "Kracking w/o Ingredients": "Kracking without Ingredients",
    "Disabling Movement of P2": "Disable Movement of P2",
    "Night Time, push Start and Down": "Nighttime, push Start and Down",
    # the USA list's names
    "Item Amount Modifier": "99 of the bag item under the cursor",
    "Walkthrough A Door/Stairs to Go Observatory/Stornway": "Walk Through a Door/Stairs to Go to the Observatory/Stornway",
    "Fight Three of The Same Monster": "Fight Three of the Same Monster",
    "View Character Animation Before A Battle": "View Character Animation Before a Battle",
    "Day": "Daytime, push Start and Up",
    "Night": "Nighttime, push Start and Down",
}
# the grey line's notes from the R4 list, in plain words (part of a note -> the new words)
NOTES = {
    "Regain Wings in Angel Falls, push L+R+START+Up, enter or exit house then,L+R+START+Down, then enter or exit house again, must have 3 or less in the party and might require to reactivate the codes after certain and save loading.Special Thanks to dsrules":
        "Push L+R+START+UP, enter or leave a house, then push L+R+START+DOWN and enter or leave a house again. Three or fewer in the party; after loading a save it may have to be switched on again. Thanks to dsrules.",
    "Used at own risk": "Use at your own risk.",
    "It makes the rest of the character stay on ground": "The other characters stay on the ground.",
    "It makes all monsters item drop count to 127": "Sets every monster's item drop count to 127.",
    "Note:- open a chest, enter/exit battle records (or equipment) or re-enter same floor to close chest": "Open a chest, then open and close the battle records (or the equipment screen) or enter the floor again: the chest is closed.",
    "::: use after completed Quests 2, 117 & 120, do not go on Nintendo Wifi": "Use after completing quests 2, 117 and 120. Don't go on Nintendo Wi-Fi.",
    "use it on a new game before accepting any quests, do not go on Nintendo Wifi": "Use it on a new game before accepting any quest. Don't go on Nintendo Wi-Fi.",
    "use it on a new game before accepting any quests": "Use it on a new game before accepting any quest.",
    "use after completed all 120 Normal Quests": "Use after completing all 120 normal quests.",
    "face value": "",
    "Option Is Still Grey in Colour": "The option still looks grey.",
    "Activate Before Attack": "Switch it on before attacking.",
    "Fight 3 of the Same Monster, Hold A and Right Before Engaging Battle": "Hold A and RIGHT just before a battle starts.",
    "activate it when you want to see the animation on your next 1 battle": "Switch it on to see the animation in your next battle.",
    "Enter Treasure Maps mode, push R when Zooming to zoom to the exact location of the cave": "In treasure map mode, push R while zooming to go to the exact spot of the grotto.",
    "Highlight an item in the bag, activate code, and get 99 - Press Start + R to activate. Note:- only use for items in bag. doesn't work while in stornway inn":
        "Move the cursor to an item in the bag and press START+R: you get 99 of it. Only for items in the bag; not in the Stornway inn.",
    "Need to reactivate after leveling up, or equipment change.": "Switch it on again after a level-up or a change of equipment.",
    "location=spot after screen blacks out (in/out door, exit Battle Records)": "The spot is where you are when the screen blacks out (through a door, leaving the battle records).",
    "It might not contain all consumable items": "It might not have every consumable item.",
    # the USA list's notes
    "Needs to be reactivated after leveling up or chaning equipment.": "Switch it on again after a level-up or a change of equipment.",
    "This will take affect everywhere.": "It works everywhere.",
    "(Press A+L to increase the head size, A+R to decrease the head size)": "(Press A+L to make the hero bigger, A+R to make them smaller)",
    "(Press Start+R while highlighting an item in the bag): Use this only for items in the bag, this will not work while in the Stornway Inn.":
        "Move the cursor to an item in the bag and press START+R: you get 99 of it. Only for items in the bag; not in the Stornway inn.",
    "This might not contain all consumable items.": "It might not have every consumable item.",
    "This makes all monsters item drop counts to 127.": "Sets every monster's item drop count to 127.",
    "WARNING: This may break the main story of the game, use this at your own risk.": "It may break the main story: use it at your own risk.",
}

# codes another entry does the same as, better: the [L/R] toggle wrote the roll itself (R: never, L: always, the opposite
# of its name), and "Always Alchemiracle" sets the result flag afterwards; "Every time" / "Never" set the chance.
# "Debug Code" changes two constants of a boot function (main 02000ec8/02000ef0) to an effect nobody describes: left out.
LABELS.update({                    # the records' names: "Max ..." first
    "Max WiFi Time": "Max Wi-Fi time",
    "Max Game Time": "Max game time",
    "Battle Won Max": "Max battles won",
    "Quest Completed Max": "Max quests completed",
    "Treasure Hunted Max": "Max treasures hunted",
    "Visitors Max": "Max visitors",
    "Forge Max": "Max items made by alchemy",
    "Inn Max Level/Upgrades": "Inn: max level and upgrades",
    "Zoom Then Push [R] to Grotto Cave Location": "Zoom then push [R] to grotto cave location",
})
HIDE = {("Alchemy", "Always Success (R)"), ("Alchemy", "Always Success (L)"), ("Alchemy", "Always Alchemiracle"),
        ("Alchemy", "Always Success v1 (R)"), ("Alchemy", "Always Success v1 (L)"),          # (the USA list's names)
        ("Speed & comfort", "Debug Code"), ("Speed & comfort", "Debug Mode"),          # (EU / USA name)
        ("World", "Daytime, push Start and Up"), ("World", "Nighttime, push Start and Down"),     # "Make it day" / "Make it night" do the same, with a button
        ("Miscellaneous", "Widescreen"),                    # USA list: not needed on a PC (the game has its own wide view)
        # USA list: its call goes to the game's random number generator (main 02003d14) where ov024 checks the chance
        # (021dfbcc), and it ORs bits into that loop's counter: not "100%", and not safe
        ("Battle", "100% Steal Rate")}
# not needed: the game's own wireless menu (the quest giver's Wi-Fi button) opens the Wi-Fi quests
HIDE_RE = r"wi-?fi quests"


def read_about(root):
    """mods/system/about.tsv: name (lower case) -> the hover text"""
    out = {}
    try:
        for line in open(os.path.join(root, "mods", "system", "about.tsv"), encoding="utf-8-sig"):
            if line.startswith("#") or "\t" not in line:
                continue
            k, t = line.rstrip("\r\n").split("\t", 1)
            out[k.strip().lower()] = clean(t)
    except OSError:
        pass
    return out


def repeats(text, note):
    """the text adds (almost) nothing to the note: most of its words are already there"""
    words = lambda x: set(re.findall(r"[a-z0-9']+", x.lower()))
    t, n = words(text), words(note)
    return not t or (len(t) <= len(n) + 3 and len(t & n) >= 0.8 * len(t))


def build(root):
    """-> (info, entries, groups). An entry is a dict; see write() for what the window gets."""
    rom = Rom(root)
    entries, groups = [], []

    # ---- the hand-made files first: a database code that does the same becomes that file's
    by_sig = {}
    files = []
    live_files, code_files = acm.hand_files(root)
    for f in live_files:
        base = os.path.basename(f)
        name, about, mode, cat, ops = read_cheat_file(f)
        if not ops:
            continue
        keys, _ = scan(ops)
        e = dict(id="file:cheats/" + base, name=name, note=about, cat=cat, group="", kind="live", status=file_header(f, "status") or "tested",
                 mode=mode, ops=ops, keys=keys, reason="", file="", on=False, patch=[], env="",
                 also=file_header(f, "also"), replaces=file_header(f, "replaces"))
        if len(ops) > 1023:
            e.update(kind="blocked", status="blocked", reason=REASONS["long"])
        files.append(e)
        by_sig.setdefault(("live", tuple(ops)), e)
    for f in code_files:
        base = os.path.basename(f)
        name, on, checks, patches, errors = acm.parse_mod(f)
        e = dict(id="file:code/" + base, name=name, note=file_header(f, "about"), cat=file_header(f, "category"),
                 group="", kind="code", status=file_header(f, "status") or "tested", mode="", ops=[], keys=[], reason="",
                 file="system/cheats/" + base, on=on, patch=[], env="",
                 also=file_header(f, "also"), replaces=file_header(f, "replaces"))
        fit = None if errors else fit_code_file(rom, checks, patches, acm.mod_tags(f))
        if errors:
            e.update(kind="blocked", status="blocked", reason="The file has a mistake: " + "; ".join(errors))
        elif not fit:
            e.update(kind="blocked", status="blocked", reason=REASONS["nomatch"])
        else:
            e["patch"] = fit
            by_sig.setdefault(("code", tuple(fit)), e)
        files.append(e)
    used, seen_sigs = set(), set()

    # ---- the database for this ROM
    info = dict(game=rom.game, region=rom.region, title="", database="", exact="0")
    db = os.path.join(root, "mods", "system", "cheats", "r4-" + rom.game + ".txt")
    folders = []
    if os.path.isfile(db):
        game, crc, title, folders = read_database(db)
        info.update(title=title, database=os.path.basename(db), exact="1" if crc == rom.crc else "0")
    for folder in folders:
        page, prefix = page_of(folder["name"]) if folder["name"] else ("System", "")
        if page == "System":
            continue                                        # backlight / Wi-Fi / anti-piracy codes: not needed on a PC
        made = []
        for c in folder["codes"]:
            if not c["ops"]:
                continue                                    # a line of text in the list ("Use V1 or V2 only")
            r = classify(rom, c["ops"])
            moved = False
            if r["kind"] == "blocked" and r["why"] == "nomatch" and rom.shifts:
                # the database sometimes lists a USA code under the European game: the same code,
                # moved to where this ROM has it, counts when its instructions are there
                r2 = classify(rom, moved_for_rom(rom, c["ops"]))
                if r2["kind"] == "code":
                    r, moved = r2, True
            if re.search(r"backlight", c["name"], re.I):
                r = dict(r, kind="blocked", why="hardware")
            shown = strip_keys(c["name"])
            note = c["note"] if clean(c["note"]) != clean(c["name"]) else ""
            if len(shown) > 60:                             # a name with the instructions in it: those go below
                cut = re.split(r", | - |\. |: ", shown, maxsplit=1)[0]
                if 10 <= len(cut) < len(shown):
                    note, shown = note if len(note) >= len(c["name"]) else clean(c["name"] + ". " + note).rstrip(". ") , cut
            continuous = any(a >> 28 == 0xA for a, b in c["ops"])      # "A" ops copy one value to another all the time
            one_shot = len(r["keys"]) <= 1 and not continuous and not re.search(KEEP_SWITCH, c["name"], re.I)
            base = dict(id=db_id(folder["name"], c["name"], c["ops"]), name=prefix + shown, prefix=prefix,
                        note=note, cat=page, group="",
                        status="untested", mode=("once" if one_shot else "always" if continuous or re.search(r"push enemy away", c["name"], re.I) else "both") if len(r["keys"]) <= 1 else "always", ops=[],
                        keys=[] if one_shot else r["keys"], reason="", file="", on=False, patch=[], env="", option=shown)
            if re.search(r"anti-?piracy", c["name"], re.I):
                r = dict(r, kind="blocked", why="piracy")
            elif re.search(r"wfc|https|wi-?fi connection", c["name"], re.I) and r["kind"] != "live":
                r = dict(r, kind="blocked", why="wfc")
            if r["kind"] == "blocked":
                made.append(dict(base, kind="blocked", status="blocked", reason=REASONS[r["why"]], mode=""))
            elif r["kind"] == "live":
                made.append(dict(base, kind="live", ops=c["ops"]))
            else:
                many = len(r["variants"]) > 1
                for i, (label, patch) in enumerate(r["variants"]):
                    e = dict(base, kind="code", mode="", patch=patch, keys=[])
                    if many:
                        e.update(id=f"{base['id']}:{i}", name=f"{base['name']} ({label or i + 1})",
                                 option=f"{shown} ({label or i + 1})")
                    if moved:
                        e["note"] = clean(e["note"] + " (Listed with the USA version's addresses; moved to where your ROM has these instructions.)")
                    if r.get("held"):
                        held = " / ".join(k for k in (key_text(k) for k in r["keys"]) if k)
                        first = e["note"] + ("" if not e["note"] or e["note"].rstrip()[-1] in ".!?)" else ".")
                        e["note"] = clean(first + f" On a DS you hold or press {held or 'a button'} for this; here it is simply on.")
                    made.append(e)
        # the list has some codes twice (in two folders): once is enough
        for e in list(made):
            sig = ("live", tuple(e["ops"])) if e["kind"] == "live" else ("code", tuple(e["patch"])) if e["kind"] == "code" else None
            if sig in seen_sigs and not folder["one"]:
                made.remove(e)
            elif sig:
                seen_sigs.add(sig)
        # a file that does exactly the same takes the code's place (its name, its switch, "tried out")
        for e in made:
            twin = by_sig.get(("live", tuple(e["ops"]))) if e["kind"] == "live" else \
                by_sig.get(("code", tuple(e["patch"]))) if e["kind"] == "code" else None
            if twin is not None and twin["id"] not in used:
                used.add(twin["id"])
                e.update(id=twin["id"], name=twin["name"], note=twin["note"] or e["note"], status="tested",
                         mode=twin["mode"], file=twin["file"], on=twin["on"], also=twin.get("also", ""))
        choice = [e for e in made if e["kind"] in ("live", "code")]
        if folder["one"] and len(choice) > 1 and len({e["kind"] for e in choice}) == 1:
            gid = "group:" + f"{zlib.crc32(folder['name'].encode('utf-8')) & 0xFFFFFFFF:08x}"
            groups.append(dict(id=gid, cat=page, title=strip_keys(folder["name"]), note=folder["note"], kind=choice[0]["kind"]))
            for e in choice:
                e["group"] = gid
        entries += made

    # ---- the files no database code matched
    for e in files:
        if e["id"] not in used:
            e["cat"] = e["cat"] or "Miscellaneous"
            e["option"] = e["name"]
            entries.append(e)

    # ---- "# replaces: <names, separated by |>" in a file: our own cheat takes the place of those database codes
    repl = set()
    for e in files:
        if e["kind"] == "blocked":
            continue                                        # a file that doesn't fit this ROM leaves the database's code in place
        for r in e.get("replaces", "").split("|"):
            if r.strip():
                repl.add(r.strip().lower())
    if repl:
        entries = [e for e in entries if not (e["id"].startswith("db:") and
                                              (e["name"].lower() in repl or e.get("option", "").lower() in repl))]

    # ---- code mods that change the same instruction differently can't be on together: one choice
    code = [e for e in entries if e["kind"] == "code"]
    parent = {e["id"]: e["id"] for e in code}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    where = {}
    for e in code:
        for name, a, w in e["patch"]:
            for other, ow in where.get((name, a), []):
                if ow != w:
                    parent[find(e["id"])] = find(other)
            where.setdefault((name, a), []).append((e["id"], w))
    sets = {}
    for e in code:
        sets.setdefault(find(e["id"]), []).append(e)
    for members in sets.values():
        if len(members) < 2:
            continue
        gids = {e["group"] for e in members if e["group"]}
        if len(gids) == 1 and all(e["group"] for e in members):
            continue                                        # already one folder's choice
        if gids:
            gid = sorted(gids)[0]
            g = next(g for g in groups if g["id"] == gid)
        else:
            gid = "group:" + f"{zlib.crc32(members[0]['id'].encode('utf-8')) & 0xFFFFFFFF:08x}"
            names = [e["name"] for e in members]
            common = os.path.commonprefix(names).rstrip(" x(-:")
            g = dict(id=gid, cat=members[0]["cat"], title=common if len(common) >= 6 else " / ".join(names[:3]), note="", kind="code")
            groups.append(g)
        for e in members:
            if not e["group"]:
                e["option"] = e["name"]
            e["group"], e["cat"] = gid, g["cat"]
    # ---- curated: clearer names for some database choices, and codes another entry does better
    for e in entries:
        for (page, old), new in RENAME_OPTIONS.items():
            if e["id"].startswith("db:") and e["cat"] == page and e.get("option", e["name"]) == old:
                e["name"] = e["option"] = new
        if e["id"] in RENAME_IDS:
            e["name"] = e["option"] = RENAME_IDS[e["id"]]
    for g in groups:
        g["title"] = RENAME_GROUPS.get((g["cat"], g["title"]), g["title"])
    for e in entries:
        e["was"] = e.get("option") or e["name"]
        for k in ("name", "option"):
            if e.get(k) in LABELS:
                e[k] = LABELS[e[k]]
        for old, new in NOTES.items():
            if old in e["note"]:
                e["note"] = clean(e["note"].replace(old, new))
        m = re.match(r"\((?:Press and hold|Press|Hold) ([A-Za-z]+(?:\s*\+\s*[A-Za-z]+)*)\)\s*:?\s*", e["note"])
        if m and e.get("keys") and all(w.strip().upper() in KEY_NAMES for w in m.group(1).split("+")):
            e["note"] = e["note"][m.end():]
            if e["note"]:
                e["note"] = e["note"][0].upper() + e["note"][1:]
    for g in groups:
        g["was"] = g["title"]
        g["title"] = re.sub(r"\s+Codes?$", "", g["title"])
        g["title"] = LABELS.get(g["title"], g["title"])
        if re.match(r"group:[0-9a-f]{6,}$", g["id"]):
            g["title"] = tidy(g["title"])
    entries = [e for e in entries if not (e["id"].startswith("db:") and ((e["cat"], e["name"]) in HIDE or re.search(HIDE_RE, e["name"], re.I)))]
    for e in entries:                                       # the list's own names, in sentence case (a choice's options keep theirs: vocations, monsters)
        if e["id"].startswith("db:") and not e["group"]:
            same = e.get("option") == e["name"]
            e["name"] = tidy(e["name"])
            e["option"] = e["name"] if same else tidy(e.get("option") or e["name"])
    # two cheats of a page that would show the same name ("Enemy 1" for HP 1 and for MP 0): the folder's prefix tells them apart
    seen = {}
    for e in entries:
        if not e["group"] and e["kind"] != "blocked":
            seen.setdefault((e["cat"], e.get("option") or e["name"]), []).append(e)
    for same in seen.values():
        if len(same) > 1:
            for e in same:
                if e.get("prefix") and not (e.get("option") or "").startswith(e["prefix"]):
                    e["option"] = e["prefix"] + (e.get("option") or e["name"])

    for e in entries:                                       # "Player 1" alone (the USA list's name) doesn't say what it does
        if e["id"].startswith("db:") and not e["group"] and re.fullmatch(r"Player \d", e.get("option") or ""):
            e["option"] = e["name"]

    for old in [g for g in groups if not any(e["group"] == g["id"] for e in entries)]:
        groups.remove(old)

    # ---- "Battle any monster you want": our own version of the database's code, one choice with every ordinary monster
    try:
        import rom_text
        nds = rom_text.Nds(os.path.join(root, "game", "data", "dqix.nds"))
        mons = rom_text.monsters(nds)
        mons_boss = rom_text.monsters(nds, bosses=True)
    except Exception:
        mons, mons_boss = [], []
    try:
        legacy = legacy_bosses(nds) if mons else []
    except Exception as ex:
        print("catalog: no legacy boss levels (%s)" % ex)
        legacy = []
    try:
        songs = boss_songs(nds) if mons else {}
    except Exception as ex:
        print("catalog: no boss songs (%s)" % ex)
        songs = {}
    if mons:
        entries = [e for e in entries if not (e["id"].startswith("db:") and e["name"].lower().startswith("battle any monsters you want"))]
        gid = "group:battle-any-monster"
        groups.append(dict(id=gid, cat="Battle", title="Battle any monster you want", note="Every monster that roams the field, and the bosses (marked boss); the legacy bosses also at Lv 50 and Lv 99, with that level's form, HP and stats (moves they learn by level are all open, as at Lv 99). Works at once, no restart: the monsters of the place still roam, and every battle they start is against the one you chose (as many as the group had; a boss alone). A boss plays its own battle music: the boss theme, a legacy boss its own.", kind="live"))
        for num, mname in mons + [(n, "%s (boss)" % m) for n, m in mons_boss]:
            # tested: tests/test_force_data.c (all 288 hand out exactly that monster) and the 288-run crash check (NOTES 2026-11-13)
            # live: a write to the switch 02F5A5B4 (mod_cheats.c) every frame says which monster; forcebtl.c makes the battles it (+ 0x10000: a boss, alone;
            # bits 24..31: a boss's song, its story battle's or 24, the boss song: forcebtl.c plays it instead of the usual battle song)
            boss = mname.endswith("(boss)")
            entries.append(dict(id=f"live:monster:{num}", name=mname, note="", cat="Battle", group=gid, kind="live", status="untested",
                                mode="always", ops=[(FORCE_SWITCH, num | (0x10000 | songs.get(num, 24) << 24 if boss else 0))], keys=[], reason="", file="", on=False, patch=[],
                                env="", option=mname, also=""))
        boss_names = dict(mons_boss)
        for base, _bands, lv in sorted(legacy, key=lambda x: boss_names.get(x[0], "")):
            for level, (mon, words) in sorted(lv.items()):
                if base not in boss_names:
                    continue
                mname = "%s, legacy Lv %d (boss)" % (boss_names[base], level)
                # live: the choice word carries the level (bits 17..23), the song (24..31: the legacy boss's own, as in its grotto) and 02F5A600.. the
                # level's stats; forcebtl.c puts them on the boss
                entries.append(dict(id=f"live:monster:{base}:lv{level}", name=mname, note="", cat="Battle", group=gid, kind="live", status="untested",
                                    mode="always", ops=[(FORCE_SWITCH, mon | 0x10000 | level << 17 | songs.get(mon, songs.get(base, 24)) << 24)]
                                    + [(LEGSTAT_SWITCH + 4 * i, w) for i, w in enumerate(words)],
                                    keys=[], reason="", file="", on=False, patch=[], env="", option=mname, also=""))

    # ---- the Nuzlocke randomizers: one launch option each, and the seed as one choice
    if acm.NUZLOCKE_ENABLED:
        for lid, name, env, note in NZ_LAUNCH:
            entries.append(dict(id=lid, name=name, note=note, cat="Nuzlocke", group="", kind="launch", status=NZ_STATUS,
                                mode="", ops=[], keys=[], reason="", file="", on=False, patch=[], env=env, option=name, also=""))
        gid = "group:nz-seed"
        groups.append(dict(id=gid, cat="Nuzlocke", title="Seed", note="Which game the randomizers make. Without a choice the seed is 1. The same seed always gives the same game; pick another one before you start a new run.", kind="launch"))
        for n in range(1, NZ_SEEDS + 1):
            entries.append(dict(id=f"launch:nz-seed:{n}", name=f"Seed {n}", note="", cat="Nuzlocke", group=gid, kind="launch", status=NZ_STATUS,
                                mode="", ops=[], keys=[], reason="", file="", on=False, patch=[], env=f"DQIX_MOD_NZ_SEED={n}", option=f"Seed {n}", also=""))
    # ---- a button on the Battle page that opens the battle window (the cards); kind "ui": no code, the window opens the window
    entries.append(dict(id="ui:battle-window", name="Battle window", option="Battle window", note="A window with a card for every party member and enemy in the fight, and big buttons for buffs and debuffs.",
                        cat="Battle", group="", kind="ui", status="tested", mode="once", ops=[], keys=[], reason="", file="", on=False, patch=[], env="", also=""))
    # ---- the live battle cheats (see BATTLE_PAGE): the database's codes that write the same bytes are replaced by them
    bad = battle_addr_set()

    def hits(e):
        for a, b in e.get("ops") or []:
            if a >> 28 in (0, 1, 2, 6, 0xA) or a >> 24 in (0xDA, 0xD7):
                if (a & 0x0FFFFFFF) in bad or (a >> 24 in (0xDA, 0xD7) and b in bad):
                    return True
        return False
    entries = [e for e in entries if not (e["id"].startswith("db:") and e["kind"] == "live" and hits(e))]
    groups = [g for g in groups if any(e["group"] == g["id"] for e in entries) or g["kind"] == "launch"]
    for eid, name, who, ops, mode, note in battle_entries():
        entries.append(dict(id=eid, name=name, option=name, note=note, cat=BATTLE_PAGE, group="", kind="live", status="untested", mode=mode, ops=ops,
                            keys=[], reason="", file="", on=False, patch=[], env="", also="", was=who, who=who))
    # ---- how the game is started
    for lid, name, env, note, cat, also in LAUNCH:
        entries.append(dict(id=lid, name=name, note=note, cat=cat, group="", kind="launch",
                            status="tested",
                            mode="", ops=[], keys=[], reason="", file="", on=False, patch=[], env=env, option=name, also=also))
    # ---- what a cheat does, the same for both ROMs: a code mod's instructions (kept with USA addresses for either ROM),
    # else its data writes (the RAM addresses are the same in the USA and the European game). verified.txt can name it
    # ("sig:..."), so a cheat confirmed on one ROM counts on the other when its code is the same.
    for e in entries:
        what = [(n, rom.from_rom(a) if n == "main" else a, w) for n, a, w in e["patch"]] if e.get("patch") else e.get("ops")   # (USA addresses)
        e["sig"] = "sig:%08x" % (zlib.crc32(repr([tuple(x) for x in what]).encode()) & 0xFFFFFFFF) if what else ""
    # ---- code mods that run live: the build wraps every function they touch (mods/system/bin/livepatch.txt, written by
    # apply_runtime_mod.py), so the game applies their instructions while it runs and switching needs no rebuild.
    sites = read_livepatch(root)
    if sites:
        def lp_ok(e):
            return e["kind"] == "code" and e["patch"] and all((n, a) in sites for n, a, w in e["patch"])
        grp_ok = {g["id"]: all(lp_ok(e) for e in entries if e["group"] == g["id"]) for g in groups if g["kind"] == "code"}
        for e in entries:
            if lp_ok(e) and grp_ok.get(e["group"], True):
                e.update(kind="live", mode="always", keys=[], lp=1,
                         ops=[(LP_BASE + 4 * sites[(n, a)], w) for n, a, w in e["patch"]])
        for g in groups:
            if grp_ok.get(g["id"]):
                g["kind"] = "live"

    # ---- the hover box: mods/system/about.tsv, by the name the window shows (a choice by its title). A text that only
    # repeats the grey line's note says nothing new and is left out.
    about = read_about(root)
    for e in entries:
        t = about.get(e["name"].lower()) or about.get(e.get("option", "").lower()) or about.get(e.get("was", "").lower(), "")
        if not t and e["name"].startswith("Hero max skill: "):          # the USA list's one-skill codes
            t = "Puts the hero's " + e["name"][len("Hero max skill: "):] + " at its maximum: every ability of that skill is learned."
        e["about"] = "" if repeats(t, e["note"]) else t
    for g in groups:
        g["about"] = about.get(g["title"].lower()) or about.get(g.get("was", "").lower(), "")

    # ---- cheats whose effect an automated test confirmed (mods/system/verified.txt) count as tried out
    try:
        ok = set(l.split()[0] for l in open(os.path.join(root, "mods", "system", "verified.txt"), encoding="utf-8") if l.strip() and not l.startswith("#"))
    except OSError:
        ok = set()
    for e in entries:
        if e["status"] == "untested" and (e["id"] in ok or (e.get("sig") and e["sig"] in ok)):
            e["status"] = "tested"

    # ---- "Can always use Coup de Grace" (both R4 lists): our own version, with the same id (the window remembers it). Theirs skipped the battle
    # menu's check (ov000 0217b2c4), so the game didn't know and drew the text grey; this one sets the game's own "ready" flag every frame
    # (mod_cheats.c mc_battle_locks): offered, lit up, and ready again right after it's used.
    for e in entries:
        if e["id"].startswith("db:") and [tuple(p) for p in e.get("patch") or []] == COUP_SKIP_PATCH:
            e.update(kind="live", mode="always", patch=[], ops=[(COUP_SWITCH, 0xF)], keys=[], status="untested", reason="",
                     name="Coup de Grace always ready", option="Coup de Grace always ready",
                     note="The whole party, in every battle: the Coup de Grace command is lit up like a real one and can be used every turn.",
                     about="Everyone in the party has their Coup de Grace (their vocation's finishing move) ready all the time, the way the game itself sets it, so the battle menu shows it lit up, not grey. After it's used it is ready again at once.")

    # ---- "Always high tension", next to it on the Battle page (Party buffs): the whole party, the game's own way (mod_cheats.c mc_battle_locks)
    entries.append(dict(id="live:party:tension", name="Always high tension", option="Always high tension", cat="Battle", group="", kind="live",
                        status="untested", mode="always", ops=[(TENSION_SWITCH, 0xF)], keys=[], reason="", file="", on=False, patch=[], env="", also="",
                        note="The whole party, in every battle: tension stays at the top (100), and it is back at once after it's used.",
                        about="Every party member's tension is kept at 100, the way Psyche Up raises it (with its aura), so every attack and spell is at full tension. "
                              "After an action uses it, it is back at once. As in the game, a member who is down or under a status that stops tension doesn't get it."))

    # ---- "Always 4-hit combo", with it: every hit of a party member counts as the fourth of a combo (challenges.c force_combo)
    entries.append(dict(id="live:party:combo", name="Always 4-hit combo", option="Always 4-hit combo", cat="Battle", group="", kind="live",
                        status="untested", mode="always", ops=[(COMBO_SWITCH, 0xF)], keys=[], reason="", file="", on=False, patch=[], env="", also="",
                        note="The whole party, in every battle: every attack or spell that can combo counts as a 4-hit combo, for double damage.",
                        about="Each hit by a party member is treated as the fourth in a row on its target, the game's biggest combo (x2 damage instead of x1.2 / x1.5), "
                              "and the game shows it as a 4-hit combo. Only actions that can combo in the game get it (attacks, most abilities and spells that deal damage); healing and support don't change."))

    # ---- the Challenges page: our own (mod_cheats.c mc_challenges, challenges.c, forcebtl.c), live, every PC of a session the same
    def challenge(eid, name, ops, note, about, group=""):
        entries.append(dict(id=eid, name=name, option=name, cat="Challenges", group=group, kind="live", status="untested", mode="always", ops=ops,
                            keys=[], reason="", file="", on=False, patch=[], env="", also="", note=note, about=about))
    gid = "group:challenge-tough"
    groups.append(dict(id=gid, cat="Challenges", title="Tougher monsters", kind="live",
                       note="Every monster has more HP and hits harder, by the amount you pick: its HP and maximum HP when it shows up, and the damage it deals to your party (attacks, spells and breath). Experience and gold stay the same."))
    for k, label in ((3, "x1.5"), (4, "x2"), (6, "x3")):
        challenge("live:challenge:tough%d" % k, label, [(TOUGH_SWITCH, k)], "Monsters have %s HP and deal %s damage." % (label, label),
                  "Every monster in a battle gets %s its HP (up to 65535) as it shows up, and the damage it deals your party is %s (up to 9999), after your defence, buffs and resistances. Bosses and legacy bosses too." % (label, label), gid)
    challenge("live:challenge:nospells", "No spells", [(NOSPELL_SWITCH, 1)],
              "Nobody in the party can cast spells in battle: they're kept under Fizzle. Abilities, items and attacks still work.",
              "Every party member is under Fizzle for the whole battle, the way the spell does it, so the game itself refuses their spells (\"...can't cast spells at the moment\"). Outside battles nothing changes.")
    challenge("live:challenge:noabilities", "No abilities", [(NOABIL_SWITCH, 1)],
              "Nobody in the party can use abilities in battle: one picked turns into Defend when their turn comes. Spells, items and attacks still work.",
              "The abilities of the skill trees (Multithrust, Psyche Up, Whistle, Dragon Slash...) can still be picked in the menu, but when that party member's turn comes they defend instead, and no MP is spent. Coups de grace and the abilities an item or a piece of equipment gives are not affected. Outside battles nothing changes. Together with \"No spells\" only attacks, items and defending are left.")
    challenge("live:challenge:randenc", "Fully random encounters", [(RANDENC_SWITCH, 1)],
              "Every battle a roaming monster starts is against other monsters, picked at random each time, from all the ordinary monsters, whatever their level. With \"Fully random boss encounters\" on too, about one battle in four is a boss instead.",
              "Each group of the battle (up to three kinds) becomes a random ordinary monster, keeping its count: a different mix every time. The monsters you see roaming stay those of the place. \"Battle any monster you want\" takes priority while one is chosen. Monsters of any level can come up, so expect some very hard fights early on.")
    challenge("live:challenge:randboss", "Fully random boss encounters", [(RANDBOSS_SWITCH, 1)],
              "Every battle a roaming monster starts is against a boss, alone, picked at random each time from all the bosses: the story's, the grottos' and the legacy bosses. Each plays its own battle music. Works together with \"Fully random encounters\".",
              "A different boss every battle (never the same one twice in a row), from the 55 bosses of \"Battle any monster you want\", the legacy bosses at their own level. Turn \"Fully random encounters\" on as well to mix them: about one battle in four is a random boss, the rest random ordinary monsters. A monster chosen in \"Battle any monster you want\" goes before both. The monsters you see roaming stay those of the place.")

    # ---- other pages, sections, undo (see MOVES, SECTIONS, UNDO)
    gby = {g["id"]: g for g in groups}

    def text(e):
        g = gby.get(e["group"])
        return " | ".join(x for x in (e["name"], e.get("option", ""), e.get("was", ""), g["title"] if g else "") if x)
    for g in groups:
        for pat, page in MOVES:
            if re.search(pat, g["title"], re.I):
                g["cat"] = page
                break
    for e in entries:
        g = gby.get(e["group"])
        if g:
            e["cat"] = g["cat"]
        else:
            for pat, page in MOVES:
                if re.search(pat, text(e), re.I):
                    e["cat"] = page
                    break
        e["undo"] = "1" if e["kind"] == "live" and re.search(UNDO, text(e), re.I) else ""
    for g in groups:
        g["section"] = section_of(g["cat"], g["title"])
        g["who"] = who_of(g["title"])
    for e in entries:
        g = gby.get(e["group"])
        e["section"] = g["section"] if g else "" if e["kind"] == "ui" else section_of(e["cat"], text(e))
        if not e.get("who"):
            e["who"] = (g["who"] if g else "") or who_of(e["name"], e.get("option", ""), e.get("was", ""))
        if e["section"] and not g and e.get("option") == e["section"]:
            e["option"] = e["name"]                         # "Hero" under the section Hero: "Max EXP in every vocation: Hero"
    return info, entries, groups


def read_state(root):
    """What is switched on in the Cheats window: mods/system/menu-state.txt, lines of "<live|code|launch> <id>"."""
    state = {"live": set(), "code": set(), "launch": set()}
    try:
        for line in open(os.path.join(root, "mods", "system", "menu-state.txt"), encoding="utf-8-sig"):
            p = line.split(None, 1)
            if len(p) == 2 and p[0] in state:
                state[p[0]].add(p[1].strip())
    except OSError:
        pass
    return state


def write(root, info, entries, groups):
    def kv(what, **f):
        return what + "\t" + "\t".join(f"{k}={clean(v)}" for k, v in f.items() if v not in ("", None))

    pages = []
    for e in entries:
        if e["cat"] not in pages:
            pages.append(e["cat"])
    for e in entries:
        if e.get("also") and e["also"] not in pages:
            pages.append(e["also"])
    pages.sort(key=lambda p: (PAGE_ORDER.index(p) if p in PAGE_ORDER else len(PAGE_ORDER) - 1.5, p))
    lines = [kv("info", **info)]
    lines += [kv("page", title=p) for p in pages]
    lines += [kv("section", cat=p, title=t) for p in pages for t, _ in SECTIONS.get(p, [])
              if any(e["cat"] == p and e.get("section") == t and e["kind"] != "blocked" for e in entries)]
    lines += [kv("group", id=g["id"], cat=g["cat"], title=g["title"], note=g["note"], kind=g["kind"], about=g.get("about", ""),
                 section=g.get("section", "")) for g in groups]
    for e in entries:
        lines.append(kv(
            "entry", id=e["id"], cat=e["cat"], group=e["group"], kind=e["kind"], status=e["status"], name=e["name"],
            option=e.get("option", ""), note=e["note"], reason=e["reason"], mode=e["mode"],
            keys=" / ".join(k for k in (key_text(k) for k in e["keys"]) if k), combos=str(len(e["keys"])) if e["keys"] else "",
            file=e["file"], on="1" if e["on"] else "", env=e["env"], also=e.get("also", ""), about=e.get("about", ""),
            section=e.get("section", ""), undo=e.get("undo", ""), who=e.get("who", ""),
            ops=",".join(f"{a:08X}:{b:08X}" for a, b in e["ops"]),
            patch=",".join(f"{n}:{a:08x}:{w:08x}" for n, a, w in e["patch"])))
    out = os.path.join(root, "mods", "system", "bin", "catalog.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    text = "\n".join(lines) + "\n"
    try:
        if open(out, encoding="utf-8", newline="").read() == text:
            return out
    except OSError:
        pass
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return out


def write_monsters(root):
    """mods/system/bin/monsters.tsv for the battle window: an enemy's record holds its species' maximum HP and MP (fld_mondata.bin values 5 and 6), so
    "maxhp<TAB>maxmp<TAB>name" for every ordinary species whose pair is unique tells the window what it is fighting"""
    import rom_text
    nds = rom_text.Nds(os.path.join(root, "game", "data", "dqix.nds"))
    names = dict(rom_text.monsters(nds))
    pairs = {}
    for t, v in rom_text.tagged_records(nds.read("data/prm/fld_mondata.bin")):
        if t == 0x65 and len(v) >= 7 and v[2] != 0:
            pairs.setdefault((v[5], v[6]), set()).add(v[0] & 0xFFF)
    lines = []
    for (hp, mp), nums in sorted(pairs.items()):
        found = {names[n] for n in nums if n in names}
        if len(found) == 1 and all(n in names for n in nums):            # every species with these numbers has the same name
            lines.append("%d\t%d\t%s" % (hp, mp, next(iter(found))))
    out = os.path.join(root, "mods", "system", "bin", "monsters.tsv")
    text = "\n".join(lines) + "\n"
    try:
        if open(out, encoding="utf-8", newline="").read() == text:
            return
    except OSError:
        pass
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if not os.path.isfile(os.path.join(root, "build", "recomp", "dispatch_table.c")):
        print("   The game hasn't been built yet (no build\\recomp): build it once, then run this again.")
        return 1
    info, entries, groups = build(root)
    write(root, info, entries, groups)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        write_monsters(root)
    except Exception as ex:
        print(f"   (enemy names for the battle window: {ex})")
    n = {k: sum(1 for e in entries if e["kind"] == k) for k in ("live", "code", "blocked", "launch")}
    print(f"   Cheat list: {n['live']} live, {n['code']} built into the game, {n['blocked']} that can't work here"
          + ("" if info["database"] else f"  (no mods\\system\\cheats\\r4-{info['game']}.txt: only your own files)"))
    # the game's own item names in all five languages (for the save editor), read from the ROM
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import rom_text
        rom = os.path.join(root, "game", "data", "dqix.nds")
        langdir = os.path.join(root, "mods", "system", "lang")
        stamp = os.path.join(langdir, "rom-itemname-de.tsv")
        if os.path.isfile(rom) and (not os.path.isfile(stamp) or os.path.getmtime(stamp) < os.path.getmtime(rom)):
            rom_text.write_tables(rom, langdir)
    except Exception as ex:
        print(f"   (game texts for the translations: {ex})")
    if "--report" in sys.argv:
        for e in entries:
            what = e["reason"] if e["kind"] == "blocked" else \
                " ".join(f"{n}:{a:08x}={w:08x}" for n, a, w in e["patch"]) if e["kind"] == "code" else f"{len(e['ops'])} lines"
            print(f"{e['kind']:8}{e['status']:9}{e['cat'][:16]:17}{('*' if e['group'] else ' ')}{e['name'][:58]:59}{what[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
