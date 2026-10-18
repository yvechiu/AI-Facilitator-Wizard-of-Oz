from unittest.mock import Mock
import pytest
import requests
from src.channel_service import ChannelService
from src.discord_client import DiscordClient
from src.database import Database
from src.session_service import SessionService
from src.logging_service import LoggingService

GUILD = "111111111111111111"
CHANNEL = "222222222222222222"
BOT = "333333333333333333"


def http_client():
    http = Mock()
    http.get.return_value.status_code = 200
    http.get.return_value.json.return_value = {"id": BOT}
    http.post.return_value.status_code = 201
    http.post.return_value.json.return_value = {"id": CHANNEL, "type": 0}
    return http


def test_create_then_send_with_bot_permissions(db, template):
    http = http_client()
    client = DiscordClient("secret", http)
    channels = ChannelService(db, client, False)
    result = channels.create("new-channel", GUILD, "實驗一組")
    assert result["status"] == "SUCCESS" and result["channel_id"] == CHANNEL
    payload = http.post.call_args.kwargs["json"]
    assert payload["type"] == 0
    assert payload["permission_overwrites"] == [{"id": BOT, "type": 1, "allow": "3072", "deny": "0"}]
    assert http.get.call_args.args[0].endswith("/users/@me")
    channels.create("new-channel", GUILD, "實驗一組")
    assert http.post.call_count == 1
    assert ChannelService(Database(db.path), client, False).available()[0]["channel_id"] == CHANNEL
    service = SessionService(db)
    sid = service.create("實驗", "正式", "WOZ", CHANNEL)
    service.start(sid)
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {"id": "444444444444444444"}
    sent = LoggingService(db, client, False).send("send-first", sid, template, "程序引導", CHANNEL)
    assert sent["send_status"] == "SUCCESS"
    assert http.post.call_args.args[0].endswith(f"/channels/{CHANNEL}/messages")
    assert http.get.call_count == 1  # Only bot identity; no participant messages are fetched.


def test_demo_channel_creation_never_calls_api(db, client):
    result = ChannelService(db, client, True).create("demo", GUILD, "模擬組")
    assert result["status"] == "DEMO"
    client.create_text_channel.assert_not_called()
    assert ChannelService(db, client, False).available() == []


@pytest.mark.parametrize("status,expected", [(401,"FAILED"),(403,"FAILED"),(429,"FAILED"),(500,"UNKNOWN")])
def test_channel_errors_no_retry_or_token_leak(db, status, expected):
    http = http_client()
    http.post.return_value.status_code = status
    http.post.return_value.text = "secret"
    service = ChannelService(db, DiscordClient("secret", http), False)
    result = service.create("error", GUILD, "實驗")
    assert result["status"] == expected
    assert "secret" not in str(result)
    service.create("error", GUILD, "實驗")
    assert http.post.call_count == 1


def test_create_timeout_pending_committed_and_never_retried(db):
    http = http_client()
    def post(*args, **kwargs):
        assert db.rows("SELECT status FROM channel_operations")[0]["status"] == "PENDING"
        raise requests.Timeout("secret")
    http.post.side_effect = post
    service = ChannelService(db, DiscordClient("secret", http), False)
    assert service.create("timeout", GUILD, "實驗")["status"] == "UNKNOWN"
    service.create("timeout", GUILD, "實驗")
    assert http.post.call_count == 1


def test_bot_identity_failure_prevents_creation(db):
    http = http_client()
    http.get.return_value.status_code = 401
    result = ChannelService(db, DiscordClient("secret", http), False).create("unauthorized", GUILD, "實驗")
    assert result["status"] == "FAILED"
    http.post.assert_not_called()


def test_rollback_removes_old_channel_restriction(db):
    with db.connect() as conn:
        conn.execute("CREATE TRIGGER sessions_unique_channel_insert BEFORE INSERT ON sessions WHEN EXISTS (SELECT 1 FROM sessions WHERE discord_channel_id=NEW.discord_channel_id) BEGIN SELECT RAISE(ABORT, 'duplicate'); END")
    reopened = Database(db.path)
    sessions = SessionService(reopened)
    sessions.create("一", "正式", "WOZ", CHANNEL)
    sessions.create("二", "正式", "WOZ", CHANNEL)
    assert len(sessions.list()) == 2


def test_create_channel_ui_demo(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "channel-ui.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"預設":"123456789012345678"}')
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo 不可呼叫 API")
    monkeypatch.setattr(DiscordClient, "create_text_channel", forbidden)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    def label(elements, text):
        return next(e for e in elements if e.label == text)
    label(app.text_input, "Discord 伺服器 ID").set_value(GUILD).run()
    label(app.text_input, "新增文字頻道名稱").set_value("實驗新組").run()
    app.checkbox(key="channel_create_confirm").check().run()
    label(app.button, "模擬建立頻道").click().run()
    assert not app.exception
    assert "實驗新組" in app.selectbox(key="target_channel").options[-1]
    assert app.selectbox(key="target_channel").value != "123456789012345678"
    assert label(app.button, "模擬建立頻道").disabled
