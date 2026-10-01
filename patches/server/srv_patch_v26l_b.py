# -*- coding: utf-8 -*-
r"""yl v26l_b server patch (reproducible, idempotent, assertion-gated)

SRC  srv/index_v26l.ts   (baseline, never modified)
DST  srv/index_v26l_b.ts (product)

Round 1 (Part 6) -- offline curve co-source + per-category quota scaling
  G1  calcOfflineGainV2(): 250 * 1.5^idx  ->  (idx <= 0 ? 4/3 : 2*idx+1) * 125
  G2a settleSaveEconV2(): declare ylScale right before capStone
  G2b settleSaveEconV2(): item (3) category terms *= ylScale

Round 2 (Part 7) -- make item (2) the non-binding floor and add a
counter-independent lump allowance, so capStone >= 1_200_000 * ylScale:
  G2c raise E2_STONE_BURST_BASE 100000 -> 1_200_000 and add
      E2_LUMP_STONE_ALLOWANCE = 1_200_000
  G2d item (2) total-burst cap *= ylScale, wrapped in Math.floor so that
      capStone stays an integer (ylScale = 13/3 is fractional at idx=6;
      capStone is written straight back as np[f] = ov + cap)

ylScale = (realmIdx <= 0 ? 4/3 : 2*realmIdx + 1) / 3
  realmIdx=1 (筑基期) -> 1.0   (unchanged)
  realmIdx=6 (长生境) -> 13/3 ~= 4.3333

Discipline:
  * every anchored replacement asserts hit count == 1 before writing
  * round-trip proof: reverse-apply all edits, assert byte-identical to source
  * idempotent: always re-reads the baseline, never accumulates in place

Usage:
  python srv_patch_v26l_b.py            # assert + apply + verify + write
  python srv_patch_v26l_b.py --count    # assert only, print hit counts
"""
import hashlib
import io
import sys

SRC = "srv/index_v26l.ts"
DST = "srv/index_v26l_b.ts"

# ------------------------------------------------------------------ G1 ------
G1_OLD = ("    out.stones = Math.floor(Math.floor(250 * Math.pow(1.5, idx)) * hours);"
          " // YL_ECON_X5_V26K \u539f 50 \u00d75")
G1_NEW = ("    out.stones = Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125)"
          " * hours); // YL_REALM_REWARD_SCALE_V26L")

# ----------------------------------------------------------------- G2a ------
G2A_OLD = "    const capStone = Math.min(ECON_CLAMP_ABS_MAX,"
G2A_NEW = ("    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3;"
           " // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)\n"
           "    const capStone = Math.min(ECON_CLAMP_ABS_MAX,")

# ------------------------------------------------------- G2b (+G2d 3rd) -----
G2B_OLD = ("      Math.floor(off.stones + dMed * ((realmIdx * 2 + 4) * 5) + dAdv * E2_ADV_STONE_EACH\n"
           "        + dKill * E2_KILL_STONE_EACH + dSR * E2_SR_STONE_EACH + sellAllow + 10000));")
G2B_NEW = ("      Math.floor(off.stones + dMed * ((realmIdx * 2 + 4) * 5) * ylScale"
           " + dAdv * E2_ADV_STONE_EACH * ylScale\n"
           "        + dKill * E2_KILL_STONE_EACH * ylScale + dSR * E2_SR_STONE_EACH * ylScale"
           " + sellAllow * ylScale\n"
           "        + E2_LUMP_STONE_ALLOWANCE * ylScale + 10000));")

# ----------------------------------------------------------------- G2c ------
G2C_OLD = "const E2_STONE_BURST_BASE = 100000; // YL_ECON_X5_V26K \u539f 20000 \u00d75"
G2C_NEW = ("const E2_STONE_BURST_BASE = 1_200_000;"
           " // YL_REALM_REWARD_SCALE_V26L \u539f 100_000\n"
           "const E2_LUMP_STONE_ALLOWANCE = 1_200_000; // YL_REALM_REWARD_SCALE_V26L")

# ----------------------------------------------------------------- G2d ------
G2D_OLD = ("      Math.floor(E2_STONE_BURST_PER_HOUR * mult * (mins / 60))"
           " + E2_STONE_BURST_BASE,")
G2D_NEW = ("      Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (mins / 60))"
           " + E2_STONE_BURST_BASE) * ylScale),")

# (name, old, new, expected_hits)
EDITS = [
    ("G1  offline curve co-source",        G1_OLD,  G1_NEW,  1),
    ("G2a declare ylScale",                G2A_OLD, G2A_NEW, 1),
    ("G2b+G2d item(3) scale + lump",       G2B_OLD, G2B_NEW, 1),
    ("G2c burst base raise + lump const",  G2C_OLD, G2C_NEW, 1),
    ("G2d item(2) total-burst *= ylScale", G2D_OLD, G2D_NEW, 1),
]

