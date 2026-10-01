# -*- coding: utf-8 -*-
"""
srv_patch_activity.py -- Y21-R "Tianjiang Lingyu" (rain) server patch generator.

Reads : srv/index.ts        (pristine baseline; NEVER modified)
Writes: srv/index_activity.ts  (patched product)

Idempotent by construction: the source is read-only, so re-running always
regenerates a byte-identical product.

Engineering guarantees enforced here (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY once in the source;
  2. round-trip equivalence: replacing each new fragment back with its old
     fragment yields the source byte-for-byte;
  3. every newly introduced identifier occurs 0 times in the source;
  4. every INJECTED fragment (the added text) is pure ASCII
     (all non-ASCII in injected string literals is emitted as \\uXXXX);
  5. the source is not already patched.

Run (paths are relative to the current working directory, i.e. the repo root):
  python srv_patch_activity.py
  python srv_patch_activity.py --src srv/index.ts     --out srv/index_activity.ts
  python srv_patch_activity.py --src srv/index_v27.ts --out srv/index_v27a.ts

--src / --out are optional; with no arguments the historical defaults
(srv/index.ts -> srv/index_activity.ts) are used, so existing callers are
unaffected. Both paths are resolved against the process CWD on purpose.
"""
import argparse
import io
import os
import sys
import hashlib

DEFAULT_SRC = os.path.join("srv", "index.ts")
DEFAULT_OUT = os.path.join("srv", "index_activity.ts")


def esc(s: str) -> str:
    """Escape every non-ASCII code point as \\uXXXX so injected text is pure ASCII."""
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append("\\u%04x" % ord(ch))
    return "".join(out)


# ---------------------------------------------------------------------------
# Fragments (authored with real Chinese; esc() converts them to \\uXXXX).
# Comments are written in ASCII English on purpose, so only the string
# literals that must contain Chinese get escaped.
# ---------------------------------------------------------------------------

# --- A: settlement state table -------------------------------------------
A_OLD = "  db.run(`CREATE INDEX IF NOT EXISTS idx_events_window ON events(enabled, start_at, end_at)`);"

A_ADD = """
  // Y21-R "Tianjiang Lingyu" (rain) settlement state: one row per (player, event, Beijing date).
  // PRIMARY KEY is the single guard against settling the same window twice. All state lives in
  // columns, never in saves.save_data JSON (the client uploads that JSON authoritatively).
  // last_minutes = last observed stats_daily.minutes; accrued_minutes = remainder below 1h;
  // settled_minutes = minutes already paid today (daily cap 480 = 8h).
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_rain_state (
      player_id INTEGER NOT NULL,
      event_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      last_minutes INTEGER NOT NULL DEFAULT 0,
      accrued_minutes INTEGER NOT NULL DEFAULT 0,
      settled_minutes INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, event_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_rain_state_date ON activity_rain_state(date)`);"""

# --- B1: widen the ACT_TYPES target union with 'live' ---------------------
B1_OLD = "const ACT_TYPES: Record<string, { name: string; target: 'exp' | 'stones' | 'boss' | 'drop'; desc: string }> = {"
B1_NEW = "const ACT_TYPES: Record<string, { name: string; target: 'exp' | 'stones' | 'boss' | 'drop' | 'live'; desc: string }> = {"

# --- B2: register the new activity type (display/window carrier only) -----
B2_OLD = "  drop:    { name: '\u9650\u65f6\u6389\u843d', target: 'drop',   desc: '\u91ce\u5916\u6389\u843d\u7387\u63d0\u5347\uff08\u5ba2\u6237\u7aef\u63a5\u7ba1\u524d\u4ec5\u5c55\u793a\uff09' },"

B2_ADD = """
  // "Tianjiang Lingyu": target 'live' matches no actMultiplierFor() query target ('exp'/'stones'),
  // so this type NEVER multiplies exp/stones income; it only carries the window and is shown in the
  // existing read-only events panel. Payout is done by the [raincore] settler, not by the multiplier engine.
  stones2_live: { name: '\u5929\u964d\u7075\u96e8', target: 'live', desc: '\u5728\u7ebf\u4fee\u884c\uff1a\u6bcf\u6ee1 1 \u5c0f\u65f6\u7ed3\u7b97\u4e00\u5c01\u7075\u77f3\u90ae\u4ef6\uff08\u6309\u5883\u754c\u6298\u7b97\uff09' },"""

# --- C: pure logic core ---------------------------------------------------
C_OLD = "// [/actcore]"

C_ADD = """

// [raincore] Y21-R "Tianjiang Lingyu" pure logic core (no external refs; extractable for unit tests).
// Reward anchor, derived from the client meditation loop (measured, not a literal in the bundle):
//   stones per meditate = max(1, max(1, 2*idx+1) + randInt(0..2) - 1) * 5
//   effective rate      = 0.982 meditates/sec (setCooldown(1) + per-second -1 cooldown, 40s steady state)
//   stones/sec          = 4.91 * rainRealmFactor(idx)
//   stones/hour         = 17676 * rainRealmFactor(idx)
//   rainRealmFactor(i)  = 4/3 (i <= 0) | 2*i + 1 (i >= 1)
// Cross-check: idx 0 -> 23568, idx 1 -> 53028, idx 6 -> 229788 stones/hour.
const RAIN_HOURLY_STONES_BASE = 17676;        // = round(0.982 * 5 * 3600) = 4.91 stones/sec * 3600
const RAIN_SETTLE_MIN_MINUTES = 60;           // pay only in whole hours
const RAIN_DAILY_CAP_MINUTES = 480;           // per-day settled cap = 8h
const RAIN_ONLINE_STALE_MS = 15 * 60 * 1000;  // presence window over server-timestamped saves.updated_at
const RAIN_TICK_MS = 10 * 60 * 1000;          // settlement period
let rainEngineOn = false;   // in-memory mirror of the GLOBAL kill switch (activity_config.engine_on)
let rainSettling = false;   // re-entrancy guard: skip a tick if the previous one is still running
let rainLastTickMs = 0;     // server wall-clock of the previous tick (the hard per-tick ceiling)
// Realm factor (pure): i <= 0 -> 4/3, else 2i+1; NaN/negative clamped to 0.
function rainRealmFactor(idx: unknown): number {
  const i = Math.max(0, Math.floor(Number(idx) || 0));
  return i <= 0 ? 4 / 3 : 2 * i + 1;
}
// Hourly stones for a realm index (pure).
function rainHourlyStones(idx: unknown): number {
  return Math.floor(RAIN_HOURLY_STONES_BASE * rainRealmFactor(idx));
}
// Minutes to credit this tick: the client-reported minutes delta, HARD-CAPPED by the server
// wall-clock interval. The wall clock is server-authoritative, so an inflated playTime can never
// earn more than the real elapsed time between two ticks.
function rainDeltaMinutes(prevMinutes: unknown, nowMinutes: unknown, wallMinutes: unknown): number {
  const p = Math.max(0, Math.floor(Number(prevMinutes) || 0));
  const n = Math.max(0, Math.floor(Number(nowMinutes) || 0));
  const raw = n > p ? n - p : 0;
  const cap = Math.max(1, Math.ceil(Math.max(0, Number(wallMinutes) || 0)));
  return Math.min(raw, cap);
}
// Whole hours payable now, bounded by the unpaid remainder and the per-day cap (pure).
function rainPayableHours(accruedMinutes: unknown, settledMinutes: unknown): number {
  const acc = Math.max(0, Math.floor(Number(accruedMinutes) || 0));
  const done = Math.max(0, Math.floor(Number(settledMinutes) || 0));
  const room = Math.max(0, RAIN_DAILY_CAP_MINUTES - done);
  return Math.floor(Math.min(acc, room) / RAIN_SETTLE_MIN_MINUTES);
}
// Stones for a whole number of hours at the given realm index (pure).
function rainBonusStones(hours: unknown, idx: unknown): number {
  const h = Math.max(0, Math.floor(Number(hours) || 0));
  return h * rainHourlyStones(idx);
}
// [/raincore]"""

# --- E1: keep the in-memory mirror in sync when GM flips the switch -------
# NOTE: the seed default of activity_config.engine_on is deliberately NOT touched.
# engine_on is the GLOBAL kill switch (exp2/stones2/boss/drop AND stones2_live), so flipping
# its default would silently disable the pre-existing activities. "Tianjiang Lingyu" is OFF by
# default through a narrower, more precise mechanism: no stones2_live row exists in `events`
# until a GM creates one, and rainSettleTick() early-returns when it finds no such row.
E1_OLD = "    res.json({ ok: true, engineOn: on === '1' });"
E1_NEW = (
    "    // GM global kill switch (activity_config.engine_on): mirror into memory so the timer\n"
    "    // needs no DB read while the engine is off. This is a hot-reload channel for the GM\n"
    "    // switch only; it is NOT what keeps Tianjiang Lingyu off by default.\n"
    "    rainEngineOn = on === '1';\n"
    "    res.json({ ok: true, engineOn: on === '1' });"
)

