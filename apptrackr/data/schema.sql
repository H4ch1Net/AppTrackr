-- AppTrackr database schema (latest). Older databases are upgraded by the
-- migrations in db.py, so only add statements here that are safe to run
-- against a v1.0 database.

CREATE TABLE IF NOT EXISTS apps (
    app_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    exe_name       TEXT    NOT NULL UNIQUE,
    display_name   TEXT,
    icon_path      TEXT,
    is_favorite    INTEGER NOT NULL DEFAULT 0,
    category       TEXT,
    is_hidden      INTEGER NOT NULL DEFAULT 0,
    daily_limit_ms INTEGER
);

CREATE TABLE IF NOT EXISTS usage_sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id      INTEGER NOT NULL REFERENCES apps(app_id),
    start_ts    REAL    NOT NULL,
    end_ts      REAL,
    duration_ms INTEGER,
    was_idle    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_app   ON usage_sessions(app_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON usage_sessions(start_ts);

CREATE TABLE IF NOT EXISTS daily_rollup (
    day          TEXT    NOT NULL,
    app_id       INTEGER NOT NULL REFERENCES apps(app_id),
    focused_ms   INTEGER NOT NULL DEFAULT 0,
    opens_count  INTEGER NOT NULL DEFAULT 0,
    clicks_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, app_id)
);
CREATE INDEX IF NOT EXISTS idx_rollup_app ON daily_rollup(app_id, day);

-- Kept for compatibility with v1.0 databases; no longer written.
CREATE TABLE IF NOT EXISTS focus_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    app_id      INTEGER NOT NULL REFERENCES apps(app_id),
    window_title_hash TEXT,
    event_type  TEXT
);

-- Rewards
CREATE TABLE IF NOT EXISTS reward_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id      INTEGER REFERENCES apps(app_id),
    metric      TEXT    NOT NULL CHECK(metric IN ('focused_ms','opens_count','clicks_count')),
    threshold   INTEGER NOT NULL,
    reward_json TEXT    NOT NULL,
    repeatable  INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reward_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    app_id        INTEGER NOT NULL REFERENCES apps(app_id),
    rule_id       INTEGER NOT NULL REFERENCES reward_rules(rule_id),
    day           TEXT    NOT NULL,
    granted_json  TEXT    NOT NULL,
    claimed       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS player_profile (
    profile_id  INTEGER PRIMARY KEY CHECK(profile_id = 1),
    xp          INTEGER NOT NULL DEFAULT 0,
    level       INTEGER NOT NULL DEFAULT 1,
    credits     INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_streak_day TEXT
);

CREATE TABLE IF NOT EXISTS village_state (
    profile_id INTEGER PRIMARY KEY CHECK(profile_id = 1) REFERENCES player_profile(profile_id),
    state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO player_profile (profile_id) VALUES (1);
INSERT OR IGNORE INTO village_state  (profile_id, state_json)
    VALUES (1, '{"buildings":{},"villagers":0,"inventory":{"wood":0,"stone":0,"metal":0,"food":0,"blueprints":0}}');
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('idle_threshold_sec', '300'),
    ('track_clicks', '0'),
    ('minimize_to_tray', '1'),
    ('rewards_enabled', '1'),
    ('notifications_enabled', '1'),
    ('auto_update_check', '1'),
    ('polling_hz', '4');