# constants that must stay byte-identical (pre AND post)
FROZEN = [
    "const E2_STONE_BURST_PER_HOUR = 1250000;",
    "const E2_ADV_STONE_EACH = 1000;",
    "const E2_KILL_STONE_EACH = 500;",
    "const E2_SR_STONE_EACH = 3000;",
    "const E2_SELL_UNIT = 250;",
    "const E2_SELL_PER_HOUR = 1000000;",
    "const ECON_CLAMP_ABS_MAX = 5_000_000_000;",
    "const ECON_CLAMP_EXP_PER_MIN = 2_000_000;",
    "const E2_INV_QTY_MAX = 1000000;",
    "const E2_MIN_SAVE_MINS = 0.5;",
]

# fragments that only exist AFTER the patch
POST_ONLY = [
    "off.stones + dMed * ((realmIdx * 2 + 4) * 5) * ylScale",
    "+ E2_LUMP_STONE_ALLOWANCE * ylScale + 10000));",
    "+ E2_STONE_BURST_BASE) * ylScale),",
    "const E2_LUMP_STONE_ALLOWANCE = 1_200_000;",
]

NEW_TOKENS = [
    ("G1 new curve present", G1_NEW, 1),
    ("G2a ylScale declared once",
     "const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3;", 1),
    ("G2b/G2d item(3) new body", G2B_NEW, 1),
    ("G2c new base const", G2C_NEW, 1),
    ("G2d item(2) new body", G2D_NEW, 1),
    ("old G1 curve gone", G1_OLD, 0),
    ("old G2b body gone", G2B_OLD, 0),
    ("old base const gone", G2C_OLD, 0),
    ("old item(2) body gone", G2D_OLD, 0),
]


def main():
    s = io.open(SRC, encoding="utf-8").read()
    src_md5 = hashlib.md5(s.encode("utf-8")).hexdigest()
    print("[src] %s" % SRC)
    print("      chars=%d  bytes=%d  md5=%s"
          % (len(s), len(s.encode("utf-8")), src_md5))

    # guard: the new identifiers must not pre-exist
    for ident in ("ylScale", "E2_LUMP_STONE_ALLOWANCE"):
        if s.count(ident) != 0:
            sys.exit("[FAIL] identifier '%s' already present (%d) -- rename required"
                     % (ident, s.count(ident)))
    print("[ok ] new identifiers absent in source: ylScale=0, E2_LUMP_STONE_ALLOWANCE=0")

    bad = []
    for name, old, new, want in EDITS:
        got = s.count(old)
        ok = (got == want)
        print("  [%s] %-36s hits=%d (want %d)" % ("ok  " if ok else "FAIL", name, got, want))
        if not ok:
            bad.append(name)
    for frag in FROZEN:
        if s.count(frag) != 1:
            print("  [FAIL] frozen fragment hits=%d (want 1): %r" % (s.count(frag), frag[:60]))
            bad.append("frozen:" + frag[:30])

    if bad:
        sys.exit("\n[FAIL] assertions failed, nothing written: %s" % ", ".join(bad))
    if "--count" in sys.argv:
        print("\n[count-only] all assertions passed, file not written")
        return

    out = s
    for name, old, new, want in EDITS:
        out = out.replace(old, new, want)
        print("  [ok ] applied %-36s x%d" % (name, want))

    nb = 0
    for label, frag, want in NEW_TOKENS:
        got = out.count(frag)
        ok = (got == want)
        if not ok:
            nb += 1
        print("  [%s] post %-36s hits=%d (want %d)"
              % ("ok  " if ok else "FAIL", label, got, want))
    for frag in FROZEN:
        if out.count(frag) != 1:
            print("  [FAIL] post frozen changed: %r" % frag[:60])
            nb += 1
    for frag in POST_ONLY:
        if out.count(frag) != 1:
            print("  [FAIL] post fragment missing: %r" % frag[:60])
            nb += 1
    if nb:
        sys.exit("[FAIL] post-checks failed %d, nothing written" % nb)

    # round-trip proof
    back = out
    for name, old, new, want in reversed(EDITS):
        back = back.replace(new, old, want)
    rt_ok = (back == s)
    print("  [%s] round-trip == source: %s" % ("ok  " if rt_ok else "FAIL", rt_ok))
    if not rt_ok:
        sys.exit("[FAIL] round-trip not equivalent, nothing written")

    io.open(DST, "w", encoding="utf-8", newline="").write(out)
    print("\n[dst] %s" % DST)
    print("      chars=%d  bytes=%d  md5=%s"
          % (len(out), len(out.encode("utf-8")),
             hashlib.md5(out.encode("utf-8")).hexdigest()))
    print("      delta chars %+d" % (len(out) - len(s)))


main()
