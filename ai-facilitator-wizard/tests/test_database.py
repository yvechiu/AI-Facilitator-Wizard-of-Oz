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
