import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            -- Remove the previous one-channel-per-session restriction, including existing databases.
            DROP TRIGGER IF EXISTS sessions_unique_channel_insert;
            DROP TRIGGER IF EXISTS sessions_unique_channel_update;
            CREATE TABLE IF NOT EXISTS message_library (
              message_id TEXT PRIMARY KEY, payload TEXT, deleted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS phase_experiments (
              experiment_id TEXT NOT NULL UNIQUE, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL,
              demo_mode INTEGER NOT NULL, phase_id TEXT, phase_name TEXT, sequence INTEGER NOT NULL DEFAULT 0,
              effective_at TEXT, checked_at TEXT, PRIMARY KEY(guild_id,channel_id,demo_mode)
            );
            CREATE TABLE IF NOT EXISTS phase_events (
              event_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES phase_experiments(experiment_id),
              guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, demo_mode INTEGER NOT NULL,
              phase_id TEXT NOT NULL, phase_name TEXT NOT NULL, sequence INTEGER NOT NULL,
              payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              effective_at TEXT, error_message TEXT, attempts INTEGER NOT NULL DEFAULT 0,
              UNIQUE(experiment_id,sequence)
            );
            CREATE TABLE IF NOT EXISTS channel_operations (
              operation_id TEXT PRIMARY KEY, timestamp_utc TEXT NOT NULL,
              guild_id TEXT NOT NULL, channel_name TEXT NOT NULL, demo_mode INTEGER NOT NULL,
              channel_id TEXT, status TEXT NOT NULL, error TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY, session_name TEXT NOT NULL,
              study_phase TEXT NOT NULL, experimental_condition TEXT NOT NULL,
              discord_channel_id TEXT NOT NULL, start_time TEXT, end_time TEXT, notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
              operation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
              timestamp_utc TEXT NOT NULL, message_id TEXT NOT NULL, template_version TEXT NOT NULL,
              cps_stage TEXT NOT NULL, cps_substage TEXT NOT NULL, intervention_type TEXT NOT NULL,
              original_message TEXT NOT NULL, actual_sent_message TEXT NOT NULL,
              was_edited INTEGER NOT NULL, discord_channel_id TEXT NOT NULL, discord_message_id TEXT,
              send_status TEXT NOT NULL CHECK(send_status IN ('PENDING','SUCCESS','FAILED','UNKNOWN','DEMO')),
              error_message TEXT, wizard_notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
              observation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
              timestamp_utc TEXT NOT NULL, cps_stage TEXT NOT NULL, interaction_problem TEXT NOT NULL,
              intervened INTEGER NOT NULL, nonintervention_reason TEXT NOT NULL, notes TEXT NOT NULL
            );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql, params=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params)]

    def integrity_check(self):
        with self.connect() as db:
            checks = [r[0] for r in db.execute("PRAGMA integrity_check")]
            foreign = list(db.execute("PRAGMA foreign_key_check"))
            return checks == ["ok"] and not foreign

    def backup(self, destination):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError("備份不得覆蓋來源資料庫")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination
