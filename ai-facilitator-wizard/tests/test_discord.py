from unittest.mock import Mock
import pytest
import requests
from src.discord_client import DiscordClient


def test_success_mentions_nonce_and_no_redirects():
    http = Mock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {"id": "987654321012345678"}
    result = DiscordClient("secret", http).send("123456789012345678", "@everyone 測試", "abc-123")
    assert result.status == "SUCCESS"
    assert result.message_id == "987654321012345678"
    kwargs = http.post.call_args.kwargs
    assert kwargs["json"]["allowed_mentions"]["parse"] == []
    assert kwargs["json"]["enforce_nonce"] is True
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == (5, 15)


@pytest.mark.parametrize("status, expected", [(401,"FAILED"), (403,"FAILED"), (404,"FAILED"), (429,"FAILED"), (500,"UNKNOWN"), (302,"FAILED")])
def test_http_failure_does_not_echo_body_or_retry(status, expected):
    http = Mock()
    http.post.return_value.status_code = status
    http.post.return_value.text = "secret token should never be recorded"
    result = DiscordClient("secret", http).send("123456789012345678", "測試", "abc")
    assert result.status == expected
    assert "secret" not in result.error
    http.post.assert_called_once()


@pytest.mark.parametrize("error", [requests.Timeout("secret"), requests.ConnectionError("secret")])
def test_network_uncertainty(error):
    http = Mock()
    http.post.side_effect = error
    result = DiscordClient("secret", http).send("123456789012345678", "測試", "abc")
    assert result.status == "UNKNOWN"
    assert "secret" not in result.error
    http.post.assert_called_once()


def test_missing_token_no_request():
    http = Mock()
    assert DiscordClient("", http).send("123456789012345678", "test", "abc").status == "FAILED"
    http.post.assert_not_called()


def test_malformed_success_unknown():
    http = Mock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {}
    assert DiscordClient("secret", http).send("123456789012345678", "測試", "abc").status == "UNKNOWN"


def test_only_configured_tool_bot_can_be_mentioned():
    http = Mock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {"id": "987654321012345678"}
    client = DiscordClient("secret", http, tool_agent_user_id="123456789012345678")
    client.send("223456789012345678", "<@123456789012345678> 摘要 @everyone <@999999999999999999>", "request")
    assert http.post.call_args.kwargs["json"]["allowed_mentions"] == {"parse": [], "replied_user": False, "users": ["123456789012345678"]}
    client.send("223456789012345678", "＠工具代理 摘要", "plain")
    assert "users" not in http.post.call_args.kwargs["json"]["allowed_mentions"]


def test_tool_agent_summary_protocol_matches_live_whitelist_version():
    http = Mock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {"id": "987654321012345678"}
    client = DiscordClient("test-token-not-real", http, tool_agent_user_id="1562006162856222725")
    result = client.send("223456789012345678", "<@1562006162856222725> 摘要", "summary-request")
    assert result.status == "SUCCESS"
    payload = http.post.call_args.kwargs["json"]
    assert payload["content"] == "<@1562006162856222725> 摘要"
    assert payload["allowed_mentions"]["users"] == ["1562006162856222725"]
    assert payload["allowed_mentions"]["parse"] == []
