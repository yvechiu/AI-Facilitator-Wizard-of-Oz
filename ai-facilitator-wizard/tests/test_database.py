import csv
import io
import pytest
from src.database import Database
from src.session_service import SessionService
from src.logging_service import LoggingService
from src.export_service import export_csv


def test_persistence_isolation_csv_observations_backup(db, session, template, client, tmp_path):
    logger = LoggingService(db, client, True)
    logger.send("operation", session, template, "編輯後\n多行,內容", "123456789012345678")
    logger.observe(session, "Generating Ideas", "參與不平衡", False, "先觀察", "筆記")
    other = SessionService(db).create("另一組", "前測", "WOZ", "223456789012345678")
    reopened = Database(db.path)
    assert reopened.integrity_check()
    for table in ["sessions", "operations", "observations"]:
        payload = export_csv(reopened, table, session)
        assert payload.startswith(b"\xef\xbb\xbf")
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        assert len(rows) == 1 and rows[0]["session_id"] == session
        if table == "operations":
            assert rows[0]["actual_sent_message"] == "編輯後\n多行,內容"
            assert rows[0]["template_version"] == template["template_version"]
            assert rows[0]["timestamp_utc"].endswith("+00:00")
    assert len(list(csv.DictReader(io.StringIO(export_csv(db, "operations", other).decode("utf-8-sig"))))) == 0
    backup = reopened.backup(tmp_path / "backup.sqlite3")
    assert Database(backup).rows("SELECT * FROM operations")[0]["operation_id"] == "operation"


def test_observation_validation(db, session, client):
    with pytest.raises(ValueError):
        LoggingService(db, client).observe(session, "Generating Ideas", "停滯", False)


def test_session_lifecycle(db):
    service = SessionService(db)
    sid = service.create("名稱", "前測", "WOZ", "123456789012345678", session_id="S01")
    assert sid == "S01"
    with pytest.raises(ValueError):
        service.end(sid)
    service.start(sid)
    with pytest.raises(ValueError):
        service.start(sid)
    service.end(sid)
    assert service.get(sid)["end_time"].endswith("+00:00")


def test_channel_cannot_be_reused_even_after_session_ends(db, session):
    service = SessionService(db)
    service.end(session)
    with pytest.raises(ValueError, match="已綁定"):
        service.create("重複", "正式", "WOZ", "123456789012345678")
    assert len(service.list()) == 1


def test_concurrent_session_creation_claims_channel_once(db):
    from concurrent.futures import ThreadPoolExecutor
    def create(i):
        try:
            return SessionService(db).create(str(i), "正式", "WOZ", "123456789012345678")
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, range(4)))
    assert sum(s is not None for s in results) == 1
    assert len(SessionService(db).list()) == 1


def test_upgrade_preserves_legacy_shared_channels_and_records(db, session, template, client):
    import sqlite3
    LoggingService(db, client).send("legacy-operation", session, template, "原始紀錄", "123456789012345678")
    with db.connect() as conn:
        conn.execute("DROP TRIGGER sessions_unique_channel_insert")
        conn.execute("DROP TRIGGER sessions_unique_channel_update")
        conn.execute("INSERT INTO sessions SELECT 'legacy-second',session_name,study_phase,experimental_condition,discord_channel_id,start_time,end_time,notes FROM sessions WHERE session_id=?", (session,))
    upgraded = Database(db.path)
    assert len(SessionService(upgraded).list()) == 2
    assert upgraded.rows("SELECT * FROM operations")[0]["actual_sent_message"] == "原始紀錄"
    SessionService(upgraded).end(session)
    with pytest.raises(ValueError, match="已綁定"):
        SessionService(upgraded).create("新場次", "正式", "WOZ", "123456789012345678")
    with pytest.raises(sqlite3.IntegrityError):
        with upgraded.connect() as conn:
            conn.execute("INSERT INTO sessions SELECT 'bypass',session_name,study_phase,experimental_condition,discord_channel_id,start_time,end_time,notes FROM sessions LIMIT 1")
    assert upgraded.integrity_check()
