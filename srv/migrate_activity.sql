-- Y21-R "Tianjiang Lingyu" (rain) migration.
-- Idempotent: safe to run any number of times.
-- Apply with:  sqlite3 /opt/yl/server/yl.db < srv/migrate_activity.sql
--
-- NOTE: the server also creates this table at boot (CREATE TABLE IF NOT EXISTS in
-- srv/index.ts), so running this file is optional. It exists for DB-only deployments
-- and for pre-creating the table before the new server binary starts.

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
);

CREATE INDEX IF NOT EXISTS idx_rain_state_date ON activity_rain_state(date);

-- ---------------------------------------------------------------------------
-- ENABLING / DISABLING (informational -- no statement below is executed here)
--
-- "Tianjiang Lingyu" is OFF by default because no `stones2_live` row exists in
-- the `events` table. rainSettleTick() early-returns when it finds no active
-- row of that type. This is a per-activity switch and is the intended on/off
-- mechanism; it does NOT touch activity_config.engine_on.
--
-- To ENABLE, use the GM API (the config call also hot-reloads the server's
-- in-memory kill-switch mirror; a direct DB write would not):
--   POST /api/gm/activity/config  {"engineOn":1}
--   POST /api/gm/activity         {"type":"stones2_live","name":"\u5929\u964d\u7075\u96e8",
--                                  "multiplier":2,"startAt":<ms>,"endAt":<ms>,"enabled":1}
--
-- To DISABLE, either set the event row's enabled=0 / move end_at into the past
-- via the same GM endpoint, or flip the GLOBAL kill switch with
-- POST /api/gm/activity/config {"engineOn":0} (that also stops exp2/stones2/
-- boss/drop, so prefer the per-event route when only this activity is meant).
--
-- activity_config.engine_on is deliberately NOT modified by this migration: it
-- is the global kill switch for the whole activity engine, and changing it here
-- would silently disable the pre-existing activities.
-- ---------------------------------------------------------------------------

-- Rollback: drops all rain settlement state; the activity then restarts from a
-- clean baseline. Safe to run; no other feature reads this table.
-- DROP TABLE IF EXISTS activity_rain_state;
