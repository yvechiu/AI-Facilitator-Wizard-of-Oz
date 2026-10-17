from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.database import Database
from src.session_service import SessionService
from src.discord_client import DiscordClient


def by_label(elements, label):
    return next(e for e in elements if e.label == label)


def test_console_demo_preview_edit_send_and_next(tmp_path, monkeypatch):
    path = tmp_path / "ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"測試頻道":"123456789012345678"}')
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo 不可呼叫 DiscordClient.send")
    monkeypatch.setattr(DiscordClient, "send", forbidden)
    db = Database(path)
    service = SessionService(db)
    sid = service.create("UI Session", "前測", "WOZ", "123456789012345678")
    service.start(sid)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    app.button(key="R01").click().run()
    assert not app.exception
    assert app.text_area(key="draft").value
    app.text_area(key="draft").set_value("手動編輯，請每位成員分享觀點。").run()
    assert app.text_area(key="draft").value == "手動編輯，請每位成員分享觀點。"
    app.checkbox(key="confirm_send").check().run()
    by_label(app.button, "確認模擬發送").click().run()
    assert not app.exception
    row = db.rows("SELECT * FROM operations")[0]
    assert row["actual_sent_message"] == "手動編輯，請每位成員分享觀點。"
    assert row["send_status"] == "DEMO"
    assert by_label(app.button, "確認模擬發送").disabled
    by_label(app.button, "準備下一次操作（必要時先核對 Discord）").click().run()
    assert not app.exception
    assert not app.checkbox(key="confirm_send").value
    assert len(db.rows("SELECT * FROM operations")) == 1
    app.checkbox(key="confirm_send").check().run()
    app.text_area(key="draft").set_value("變更內容需重新確認").run()
    assert not app.checkbox(key="confirm_send").value
    assert by_label(app.button, "確認模擬發送").disabled
