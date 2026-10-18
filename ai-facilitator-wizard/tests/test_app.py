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
    assert any("DEMO · Discord Message ID" in message.value for message in app.success)
    assert not any("DeltaGenerator" in message.value for message in app.markdown)
    by_label(app.button, "檢查資料完整性").click().run()
    assert not app.exception
    assert any("SQLite 完整性檢查通過" in message.value for message in app.success)
    assert not any("DeltaGenerator" in message.value for message in app.markdown)
    assert by_label(app.button, "確認模擬發送").disabled
    by_label(app.button, "準備下一次操作（必要時先核對 Discord）").click().run()
    assert not app.exception
    assert not app.checkbox(key="confirm_send").value
    assert len(db.rows("SELECT * FROM operations")) == 1
    app.checkbox(key="confirm_send").check().run()
    app.text_area(key="draft").set_value("變更內容需重新確認").run()
    assert not app.checkbox(key="confirm_send").value
    assert by_label(app.button, "確認模擬發送").disabled


def test_session_drives_channel_and_switch_requires_confirmation(tmp_path, monkeypatch):
    path = tmp_path / "bound-ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"A組":"123456789012345678","B組":"223456789012345678"}')
    db = Database(path)
    service = SessionService(db)
    a = service.create("A組實驗", "正式", "WOZ", "123456789012345678")
    b = service.create("B組實驗", "正式", "WOZ", "223456789012345678")
    service.start(a)
    service.start(b)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    assert not any(s.label in {"目標 Discord 頻道", "新場次 Discord 頻道"} for s in app.selectbox)
    app.selectbox(key="selected_session").select(a).run()
    app.button(key="R01").click().run()
    app.checkbox(key="confirm_send").check().run()
    app.selectbox(key="selected_session").select(b).run()
    assert not app.exception
    assert not app.checkbox(key="confirm_send").value
    assert any("目標：B組（223456789012345678）" in m.value for m in app.markdown)
    app.checkbox(key="confirm_send").check().run()
    by_label(app.button, "確認模擬發送").click().run()
    assert not app.exception
    row = db.rows("SELECT * FROM operations")[0]
    assert row["session_id"] == b and row["discord_channel_id"] == "223456789012345678"
    assert row["send_status"] == "DEMO"


def test_create_session_only_offers_unused_channels(tmp_path, monkeypatch):
    path = tmp_path / "create-ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"已使用":"123456789012345678","未使用":"223456789012345678"}')
    service = SessionService(Database(path))
    service.create("原場次", "正式", "WOZ", "123456789012345678")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert by_label(app.selectbox, "新場次 Discord 頻道").options == ["未使用"]
    by_label(app.text_input, "實驗場次名稱").set_value("新實驗")
    by_label(app.button, "建立").click().run()
    assert not app.exception
    sid = app.selectbox(key="selected_session").value
    assert service.get(sid)["session_name"] == "新實驗"
    assert service.get(sid)["discord_channel_id"] == "223456789012345678"


def test_missing_config_channel_disables_send(tmp_path, monkeypatch):
    path = tmp_path / "missing-ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"另一個頻道":"223456789012345678"}')
    service = SessionService(Database(path))
    sid = service.create("保留場次", "正式", "WOZ", "123456789012345678")
    service.start(sid)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="R01").click().run()
    app.checkbox(key="confirm_send").check().run()
    assert not app.exception
    assert by_label(app.button, "確認模擬發送").disabled
    assert any("不在 .env 設定中" in m.value for m in app.warning)