# --- E2: settler + the only new setInterval + boot mirror -----------------
E2_OLD = (
    "    console.error('gm activity config error:', e?.message || e);\n"
    "    res.status(500).json({ error: '\u4fdd\u5b58\u5931\u8d25' });\n"
    "  }\n"
    "});"
)

E2_ADD = """

// [raincore-settler] Y21-R rain settler: the only new setInterval in this file.
// When the engine is off the timer callback returns on its FIRST line, before any DB work.
// dbGet/dbAll/dbRun/insertMail/bjDate are hoisted function declarations, safe to call at runtime.
async function rainSettleTick(wallMinutes: number): Promise<void> {
  if (rainSettling) return;
  rainSettling = true;
  try {
    const nowMs = Date.now();
    const ev: any = await dbGet(
      "SELECT id FROM events WHERE type = 'stones2_live' AND enabled = 1 AND start_at <= ? AND end_at > ? LIMIT 1",
      [nowMs, nowMs]
    );
    if (!ev) return;
    const eventId = Math.max(0, Math.floor(Number(ev.id) || 0));
    if (!eventId) return;
    const today = bjDate(nowMs);
    const staleMod = '-' + Math.floor(RAIN_ONLINE_STALE_MS / 60000) + ' minutes';
    const rows: any[] = await dbAll(
      "SELECT s.user_id AS uid, r.realm_index AS ri, COALESCE(d.minutes, 0) AS minutes" +
      " FROM saves s" +
      " LEFT JOIN rankings r ON r.user_id = s.user_id" +
      " LEFT JOIN stats_daily d ON d.player_id = s.user_id AND d.date = ?" +
      " WHERE s.updated_at >= datetime('now', ?)",
      [today, staleMod]
    );
    for (const row of rows || []) {
      try {
        const uid = Math.max(0, Math.floor(Number(row.uid) || 0));
        if (!uid) continue;
        const nowMinutes = Math.max(0, Math.floor(Number(row.minutes) || 0));
        const st: any = await dbGet(
          'SELECT last_minutes, accrued_minutes, settled_minutes FROM activity_rain_state WHERE player_id = ? AND event_id = ? AND date = ?',
          [uid, eventId, today]
        );
        if (!st) {
          // First sight of this player/date: baseline only, never pay for the whole day at once.
          await dbRun(
            'INSERT OR IGNORE INTO activity_rain_state (player_id, event_id, date, last_minutes, accrued_minutes, settled_minutes) VALUES (?, ?, ?, ?, 0, 0)',
            [uid, eventId, today, nowMinutes]
          );
          continue;
        }
        const delta = rainDeltaMinutes(st.last_minutes, nowMinutes, wallMinutes);
        const accrued = Math.max(0, Math.floor(Number(st.accrued_minutes) || 0)) + delta;
        const settled = Math.max(0, Math.floor(Number(st.settled_minutes) || 0));
        const hours = rainPayableHours(accrued, settled);
        if (hours <= 0) {
          await dbRun(
            'UPDATE activity_rain_state SET last_minutes = ?, accrued_minutes = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND event_id = ? AND date = ?',
            [nowMinutes, accrued, uid, eventId, today]
          );
          continue;
        }
        const payMinutes = hours * RAIN_SETTLE_MIN_MINUTES;
        // Guarded single statement: atomically reserve this payout (concurrency/re-entry safe, daily cap enforced).
        const claim = await dbRun(
          'UPDATE activity_rain_state SET last_minutes = ?, accrued_minutes = accrued_minutes + ? - ?, settled_minutes = settled_minutes + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND event_id = ? AND date = ? AND settled_minutes + ? <= ?',
          [nowMinutes, delta, payMinutes, payMinutes, uid, eventId, today, payMinutes, RAIN_DAILY_CAP_MINUTES]
        );
        if (!claim.changes) continue;
        const bonus = rainBonusStones(hours, row.ri);
        const title = '\u5929\u964d\u7075\u96e8 \u00b7 \u5728\u7ebf\u4fee\u884c\u56de\u9988';
        const body = '\u7075\u96e8\u6da6\u6cfd\uff0c\u9053\u53cb\u5728\u7ebf\u4fee\u884c ' + hours + ' \u5c0f\u65f6\uff0c\u5929\u5730\u7075\u6c14\u5316\u4f5c\u7075\u77f3\u76f8\u8d60\uff1a\\n\\n\u00b7 \u7075\u77f3 +' + bonus + '\uff08\u8bf7\u70b9\u51fb\u4e0b\u65b9\u9886\u53d6\uff09\\n\\n\uff08\u6d3b\u52a8\u671f\u95f4\u5728\u7ebf\u6bcf\u6ee1 1 \u5c0f\u65f6\u7ed3\u7b97\u4e00\u6b21\uff0c\u5355\u65e5\u4e0a\u9650 8 \u5c0f\u65f6\uff09';
        try {
          await insertMail(uid, title, body, 'system', bonus);
        } catch (mailErr: any) {
          // Compensating rollback: mail failed, release the reservation so the player retries next tick.
          await dbRun(
            'UPDATE activity_rain_state SET accrued_minutes = accrued_minutes + ?, settled_minutes = settled_minutes - ? WHERE player_id = ? AND event_id = ? AND date = ?',
            [payMinutes, payMinutes, uid, eventId, today]
          ).catch(() => {});
          console.error('rain mail error:', mailErr?.message || mailErr);
        }
      } catch (perUserErr: any) {
        console.error('rain settle per-user error:', perUserErr?.message || perUserErr);
      }
    }
  } catch (e: any) {
    console.error('rain settle tick error:', e?.message || e);
  } finally {
    rainSettling = false;
  }
}
setInterval(() => {
  if (!rainEngineOn) return; // engine off: first-line early return, zero DB work
  const nowMs = Date.now();
  const wallMinutes = rainLastTickMs > 0 ? (nowMs - rainLastTickMs) / 60000 : RAIN_TICK_MS / 60000;
  rainLastTickMs = nowMs;
  rainSettleTick(wallMinutes).catch((e: any) => console.error('rain tick error:', e?.message || e));
}, RAIN_TICK_MS).unref();
// Boot: mirror engine_on into memory so the timer needs no DB read while the engine is off.
dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'")
  .then((r: any) => { rainEngineOn = String(r && r.value) === '1'; })
  .catch(() => {});"""

