import uuid
import pytest
from src.logging_service import LoggingService
from src.discord_client import SendResult


def test_demo_never_calls_discord_and_keeps_edit(db, session, template, client):
    logger = LoggingService(db, client, True)
    result = logger.send(str(uuid.uuid4()), session, template, "手動修改的訊息", "123456789012345678")
    assert result["send_status"] == "DEMO"
    assert result["actual_sent_message"] == "手動修改的訊息"
    assert result["original_message"] == template["content"]
    assert result["was_edited"] == 1
    client.send.assert_not_called()


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "UNKNOWN"])
def test_real_result_and_dedup(db, session, template, client, status):
    client.send.return_value = SendResult(status, "123" if status == "SUCCESS" else None, None if status == "SUCCESS" else "安全錯誤")
    logger = LoggingService(db, client, False)
    opid = str(uuid.uuid4())
    first = logger.send(opid, session, template, template["content"], "123456789012345678")
    second = logger.send(opid, session, template, template["content"], "123456789012345678")
    assert first == second
    assert first["send_status"] == status
    assert first["discord_message_id"] == ("123" if status == "SUCCESS" else None)
    assert first["error_message"] == (None if status == "SUCCESS" else "安全錯誤")
    client.send.assert_called_once()


def test_pending_committed_before_network(db, session, template, client):
    opid = str(uuid.uuid4())
    def send(*args):
        assert db.rows("SELECT send_status FROM operations WHERE operation_id=?", (opid,))[0]["send_status"] == "PENDING"
        return SendResult("SUCCESS", "123")
    client.send.side_effect = send
    assert LoggingService(db, client, False).send(opid, session, template, template["content"], "123456789012345678")["send_status"] == "SUCCESS"


def test_database_failure_blocks_network(db, session, template, client, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def broken():
        raise OSError("disk unavailable")
        yield
    monkeypatch.setattr(db, "connect", broken)
    with pytest.raises(OSError):
        LoggingService(db, client, False).send("op", session, template, "測試", "123456789012345678")
    client.send.assert_not_called()


def test_pending_after_crash_never_retried(db, session, template, client):
    class Crash(BaseException):
        pass
    client.send.side_effect = Crash()
    logger = LoggingService(db, client, False)
    with pytest.raises(Crash):
        logger.send("crash", session, template, "訊息", "123456789012345678")
    assert logger.send("crash", session, template, "訊息", "123456789012345678")["send_status"] == "PENDING"
    client.send.assert_called_once()


def test_token_not_in_operations(db, session, template, client):
    logger = LoggingService(db, client, False)
    client.send.side_effect = RuntimeError(client.token)
    result = logger.send("error", session, template, "安全訊息", "123456789012345678")
    assert result["send_status"] == "UNKNOWN"
    assert client.token not in str(db.rows("SELECT * FROM operations"))
    with pytest.raises(ValueError):
        logger.send("leak", session, template, client.token, "123456789012345678")


def test_wrong_channel_and_ended_session_blocked(db, session, template, client):
    from src.session_service import SessionService
    logger = LoggingService(db, client, False)
    with pytest.raises(ValueError):
        logger.send("bad", session, template, "test", "999999999999999999")
    SessionService(db).end(session)
    with pytest.raises(ValueError):
        logger.send("end", session, template, "test", "123456789012345678")
    client.send.assert_not_called()


def test_concurrent_duplicate_only_sends_once(db, session, template, client):
    from concurrent.futures import ThreadPoolExecutor
    client.send.return_value = SendResult("SUCCESS", "123")
    logger = LoggingService(db, client, False)
    def send(_):
        return logger.send("concurrent", session, template, "訊息", "123456789012345678")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    client.send.assert_called_once()
    assert len(db.rows("SELECT * FROM operations")) == 1
    assert logger.get_operation("concurrent")["send_status"] == "SUCCESS"
    assert all(r["send_status"] in {"PENDING", "SUCCESS"} for r in results)


def test_final_write_failure_leaves_pending_no_retry(db, session, template, client):
    from contextlib import contextmanager
    original_connect = db.connect
    @contextmanager
    def failing_update():
        raise OSError("full disk")
        yield
    def send(*args):
        db.connect = failing_update
        return SendResult("SUCCESS", "123")
    client.send.side_effect = send
    logger = LoggingService(db, client, False)
    with pytest.raises(OSError):
        logger.send("disk-full", session, template, "訊息", "123456789012345678")
    db.connect = original_connect
    assert logger.send("disk-full", session, template, "訊息", "123456789012345678")["send_status"] == "PENDING"
    client.send.assert_called_once()
