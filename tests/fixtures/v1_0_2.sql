-- Written by AppTrackr v1.0.2 code via tests/fixtures/make_v1_fixture.py. Do not edit.
BEGIN TRANSACTION;
CREATE TABLE apps (
    app_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    exe_name    TEXT    NOT NULL UNIQUE,
    display_name TEXT,
    icon_path   TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    category    TEXT
);
INSERT INTO "apps" VALUES(1,'code.exe','VS Code','C:\Programs\VS Code\Code.exe',1,'Development');
INSERT INTO "apps" VALUES(2,'chrome.exe','Google Chrome',NULL,0,'Work');
INSERT INTO "apps" VALUES(3,'discord.exe','Discord',NULL,0,NULL);
INSERT INTO "apps" VALUES(4,'steamwebhelper.exe','Steam',NULL,0,NULL);
INSERT INTO "apps" VALUES(5,'steam.exe','Steam',NULL,0,NULL);
CREATE TABLE daily_rollup (
    day         TEXT    NOT NULL,
    app_id      INTEGER NOT NULL REFERENCES apps(app_id),
    focused_ms  INTEGER NOT NULL DEFAULT 0,
    opens_count INTEGER NOT NULL DEFAULT 0,
    clicks_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, app_id)
);
INSERT INTO "daily_rollup" VALUES('2026-03-01',1,5700000,4,650);
INSERT INTO "daily_rollup" VALUES('2026-03-01',2,2400000,1,0);
INSERT INTO "daily_rollup" VALUES('2026-03-01',3,1500000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-01',4,720000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-01',5,1800000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-02',1,5700000,5,750);
INSERT INTO "daily_rollup" VALUES('2026-03-02',2,2400000,1,0);
INSERT INTO "daily_rollup" VALUES('2026-03-02',3,1500000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-02',4,720000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-02',5,1800000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-03',1,5700000,6,850);
INSERT INTO "daily_rollup" VALUES('2026-03-03',2,2400000,1,0);
INSERT INTO "daily_rollup" VALUES('2026-03-03',3,1500000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-03',4,720000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-03',5,1800000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-04',1,5700000,7,950);
INSERT INTO "daily_rollup" VALUES('2026-03-04',2,9600000,1,0);
INSERT INTO "daily_rollup" VALUES('2026-03-04',3,1500000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-04',4,720000,0,0);
INSERT INTO "daily_rollup" VALUES('2026-03-04',5,1800000,0,0);
CREATE TABLE focus_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    app_id      INTEGER NOT NULL REFERENCES apps(app_id),
    window_title_hash TEXT,
    event_type  TEXT
);
CREATE TABLE player_profile (
    profile_id  INTEGER PRIMARY KEY CHECK(profile_id = 1),
    xp          INTEGER NOT NULL DEFAULT 0,
    level       INTEGER NOT NULL DEFAULT 1,
    credits     INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_streak_day TEXT
);
INSERT INTO "player_profile" VALUES(1,110,2,0,4,'2026-03-04');
CREATE TABLE reward_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    app_id        INTEGER NOT NULL REFERENCES apps(app_id),
    rule_id       INTEGER NOT NULL REFERENCES reward_rules(rule_id),
    day           TEXT    NOT NULL,
    granted_json  TEXT    NOT NULL,
    claimed       INTEGER NOT NULL DEFAULT 0
);
INSERT INTO "reward_events" VALUES(1,1.79124211643379116e+09,1,1,'2026-03-01','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(2,1.79124211643384933e+09,1,1,'2026-03-01','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(3,1.79124211643385934e+09,1,1,'2026-03-01','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(4,1.7912421164338746e+09,1,2,'2026-03-01','{"xp": 25, "stone": 10}',0);
INSERT INTO "reward_events" VALUES(5,1.79124211643393254e+09,1,7,'2026-03-01','{"xp": 10, "stone": 5}',0);
INSERT INTO "reward_events" VALUES(6,1.79124211643457055e+09,1,1,'2026-03-02','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(7,1.79124211643459224e+09,1,1,'2026-03-02','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(8,1.79124211643459868e+09,1,1,'2026-03-02','{"xp": 10, "wood": 5}',0);
INSERT INTO "reward_events" VALUES(9,1.79124211643461632e+09,1,2,'2026-03-02','{"xp": 25, "stone": 10}',0);
INSERT INTO "reward_events" VALUES(10,1.79124211643517875e+09,1,1,'2026-03-03','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(11,1.79124211643519926e+09,1,1,'2026-03-03','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(12,1.79124211643521356e+09,1,1,'2026-03-03','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(13,1.79124211643526506e+09,1,2,'2026-03-03','{"xp": 25, "stone": 10}',1);
INSERT INTO "reward_events" VALUES(14,1.79124211643574857e+09,1,1,'2026-03-04','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(15,1.79124211643576359e+09,1,1,'2026-03-04','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(16,1.79124211643576931e+09,1,1,'2026-03-04','{"xp": 10, "wood": 5}',1);
INSERT INTO "reward_events" VALUES(17,1.79124211643578171e+09,1,2,'2026-03-04','{"xp": 25, "stone": 10}',1);
CREATE TABLE reward_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id      INTEGER REFERENCES apps(app_id),
    metric      TEXT    NOT NULL CHECK(metric IN ('focused_ms','opens_count','clicks_count')),
    threshold   INTEGER NOT NULL,
    reward_json TEXT    NOT NULL,
    repeatable  INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1
);
INSERT INTO "reward_rules" VALUES(1,1,'focused_ms',1800000,'{"xp": 10, "wood": 5}',1,1);
INSERT INTO "reward_rules" VALUES(2,1,'focused_ms',3600000,'{"xp": 25, "stone": 10}',1,1);
INSERT INTO "reward_rules" VALUES(3,1,'focused_ms',7200000,'{"xp": 60, "blueprints": 1}',1,1);
INSERT INTO "reward_rules" VALUES(4,1,'focused_ms',18000000,'{"xp": 150, "metal": 20}',1,1);
INSERT INTO "reward_rules" VALUES(5,1,'opens_count',10,'{"xp": 5, "food": 5}',0,1);
INSERT INTO "reward_rules" VALUES(6,1,'opens_count',50,'{"xp": 20, "wood": 10}',0,1);
INSERT INTO "reward_rules" VALUES(7,1,'clicks_count',500,'{"xp": 10, "stone": 5}',0,1);
INSERT INTO "reward_rules" VALUES(8,1,'clicks_count',2000,'{"xp": 30, "metal": 10}',0,1);
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO "settings" VALUES('track_window_titles','0');
INSERT INTO "settings" VALUES('rewards_enabled','1');
INSERT INTO "settings" VALUES('polling_hz','4');
INSERT INTO "settings" VALUES('ui_theme','Purple');
INSERT INTO "settings" VALUES('idle_threshold_sec','600');
INSERT INTO "settings" VALUES('track_clicks','1');
INSERT INTO "settings" VALUES('autostart','1');
INSERT INTO "settings" VALUES('minimize_to_tray','0');
INSERT INTO "settings" VALUES('update_url','https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest');
INSERT INTO "settings" VALUES('last_update_check_day','2026-03-04');
CREATE TABLE usage_sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id      INTEGER NOT NULL REFERENCES apps(app_id),
    start_ts    REAL    NOT NULL,
    end_ts      REAL,
    duration_ms INTEGER,
    was_idle    INTEGER NOT NULL DEFAULT 0
);
INSERT INTO "usage_sessions" VALUES(1,1,1772366400.0,1772372100.0,5700000,0);
INSERT INTO "usage_sessions" VALUES(2,2,1772372400.0,1772374800.0,2400000,0);
INSERT INTO "usage_sessions" VALUES(3,3,1772375400.0,1772376900.0,1500000,0);
INSERT INTO "usage_sessions" VALUES(4,1,1772377400.0,1772380400.0,3000000,1);
INSERT INTO "usage_sessions" VALUES(5,4,1772381400.0,1772382120.0,720000,0);
INSERT INTO "usage_sessions" VALUES(6,5,1772382400.0,1772384200.0,1800000,0);
INSERT INTO "usage_sessions" VALUES(7,1,1772452800.0,1772458500.0,5700000,0);
INSERT INTO "usage_sessions" VALUES(8,2,1772458800.0,1772461200.0,2400000,0);
INSERT INTO "usage_sessions" VALUES(9,3,1772461800.0,1772463300.0,1500000,0);
INSERT INTO "usage_sessions" VALUES(10,1,1772463800.0,1772466800.0,3000000,1);
INSERT INTO "usage_sessions" VALUES(11,4,1772467800.0,1772468520.0,720000,0);
INSERT INTO "usage_sessions" VALUES(12,5,1772468800.0,1772470600.0,1800000,0);
INSERT INTO "usage_sessions" VALUES(13,1,1772539200.0,1772544900.0,5700000,0);
INSERT INTO "usage_sessions" VALUES(14,2,1772545200.0,1772547600.0,2400000,0);
INSERT INTO "usage_sessions" VALUES(15,3,1772548200.0,1772549700.0,1500000,0);
INSERT INTO "usage_sessions" VALUES(16,1,1772550200.0,1772553200.0,3000000,1);
INSERT INTO "usage_sessions" VALUES(17,4,1772554200.0,1772554920.0,720000,0);
INSERT INTO "usage_sessions" VALUES(18,5,1772555200.0,1772557000.0,1800000,0);
INSERT INTO "usage_sessions" VALUES(19,1,1772625600.0,1772631300.0,5700000,0);
INSERT INTO "usage_sessions" VALUES(20,2,1772631600.0,1772634000.0,2400000,0);
INSERT INTO "usage_sessions" VALUES(21,3,1772634600.0,1772636100.0,1500000,0);
INSERT INTO "usage_sessions" VALUES(22,1,1772636600.0,1772639600.0,3000000,1);
INSERT INTO "usage_sessions" VALUES(23,4,1772640600.0,1772641320.0,720000,0);
INSERT INTO "usage_sessions" VALUES(24,5,1772641600.0,1772643400.0,1800000,0);
INSERT INTO "usage_sessions" VALUES(25,2,1772666600.0,1772673800.0,7200000,0);
INSERT INTO "usage_sessions" VALUES(26,3,1772675600.0,NULL,NULL,0);
CREATE TABLE village_state (
    profile_id INTEGER PRIMARY KEY CHECK(profile_id = 1) REFERENCES player_profile(profile_id),
    state_json TEXT NOT NULL DEFAULT '{}'
);
INSERT INTO "village_state" VALUES(1,'{"buildings": {"workshop": {"level": 1}}, "villagers": 0, "inventory": {"wood": 50, "stone": 20, "metal": 0, "food": 0, "blueprints": 0}}');
CREATE INDEX idx_sessions_app   ON usage_sessions(app_id);
CREATE INDEX idx_sessions_start ON usage_sessions(start_ts);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('apps',5);
INSERT INTO "sqlite_sequence" VALUES('usage_sessions',26);
INSERT INTO "sqlite_sequence" VALUES('reward_rules',8);
INSERT INTO "sqlite_sequence" VALUES('reward_events',17);
COMMIT;
