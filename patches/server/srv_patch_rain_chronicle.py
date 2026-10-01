# -*- coding: utf-8 -*-
"""
srv_patch_rain_chronicle.py -- v27b patch: stop the rain mails from spamming the
global chronicle ("江湖志").

Background
  insertMail() broadcasts a "【鸿函】" chronicle entry for every mail whose attached
  stones >= CHRONICLE_MAIL_STONES (1000). "Tianjiang Lingyu" pays an hourly mail of
  at least 17676 stones to every online player, so each player injected up to 8
  chronicle lines per day. The rain reward is routine and automatic, not a rare
  player-earned jackpot, so it must NOT broadcast -- while still keeping the stones
  as a claimable mail attachment (mailClaimCore credits attached_lingshi).

Fix (exactly 3 edits, nothing else)
  1. insertMail gains an optional 6th param: opts?: { noChronicle?: boolean }
  2. the chronicle guard short-circuits on opts?.noChronicle
  3. the rain settler call site passes { noChronicle: true }

All other ~30 insertMail call sites are untouched and therefore behave exactly as
before (no opts => noChronicle falsy => unchanged).

Reads : srv/index_v27a.ts        (pristine v27a baseline; NEVER modified)
Writes: srv/index_v27b.ts        (patched product)

Idempotent by construction: the source is read-only, so re-running always
regenerates a byte-identical product.

Engineering guarantees enforced here (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY once in the source;
  2. round-trip equivalence: replacing each new fragment back with its old
     fragment yields the source byte-for-byte;
  3. the newly introduced identifier `noChronicle` occurs 0 times in the source;
  4. every INJECTED fragment (the added text) is pure ASCII;
  5. the source is not already patched.

Run (paths are relative to the current working directory, i.e. the repo root):
  python srv_patch_rain_chronicle.py
  python srv_patch_rain_chronicle.py --src srv/index_v27a.ts --out srv/index_v27b.ts

--src / --out are optional; with no arguments the defaults above are used. Both
paths are resolved against the process CWD on purpose.
"""
import argparse
import io
import os
import sys
import hashlib

DEFAULT_SRC = os.path.join("srv", "index_v27a.ts")
DEFAULT_OUT = os.path.join("srv", "index_v27b.ts")

# ---------------------------------------------------------------------------
# Edit table: (label, old, new). Every old/new pair here is pure ASCII.
# ---------------------------------------------------------------------------

# --- 1: insertMail signature gains an optional opts bag --------------------
E1_OLD = "function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number): Promise<number> {"
E1_NEW = "function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number, opts?: { noChronicle?: boolean }): Promise<number> {"

# --- 2: chronicle guard short-circuits for opt-out senders -----------------
E2_OLD = "  if (lingshi >= CHRONICLE_MAIL_STONES) {"
E2_NEW = "  if (!opts?.noChronicle && lingshi >= CHRONICLE_MAIL_STONES) {"

# --- 3: the rain settler opts out -----------------------------------------
E3_OLD = "          await insertMail(uid, title, body, 'system', bonus);"
E3_NEW = "          await insertMail(uid, title, body, 'system', bonus, { noChronicle: true });"

EDITS = [
    ("signature_opts", E1_OLD, E1_NEW),
    ("guard_shortcircuit", E2_OLD, E2_NEW),
    ("rain_call_optout", E3_OLD, E3_NEW),
]

NEW_IDENTIFIERS = ["noChronicle"]

# The exact delta this patch is expected to introduce (chars == bytes, all ASCII).
EXPECTED_DELTA = 79

# After the patch this literal must be gone (it is the pre-patch guard).
MUST_BE_ABSENT = "  if (lingshi >= CHRONICLE_MAIL_STONES) {"


def injected_text(label: str, old: str, new: str):
    """Return the text actually injected by this edit (None => in-place edit)."""
    if new.startswith(old):
        return new[len(old):]
    if new.endswith(old):
        return new[:len(new) - len(old)]
    return None


def fail(msg: str) -> None:
    sys.stderr.write("FAIL: " + msg + "\n")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the v27b patch that stops rain mails from broadcasting to the chronicle."
    )
    ap.add_argument("--src", default=DEFAULT_SRC, help="pristine baseline (default: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="patched product (default: %(default)s)")
    args = ap.parse_args()
    src_path = args.src
    out_path = args.out

    if not os.path.isfile(src_path):
        fail("source not found: " + src_path)
    if os.path.abspath(src_path) == os.path.abspath(out_path):
        fail("--src and --out must differ (refusing to overwrite the baseline in place)")
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 5) source must not already be patched
    if "noChronicle" in src:
        fail("source already contains 'noChronicle'; refusing to double-patch")

    # 1) anchor uniqueness
    for label, old, _new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (expected exactly 1)" % (label, n))

    # 3) new identifiers must not pre-exist
    for ident in NEW_IDENTIFIERS:
        n = src.count(ident)
        if n != 0:
            fail("identifier %r already occurs %d times in source" % (ident, n))

    # 4) injected text must be pure ASCII
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            if not (old.isascii() and new.isascii()):
                fail("in-place edit %s touches non-ASCII bytes" % label)
            continue
        try:
            added.encode("ascii")
        except UnicodeEncodeError as e:
            fail("injected text for %s is not ASCII: %s" % (label, e))

    # apply
    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 2) round-trip equivalence (undo in reverse order)
    rt = out
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    # product assertions
    if out.count("noChronicle") != 3:
        fail("expected 'noChronicle' exactly 3 times in product, got %d" % out.count("noChronicle"))
    if MUST_BE_ABSENT in out:
        fail("pre-patch guard still present in product: " + MUST_BE_ABSENT)
    delta = len(out) - len(src)
    if delta != EXPECTED_DELTA:
        fail("unexpected delta: got +%d, expected +%d" % (delta, EXPECTED_DELTA))
    # the other ~30 call sites must be untouched
    if out.count("insertMail(") != src.count("insertMail("):
        fail("insertMail call-site count changed: %d -> %d" % (src.count("insertMail("), out.count("insertMail(")))

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s" % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s" % (out_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d" % (delta, len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            print("    ~ %-18s in-place ASCII edit (old=%d chars, new=%d chars)" % (label, len(old), len(new)))
        else:
            print("    + %-18s injected chars=%d (ascii=%s)" % (label, len(added), added.isascii()))
    print("OK  product: 'noChronicle' count = %d (expected 3)" % out.count("noChronicle"))
    print("OK  product: pre-patch guard absent = %s" % (MUST_BE_ABSENT not in out))
    print("OK  product: insertMail( occurrences = %d (unchanged)" % out.count("insertMail("))
    print("OK  all anchors unique, identifier collision-free, round-trip byte-exact, injected text ASCII")


if __name__ == "__main__":
    main()
