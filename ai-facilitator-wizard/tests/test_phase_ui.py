from pathlib import Path
from unittest.mock import Mock
from streamlit.testing.v1 import AppTest
from src.database import Database
from src.phase_client import PhaseControlClient, PhaseControlError
from src.discord_client import DiscordClient

STAMP = "2026-10-20T06:00:00+00:00"
CHANNEL, OTHER = "1561280537442652240", "1561989705070018560"


def app_for(tmp_path, monkeypatch):
    path = tmp_path / "phase-ui.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DISCORD_CHANNELS", '{"一組":"' + CHANNEL + '","二組":"' + OTHER + '"}')
    monkeypatch.setenv("DISCORD_GUILD_ID", "1499044385793507350")
    monkeypatch.setenv("PHASE_SYNC_TOKEN", "phase-test-only-" * 4)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-test-not-real")
    sender = Mock()
    monkeypatch.setattr(DiscordClient, "send", sender)
    applied = {}
    def apply(event):
        applied[event["channel_id"]] = event.copy()
        return {"status": "applied", **{k:event[k] for k in ("event_id","channel_id","phase_id","sequence")}, "effective_at":STAMP}
    post = Mock(side_effect=apply)
    get = Mock(side_effect=lambda guild, channel: applied.get(channel) | {"effective_at":STAMP} if applied.get(channel) else None)
    monkeypatch.setattr(PhaseControlClient, "apply", lambda self,event: post(event))
    monkeypatch.setattr(PhaseControlClient, "current", lambda self,guild,channel: get(guild,channel))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    return app, path, post, get, sender


def phase_widget(app, prefix):
    elements = app.selectbox if prefix == "phase_choice:" else app.checkbox
    return next(e for e in elements if e.key and e.key.startswith(prefix))


def test_host_switch_is_durable_independent_and_never_posts_discord(tmp_path, monkeypatch):
    app, path, post, get, sender = app_for(tmp_path, monkeypatch)
    assert not app.exception
    phase_widget(app, "phase_choice:").select("A-2 探索資料").run()
    phase_widget(app, "phase_confirm:").check().run()
    app.button(key="phase_apply").click().run()
    assert not app.exception
    assert any("最後確認階段：A-2 探索資料" in m.value for m in app.markdown)
    assert app.session_state["navigation_state"]["selected"] == "A-1"
    assert app.button(key="phase_apply").disabled
    post.assert_called_once()
    sender.assert_not_called()
    app.button(key="tree:A-3").click().run()
    assert app.button(key="R05")
    assert Database(path).rows("SELECT * FROM phase_experiments WHERE channel_id=?", (CHANNEL,))[0]["phase_name"] == "A-2 探索資料"
    app.selectbox(key="target_channel").select(OTHER).run()
    assert any(m.value == "尚未開始討論階段" for m in app.caption)
    post.assert_called_once()
    restarted = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert any("最後確認階段：A-2 探索資料" in m.value for m in restarted.markdown)
    assert not restarted.exception


def test_failed_sync_shows_pending_and_retries_same_event(tmp_path, monkeypatch):
    app, path, post, get, sender = app_for(tmp_path, monkeypatch)
    apply_success = post.side_effect
    post.side_effect = PhaseControlError("階段同步密碼驗證失敗")
    phase_widget(app, "phase_confirm:").check().run()
    app.button(key="phase_apply").click().run()
    assert not app.exception
    assert any("階段同步未完成" in w.value for w in app.warning)
    event = Database(path).rows("SELECT * FROM phase_events")[0]
    assert event["status"] == "FAILED"
    assert Database(path).rows("SELECT * FROM phase_experiments")[0]["sequence"] == 0
    assert app.button(key="phase_apply").disabled
    app.button(key="R01").click().run()
    app.checkbox(key="confirm_send").check().run()
    send_button = next(b for b in app.button if b.label == "確認發送 Discord")
    assert send_button.disabled
    post.side_effect = apply_success
    app.button(key="phase_retry").click().run()
    assert not app.exception
    assert post.call_args_list[0].args == post.call_args_list[1].args
    assert len(Database(path).rows("SELECT * FROM phase_events")) == 1
    assert Database(path).rows("SELECT * FROM phase_events")[0]["status"] == "APPLIED"
    sender.assert_not_called()


def test_query_of_later_remote_phase_does_not_report_failed_event_as_applied(tmp_path, monkeypatch):
    import json
    app, path, post, get, sender = app_for(tmp_path, monkeypatch)
    post.side_effect = PhaseControlError("結果待確認", True)
    phase_widget(app, "phase_confirm:").check().run()
    app.button(key="phase_apply").click().run()
    event = Database(path).rows("SELECT * FROM phase_events")[0]
    payload = json.loads(event["payload"])
    later = {**payload, "phase_id":"later-phase", "phase_name":"A-2 探索資料", "sequence":2, "effective_at":STAMP}
    get.side_effect = lambda *args: later
    app.button(key="phase_refresh").click().run()
    assert not app.exception
    assert Database(path).rows("SELECT * FROM phase_events")[0]["status"] == "SUPERSEDED"
    assert Database(path).rows("SELECT * FROM phase_experiments")[0]["phase_name"] == "A-2 探索資料"
    assert any("未認定原事件成功" in w.value for w in app.warning)
    assert not any("事件同步已完成" in s.value for s in app.success)
    assert app.button(key="phase_apply").disabled
    post.assert_called_once()
    sender.assert_not_called()


def test_pending_event_after_browser_restart_keeps_original_choice_and_id(tmp_path, monkeypatch):
    app, path, post, get, sender = app_for(tmp_path, monkeypatch)
    success = post.side_effect
    post.side_effect = PhaseControlError("尚未確認", True)
    phase_widget(app, "phase_choice:").select("A-2 探索資料").run()
    phase_widget(app, "phase_confirm:").check().run()
    app.button(key="phase_apply").click().run()
    event = Database(path).rows("SELECT * FROM phase_events")[0]
    restarted = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert phase_widget(restarted, "phase_choice:").value == "A-2 探索資料"
    assert phase_widget(restarted, "phase_choice:").disabled
    post.side_effect = success
    restarted.button(key="phase_retry").click().run()
    assert not restarted.exception
    assert restarted.button(key="phase_apply").disabled
    assert post.call_args_list[0].args == post.call_args_list[1].args
    assert len(Database(path).rows("SELECT * FROM phase_events")) == 1
    assert Database(path).rows("SELECT * FROM phase_events")[0]["event_id"] == event["event_id"]
