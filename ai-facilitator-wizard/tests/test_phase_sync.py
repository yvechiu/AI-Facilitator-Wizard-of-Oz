import json
from unittest.mock import Mock
import pytest
import requests
from src.database import Database
from src.phase_client import PhaseControlClient, PhaseControlError
from src.phase_service import PhaseService

GUILD, CHANNEL, OTHER = "1499044385793507350", "1561280537442652240", "1561989705070018560"
STAMP = "2026-10-20T06:00:00+00:00"


def response(code, data=None):
    r = Mock(status_code=code)
    r.json.return_value = data
    return r


def ack(event):
    return {"status": "applied", **{key: event[key] for key in ("event_id", "channel_id", "phase_id", "sequence")}, "effective_at": STAMP}


def remote(event):
    return {key: event[key] for key in ("experiment_id", "guild_id", "channel_id", "phase_id", "phase_name", "sequence")} | {"effective_at": STAMP}


@pytest.fixture
def setup(db):
    client = Mock()
    client.configured.return_value = True
    service = PhaseService(db, client, GUILD, {CHANNEL, OTHER}, False)
    return service, client


def test_persist_before_network_retry_reuses_exact_event_after_restart(db, setup):
    service, client = setup
    event = service.prepare(CHANNEL, "A-1 建構機會")
    payload = json.loads(event["payload"])
    client.apply.side_effect = PhaseControlError("逾時，待確認", True)
    with pytest.raises(PhaseControlError):
        service.sync(event["event_id"])
    assert service.context(CHANNEL)["sequence"] == 0
    assert service.pending(CHANNEL)["status"] == "UNKNOWN"
    reopened = PhaseService(Database(db.path), client, GUILD, {CHANNEL, OTHER}, False)
    same = reopened.prepare(CHANNEL, "A-1 建構機會")
    assert same["event_id"] == event["event_id"] and same["payload"] == event["payload"]
    client.apply.side_effect = None
    client.apply.return_value = ack(payload)
    client.current.return_value = remote(payload)
    current = reopened.sync(same["event_id"])
    assert current["phase_id"] == payload["phase_id"] and current["effective_at"] == STAMP
    assert client.apply.call_args_list[0].args == client.apply.call_args_list[1].args
    assert reopened.pending(CHANNEL) is None
    assert len(db.rows("SELECT * FROM phase_events")) == 1


def test_phase_ids_repeat_names_sequence_and_channel_isolation_and_old_ack(db, setup):
    service, client = setup
    first = service.prepare(CHANNEL, "A-1 建構機會")
    a = json.loads(first["payload"])
    client.apply.return_value, client.current.return_value = ack(a), remote(a)
    service.sync(first["event_id"])
    second = service.prepare(CHANNEL, "A-1 建構機會")
    b = json.loads(second["payload"])
    assert b["phase_id"] != a["phase_id"] and b["sequence"] == 2
    assert b["experiment_id"] == a["experiment_id"]
    client.apply.return_value, client.current.return_value = ack(b), remote(b)
    service.sync(second["event_id"])
    client.apply.return_value = ack(a)
    current = service.sync(first["event_id"])
    assert current["phase_id"] == b["phase_id"] and current["sequence"] == 2
    assert service.context(OTHER)["sequence"] == 0
    assert service.context(OTHER)["experiment_id"] != current["experiment_id"]


def test_demo_never_calls_control_api_and_separates_real_bindings(db):
    client = Mock()
    demo = PhaseService(db, client, GUILD, {CHANNEL}, True)
    event = demo.prepare(CHANNEL, "B-1 產生點子")
    current = demo.sync(event["event_id"])
    original_time = current["effective_at"]
    assert demo.sync(event["event_id"])["effective_at"] == original_time
    assert client.method_calls == []
    live = PhaseService(db, client, GUILD, {CHANNEL}, False)
    assert live.context(CHANNEL)["sequence"] == 0
    assert live.context(CHANNEL)["experiment_id"] != current["experiment_id"]


def test_pending_blocks_new_event_and_invalid_channel_has_no_http(db, setup):
    service, client = setup
    service.prepare(CHANNEL, "A-1 建構機會")
    with pytest.raises(ValueError, match="未完成"):
        service.prepare(CHANNEL, "A-2 探索資料")
    with pytest.raises(ValueError):
        service.prepare("999999999999999999", "A-1 建構機會")
    assert client.method_calls == []


