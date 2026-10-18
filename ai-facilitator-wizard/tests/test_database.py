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
    other = SessionService(db).create("另一組", "前測", "WOZ", "123456789012345678")
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


def test_channel_workflow_preserves_legacy_and_exports_by_channel(db, session, template, client):
    from src.export_service import channel_records, export_channel_csv
    channel = "123456789012345678"
    other = "223456789012345678"
    logger = LoggingService(db, client, True)
    logger.send("legacy", session, template, "舊場次內容", channel)
    logger.observe(session, "Generating Ideas", "舊觀察", False, "等待")
    SessionService(db).end(session)
    logger.send_to_channel("new", channel, template, "新內容")
    logger.observe_channel(channel, "Generating Ideas", "新觀察", False, "等待")
    logger.send_to_channel("other", other, template, "另一組內容")
    for table in ["operations", "observations"]:
        rows = channel_records(db, table, channel)
        assert len(rows) == 2
        assert all(r["discord_channel_id"] == channel for r in rows)
        payload = export_channel_csv(db, table, channel)
        assert payload.startswith(b"\xef\xbb\xbf")
        exported = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        assert len(exported) == 2 and all(r["discord_channel_id"] == channel for r in exported)
        empty = export_channel_csv(db, table, "999999999999999999")
        assert len(list(csv.DictReader(io.StringIO(empty.decode("utf-8-sig"))))) == 0
    assert SessionService(db).get(session)["end_time"] is not None
    assert Database(db.path).integrity_check()
    assert len(db.rows("SELECT * FROM sessions")) == 3


def test_automatic_channel_link_reused_and_demo_is_separate(db, template, client):
    from src.discord_client import SendResult
    demo = LoggingService(db, client, True)
    demo.send_to_channel("one", "123456789012345678", template, "第一則")
    demo.send_to_channel("two", "123456789012345678", template, "第二則")
    client.send.assert_not_called()
    client.send.return_value = SendResult("SUCCESS", "987654321098765432")
    live = LoggingService(db, client, False)
    live.send_to_channel("three", "123456789012345678", template, "正式")
    live.send_to_channel("three", "123456789012345678", template, "正式")
    client.send.assert_called_once()
    rows = db.rows("SELECT * FROM operations ORDER BY timestamp_utc")
    assert rows[0]["session_id"] == rows[1]["session_id"]
    assert rows[2]["session_id"] != rows[0]["session_id"]
    assert len(db.rows("SELECT * FROM sessions")) == 2
