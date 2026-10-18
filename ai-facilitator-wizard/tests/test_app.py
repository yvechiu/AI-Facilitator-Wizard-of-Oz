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


def test_navigation_remembers_routine_and_skips_single_substage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "navigation.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not any(s.label in {"CPS 階段", "CPS 子階段", "介入類型"} for s in app.selectbox)
    app.button(key="nav_substage:A-2 Exploring Data").click().run()
    assert app.button(key="R03")
    app.button(key="nav_group:special").click().run()
    app.button(key="nav_special:參與不平衡").click().run()
    assert app.button(key="S07")
    app.button(key="nav_group:routine").click().run()
    assert app.button(key="R03")
    app.button(key="nav_stage:Generating Ideas").click().run()
    assert app.button(key="R07")
    assert not any(b.key and b.key.startswith("nav_substage:") for b in app.button)
    app.button(key="nav_stage:Preparing for Action").click().run()
    assert app.button(key="R09")
    assert not any(b.key and b.key.startswith("nav_substage:") for b in app.button)
    assert not app.exception


def test_general_fields_block_send_and_preserve_edits(tmp_path, monkeypatch):
    path = tmp_path / "general.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo 不可呼叫 API")
    monkeypatch.setattr(DiscordClient, "send", forbidden)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="nav_group:general").click().run()
    assert len([b for b in app.button if b.key and b.key.startswith("G")]) == 7
    app.button(key="G03").click().run()
    app.checkbox(key="confirm_send").check().run()
    assert by_label(app.button, "確認模擬發送").disabled
    for field, value in [("當前活動", "探索資料"), ("成果要求", "腳本成果"), ("操作說明", "腳本操作")]:
        app.text_input(key=f"field:G03:{field}").set_value(value).run()
    assert "〈" not in app.text_area(key="draft").value
    app.text_area(key="draft").set_value("手動微調後的活動說明").run()
    app.checkbox(key="confirm_send").check().run()
    assert app.text_area(key="draft").value == "手動微調後的活動說明"
    by_label(app.button, "確認模擬發送").click().run()
    assert not app.exception
    row = Database(path).rows("SELECT * FROM operations")[0]
    assert row["send_status"] == "DEMO" and row["intervention_type"] == "general"
    assert row["actual_sent_message"] == "手動微調後的活動說明"
    assert "〈成果要求〉" in row["original_message"]
    app.button(key="nav_group:special").click().run()
    assert not app.checkbox  or not any(c.key == "confirm_send" for c in app.checkbox)


def test_cross_category_search(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "search.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.text_input(key="message_search").set_value("成果要求").run()
    assert app.button(key="G03")
    app.button(key="G03").click().run()
    app.button(key="nav_group:routine").click().run()
    assert app.text_input(key="message_search").value == ""
    assert not any(c.key == "confirm_send" for c in app.checkbox)
    assert not app.exception