def test_ack_without_current_confirmation_is_not_success_and_query_reconciles(db, setup):
    service, client = setup
    event = service.prepare(CHANNEL, "A-2 探索資料")
    payload = json.loads(event["payload"])
    client.apply.return_value = ack(payload)
    client.current.side_effect = PhaseControlError("查詢離線", True)
    with pytest.raises(PhaseControlError):
        service.sync(event["event_id"])
    assert service.context(CHANNEL)["sequence"] == 0
    assert service.pending(CHANNEL)["status"] == "UNKNOWN"
    client.current.side_effect = None
    client.current.return_value = remote(payload)
    assert service.refresh(CHANNEL)["phase_id"] == payload["phase_id"]
    assert service.pending(CHANNEL) is None
    assert client.apply.call_count == 1


def test_fresh_install_can_recover_binding_from_authenticated_remote(db, setup):
    service, client = setup
    event = dict(experiment_id="existing-experiment", guild_id=GUILD, channel_id=CHANNEL,
                 phase_id="existing-phase", phase_name="A-2 探索資料", sequence=2)
    client.current.return_value = remote(event)
    assert service.refresh(CHANNEL)["experiment_id"] == "existing-experiment"
    assert service.prepare(CHANNEL, "A-3 陳述問題")["sequence"] == 3


def test_stale_or_other_experiment_cannot_override_local(db, setup):
    service, client = setup
    event = service.prepare(CHANNEL, "A-1 建構機會")
    payload = json.loads(event["payload"])
    client.apply.return_value, client.current.return_value = ack(payload), remote(payload)
    service.sync(event["event_id"])
    client.current.return_value = remote(payload) | {"experiment_id": "different"}
    with pytest.raises(PhaseControlError):
        service.refresh(CHANNEL)
    assert service.context(CHANNEL)["experiment_id"] == payload["experiment_id"]
    client.current.return_value = None
    with pytest.raises(PhaseControlError):
        service.refresh(CHANNEL)
    assert service.context(CHANNEL)["sequence"] == 1


@pytest.mark.parametrize("code,uncertain,count", [(401,False,1),(403,False,1),(409,False,1),(503,True,2),(429,True,2)])
def test_http_errors_are_bounded_safe_and_never_echo_secret(code, uncertain, count, monkeypatch):
    monkeypatch.setattr("src.phase_client.time.sleep", lambda _: None)
    http = Mock()
    http.post.return_value = response(code, {"error": "PRIVATE_TOKEN"})
    client = PhaseControlClient("http://127.0.0.1:5860", "PRIVATE_TOKEN" * 4, http)
    with pytest.raises(PhaseControlError) as caught:
        client.apply({})
    assert caught.value.uncertain == uncertain and "PRIVATE_TOKEN" not in str(caught.value)
    assert http.post.call_count == count
    assert http.post.call_args.kwargs["timeout"] == (3,20)
    assert http.post.call_args.kwargs["allow_redirects"] is False


def test_timeout_retries_identical_payload_and_validates_ack(monkeypatch):
    monkeypatch.setattr("src.phase_client.time.sleep", lambda _: None)
    event = dict(event_id="e", channel_id=CHANNEL, phase_id="p", sequence=1)
    http = Mock()
    http.post.side_effect = [requests.Timeout("SECRET"), response(200, ack(event))]
    client = PhaseControlClient("http://localhost:5860", "x" * 32, http)
    assert client.apply(event)["effective_at"] == STAMP
    assert http.post.call_args_list[0].kwargs["json"] == http.post.call_args_list[1].kwargs["json"]
    http.post.side_effect = None
    http.post.return_value = response(200, ack(event) | {"channel_id": OTHER})
    with pytest.raises(PhaseControlError):
        client.apply(event)


def test_invalid_config_cannot_send_secret_to_unprotected_remote():
    for url in ["http://example.com:5860", "https://user:pass@example.com", "https://example.com?token=x"]:
        http = Mock()
        with pytest.raises(PhaseControlError):
            PhaseControlClient(url, "x" * 32, http).apply({})
        http.post.assert_not_called()
