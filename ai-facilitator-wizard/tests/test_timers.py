import pytest
from src.timers import initialize_timers, start_timer, stop_timer, elapsed, remaining, clock_text


def test_stopwatch_only_runs_between_manual_start_and_stop():
    state = {}
    initialize_timers(state)
    timers = state["timers"]
    assert elapsed(timers["overall"], now=20) == 0
    stop_timer(timers, "overall", now=20)
    assert timers["overall"]["ended_at"] is None
    start_timer(timers, "overall", now=100, utc="2026-10-20T01:00:00+00:00")
    start_timer(timers, "overall", now=102)
    assert timers["overall"]["started_at"] == 100
    assert elapsed(timers["overall"], now=165.9) == pytest.approx(65.9)
    stop_timer(timers, "overall", now=166, utc="2026-10-20T01:01:06+00:00")
    stop_timer(timers, "overall", now=180)
    assert elapsed(timers["overall"], now=999) == 66
    assert timers["overall"]["ended_utc"] == "2026-10-20T01:01:06+00:00"
    assert clock_text(elapsed(timers["overall"], now=999)) == "00:01:06"
    start_timer(timers, "overall", now=1000)
    assert elapsed(timers["overall"], now=1000) == 0
    assert timers["overall"]["ended_at"] is None


def test_countdown_timeup_does_not_implicitly_stop_other_timer():
    state = {}
    initialize_timers(state)
    timers = state["timers"]
    start_timer(timers, "overall", now=0)
    start_timer(timers, "stage", duration=65, now=10)
    assert remaining(timers["stage"], now=70) == 5
    assert remaining(timers["stage"], now=80) == -5
    assert timers["stage"]["running"] and timers["overall"]["running"]
    assert clock_text(remaining(timers["stage"], now=80)) == "00:00:00"
    stop_timer(timers, "stage", now=82)
    assert remaining(timers["stage"], now=999) == -7
    assert timers["overall"]["running"]
    start_timer(timers, "stage", duration=30, now=90)
    assert remaining(timers["stage"], now=90) == 30
    assert timers["overall"]["started_at"] == 0


@pytest.mark.parametrize("duration", [0, -1, 1.5])
def test_countdown_rejects_invalid_duration(duration):
    state = {}
    initialize_timers(state)
    with pytest.raises(ValueError):
        start_timer(state["timers"], "stage", duration=duration)
    assert not state["timers"]["stage"]["running"]


def test_format_and_initialization_preserve_running_timers():
    state = {}
    initialize_timers(state)
    start_timer(state["timers"], "overall", now=0)
    initialize_timers(state)
    assert state["timers"]["overall"]["running"]
    assert clock_text(0.1, round_up=True) == "00:00:01"
    assert clock_text(-3, round_up=True) == "00:00:00"
    assert clock_text(3661.9) == "01:01:01"


def test_timer_ui_manual_controls_are_independent_and_keep_draft(tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "timers-ui.sqlite3"))
    monkeypatch.setenv("DEMO_MODE", "true")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
    assert not app.exception
    assert app.button(key="overall_stop").disabled and app.button(key="stage_stop").disabled
    app.button(key="overall_start").click().run()
    started = app.session_state["timers"]["overall"]["started_at"]
    app.number_input(key="stage_minutes").set_value(0).run()
    app.number_input(key="stage_seconds").set_value(0).run()
    assert app.button(key="stage_start").disabled
    app.number_input(key="stage_seconds").set_value(2).run()
    app.button(key="stage_start").click().run()
    assert app.session_state["timers"]["stage"]["duration"] == 2
    assert app.session_state["timers"]["overall"]["started_at"] == started
    assert app.button(key="stage_start").disabled and app.number_input(key="stage_seconds").disabled
    app.session_state["timers"]["stage"]["started_at"] -= 5
    app.run()
    assert app.session_state["timers"]["stage"]["running"]
    assert any("時間到" in c.value for c in app.caption)
    app.button(key="stage_stop").click().run()
    assert not app.session_state["timers"]["stage"]["running"]
    assert app.session_state["timers"]["overall"]["running"]
    app.button(key="tree:A-2").click().run()
    app.button(key="R03").click().run()
    app.text_area(key="draft").set_value("保持我的編輯內容").run()
    app.button(key="overall_stop").click().run()
    stopped = app.session_state["timers"]["overall"]["ended_at"]
    app.run()
    assert app.session_state["timers"]["overall"]["ended_at"] == stopped
    assert app.text_area(key="draft").value == "保持我的編輯內容"
    assert app.session_state["navigation_state"]["selected"] == "A-2"
    assert not app.exception