# ---------------------------------------------------------------------------
# Edit table: (label, old, new). The "injected" text is derived automatically:
#   * pure append  -> new[len(old):]            (old is re-emitted unchanged)
#   * pure prepend -> new[:len(new)-len(old)]
#   * in-place edit-> both old and new must be fully ASCII
# ---------------------------------------------------------------------------
EDITS = [
    ("A_state_table",   A_OLD,   A_OLD + esc(A_ADD)),
    ("B1_target_union", B1_OLD,  B1_NEW),
    ("B2_new_type",     B2_OLD,  B2_OLD + esc(B2_ADD)),
    ("C_raincore",      C_OLD,   C_OLD + esc(C_ADD)),
    ("E1_mirror_sync",  E1_OLD,  esc(E1_NEW)),
    ("E2_settler",      E2_OLD,  E2_OLD + esc(E2_ADD)),
]


def injected_text(label: str, old: str, new: str):
    """Return the text actually injected by this edit (None => in-place edit)."""
    if new.startswith(old):
        return new[len(old):]
    if new.endswith(old):
        return new[:len(new) - len(old)]
    return None

NEW_IDENTIFIERS = [
    "activity_rain_state", "idx_rain_state_date", "stones2_live",
    "rainEngineOn", "rainSettling", "rainLastTickMs", "rainRealmFactor",
    "rainHourlyStones", "rainDeltaMinutes", "rainPayableHours",
    "rainBonusStones", "rainSettleTick", "RAIN_HOURLY_STONES_BASE",
    "RAIN_SETTLE_MIN_MINUTES", "RAIN_DAILY_CAP_MINUTES",
    "RAIN_ONLINE_STALE_MS", "RAIN_TICK_MS", "raincore",
]


def fail(msg: str) -> None:
    sys.stderr.write("FAIL: " + msg + "\n")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the Y21-R 'Tianjiang Lingyu' (rain) server patch product."
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
    if "activity_rain_state" in src or "raincore" in src:
        fail("source already contains rain markers; refusing to double-patch")

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
            # in-place edit: no new text is injected, both sides must be ASCII anyway
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

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s" % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s" % (out_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d" % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            print("    ~ %-16s in-place ASCII edit" % label)
        else:
            print("    + %-16s injected chars=%d (ascii=%s)" % (label, len(added), added.isascii()))
    print("OK  all anchors unique, identifiers collision-free, round-trip byte-exact, injected text ASCII")


if __name__ == "__main__":
    main()
