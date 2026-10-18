from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.database import Database
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
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    assert db.rows("SELECT * FROM sessions") == []
    assert not any("Session" in item.label for item in [*app.button, *app.selectbox, *app.text_input, *app.checkbox])
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


def test_switch_channel_clears_confirmation_and_separates_logs(tmp_path, monkeypatch):
    path = tmp_path / "switch.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"A組":"123456789012345678","B組":"223456789012345678"}')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="R01").click().run()
    app.checkbox(key="confirm_send").check().run()
    by_label(app.button, "確認模擬發送").click().run()
    app.selectbox(key="target_channel").select("223456789012345678").run()
    assert not app.exception
    assert not app.checkbox(key="confirm_send").value
    app.checkbox(key="confirm_send").check().run()
    assert not by_label(app.button, "確認模擬發送").disabled
    by_label(app.button, "確認模擬發送").click().run()
    assert not app.exception
    rows = Database(path).rows("SELECT * FROM operations")
    assert len(rows) == 2
    assert {r["discord_channel_id"] for r in rows} == {"123456789012345678", "223456789012345678"}
