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


def test_tree_navigation_preserves_experiment_and_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "navigation.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15)
    experiment = {"stage": "A-2", "status": "暫停", "remaining": "8 分鐘"}
    app.session_state["experiment_state"] = experiment.copy()
    app.run()
    assert app.session_state["navigation_state"]["selected"] == "A-1"
    assert "▾" in app.button(key="tree:routine").label
    assert "▾" in app.button(key="tree:phase:0").label
    assert app.button(key="R01")
    app.button(key="tree:A-2").click().run()
    assert app.button(key="R03")
    app.button(key="tree:routine").click().run()
    assert "▸" in app.button(key="tree:routine").label
    assert not any(b.key == "tree:A-2" for b in app.button)
    assert app.button(key="R03")
    app.button(key="tree:routine").click().run()
    app.button(key="tree:phase:1").click().run()
    app.button(key="tree:B-1").click().run()
    assert app.button(key="R07")
    app.button(key="tree:phase:2").click().run()
    app.button(key="tree:C-1").click().run()
    assert app.button(key="R09")
    app.button(key="tree:special").click().run()
    app.button(key="tree:special:participation").click().run()
    assert app.button(key="S07")
    app.button(key="tree:A-1").click().run()
    assert app.button(key="R01")
    assert app.session_state["experiment_state"] == experiment
    assert any(m.value == "A-2 探索資料" for m in app.markdown)
    assert not app.exception


def test_general_fields_block_send_and_preserve_edits(tmp_path, monkeypatch):
    path = tmp_path / "general.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo 不可呼叫 API")
    monkeypatch.setattr(DiscordClient, "send", forbidden)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="tree:general").click().run()
    app.button(key="tree:general:flow").click().run()
    assert len([b for b in app.button if b.key in {"G03", "G07"}]) == 2
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
    app.button(key="tree:special").click().run()
    app.button(key="tree:special:stall").click().run()
    assert app.text_area(key="draft").value == "手動微調後的活動說明"
    assert not app.checkbox(key="confirm_send").value


def test_cross_category_search(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "search.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.text_input(key="message_search").set_value("成果要求").run()
    assert not any(b.key == "G03" for b in app.button)
    app.checkbox(key="search_all").check().run()
    assert app.button(key="G03")
    app.button(key="G03").click().run()
    app.text_input(key="field:G03:當前活動").set_value("探索資料").run()
    app.button(key="tree:A-2").click().run()
    assert app.text_input(key="field:G03:當前活動").value == "探索資料"
    assert not app.checkbox(key="confirm_send").value
    assert not app.exception


def test_drafts_survive_switching_messages_and_reselection_does_not_resend(tmp_path, monkeypatch):
    path = tmp_path / "drafts.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="send:R01").click().run()
    assert Database(path).rows("SELECT * FROM operations") == []
    app.text_area(key="draft").set_value("修改第一則\n保留換行").run()
    app.button(key="R02").click().run()
    app.text_area(key="draft").set_value("修改第二則").run()
    app.button(key="R01").click().run()
    assert app.text_area(key="draft").value == "修改第一則\n保留換行"
    assert any(c.value == "修改第一則\n保留換行" for c in app.code)
    app.checkbox(key="confirm_send").check().run()
    by_label(app.button, "確認模擬發送").click().run()
    app.button(key="R02").click().run()
    assert app.text_area(key="draft").value == "修改第二則"
    app.button(key="send:R01").click().run()
    assert by_label(app.button, "確認模擬發送").disabled
    assert len(Database(path).rows("SELECT * FROM operations")) == 1
    assert not app.exception


def test_every_tree_category_can_expand_select_and_collapse(tmp_path, monkeypatch):
    from src.navigation import navigation_tree, search_messages
    from src.message_service import load_messages
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "all-categories.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    messages = load_messages()
    for root in navigation_tree(messages):
        if root["id"] not in app.session_state["navigation_state"]["expanded"]:
            app.button(key=f"tree:{root['id']}").click().run()
        for node in root["children"]:
            if "children" in node:
                if node["id"] not in app.session_state["navigation_state"]["expanded"]:
                    app.button(key=f"tree:{node['id']}").click().run()
                selectable = node["children"]
            else:
                selectable = [node]
            for leaf in selectable:
                app.button(key=f"tree:{leaf['id']}").click().run()
                expected = {m["message_id"] for m in search_messages(messages, leaf["id"])}
                actual = {b.key for b in app.button if b.key in {m["message_id"] for m in messages}}
                assert actual == expected
                assert not app.exception
            if "children" in node:
                app.button(key=f"tree:{node['id']}").click().run()
                assert all(not any(b.key == f"tree:{leaf['id']}" for b in app.button) for leaf in selectable)
        app.button(key=f"tree:{root['id']}").click().run()
        assert root["id"] not in app.session_state["navigation_state"]["expanded"]
    assert app.session_state["experiment_state"] == {"stage": None, "status": "未開始", "remaining": None}


def test_failed_send_preserves_error_and_blocks_duplicate(tmp_path, monkeypatch):
    from src.discord_client import SendResult
    from unittest.mock import Mock
    path = tmp_path / "failed-ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "ui-test-not-a-real-token")
    sender = Mock(return_value=SendResult("FAILED", error="Discord 拒絕請求（HTTP 403）"))
    monkeypatch.setattr(DiscordClient, "send", sender)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    app.button(key="send:R01").click().run()
    app.checkbox(key="confirm_send").check().run()
    by_label(app.button, "確認發送 Discord").click().run()
    assert any("FAILED" in w.value and "403" in w.value for w in app.warning)
    assert by_label(app.button, "確認發送 Discord").disabled
    app.button(key="R01").click().run()
    assert by_label(app.button, "確認發送 Discord").disabled
    sender.assert_called_once()
    row = Database(path).rows("SELECT * FROM operations")[0]
    assert row["send_status"] == "FAILED" and "403" in row["error_message"]
    assert "ui-test-not-a-real-token" not in str(row)
    assert not app.exception
