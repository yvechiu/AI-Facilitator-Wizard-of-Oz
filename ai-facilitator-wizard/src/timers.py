"""Independent, manually started/stopped timers using monotonic elapsed time."""
import math
import time
from datetime import datetime, timezone


def new_timer():
    return {"running": False, "started_at": None, "ended_at": None,
            "started_utc": None, "ended_utc": None, "duration": 0}


def initialize_timers(state):
    state.setdefault("timers", {"overall": new_timer(), "stage": new_timer()})


def start_timer(timers, name, duration=0, now=None, utc=None):
    timer = timers[name]
    if timer["running"]:
        return
    if name == "stage" and (not isinstance(duration, int) or duration <= 0):
        raise ValueError("倒數時間必須大於零")
    timer.update(running=True, started_at=time.monotonic() if now is None else now,
                 ended_at=None, started_utc=utc or datetime.now(timezone.utc).isoformat(),
                 ended_utc=None, duration=duration)


def stop_timer(timers, name, now=None, utc=None):
    timer = timers[name]
    if not timer["running"]:
        return
    timer.update(running=False, ended_at=time.monotonic() if now is None else now,
                 ended_utc=utc or datetime.now(timezone.utc).isoformat())


def elapsed(timer, now=None):
    if timer["started_at"] is None:
        return 0.0
    end = (time.monotonic() if now is None else now) if timer["running"] else timer["ended_at"]
    return max(0.0, end - timer["started_at"])


def remaining(timer, now=None):
    return timer["duration"] - elapsed(timer, now)


def clock_text(seconds, round_up=False):
    seconds = max(0, math.ceil(seconds) if round_up else math.floor(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
