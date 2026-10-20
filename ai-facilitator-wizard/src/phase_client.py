"""Authenticated server-to-server control calls; never use Discord for synchronization."""
import time
from urllib.parse import urlsplit
from datetime import datetime, timedelta
import requests


class PhaseControlError(RuntimeError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def valid_utc(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.utcoffset() == timedelta(0)
    except (ValueError, TypeError, AttributeError):
        return False


class PhaseControlClient:
    def __init__(self, url, token, http=None):
        self.url, self.token = url.rstrip("/"), token
        self.http = http if http is not None else requests.Session()

    def configured(self):
        try:
            parsed = urlsplit(self.url)
            valid_url = (parsed.scheme == "https" or
                         parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
            return bool(valid_url and parsed.hostname and not parsed.username and not parsed.password
                        and not parsed.query and not parsed.fragment and parsed.path in {"", "/"}
                        and parsed.port != 0 and len(self.token) >= 32)
        except ValueError:
            return False

    def _request(self, method, path, payload=None, allow_missing=False):
        if not self.configured():
            raise PhaseControlError("請設定有效 TOOL_AGENT_CONTROL_URL 與至少 32 字元的獨立 PHASE_SYNC_TOKEN")
        for attempt in range(2):
            try:
                kwargs = dict(headers={"Authorization": "Bearer " + self.token},
                              timeout=(3, 20), allow_redirects=False)
                if payload is not None:
                    kwargs["json"] = payload
                response = getattr(self.http, method)(self.url + path, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise PhaseControlError("階段控制連線中斷或逾時；結果待確認，請重試原事件或查詢目前階段", True) from None
            except requests.RequestException:
                raise PhaseControlError("階段控制請求設定無效或無法完成，請核對後端 URL 與密碼設定") from None
            if allow_missing and response.status_code == 404:
                return None
            if response.status_code == 200:
                try:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError()
                    return data
                except (ValueError, TypeError):
                    raise PhaseControlError("工具代理回應格式不完整；尚未確認階段同步", True) from None
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise PhaseControlError(f"工具代理暫時無法確認階段（HTTP {response.status_code}）；請重試原事件", True)
            messages = {400: "階段事件格式遭拒絕", 401: "階段同步密碼驗證失敗", 403: "伺服器未獲授權",
                        409: "事件、階段順序或實驗對應衝突；請先查詢目前階段"}
            raise PhaseControlError(messages.get(response.status_code, f"階段控制請求遭拒絕（HTTP {response.status_code}）"))

    def apply(self, event):
        data = self._request("post", "/internal/v1/phase-transitions", event)
        matches = data.get("status") == "applied" and all(data.get(k) == event[k] for k in
                  ("event_id", "channel_id", "phase_id", "sequence"))
        if not matches or type(data.get("sequence")) is not int or not valid_utc(data.get("effective_at")):
            raise PhaseControlError("切換回應與原事件不符；尚未確認同步，請查詢或重試原事件", True)
        return data

    def current(self, guild, channel):
        data = self._request("get", f"/internal/v1/channels/{guild}/{channel}/phase", allow_missing=True)
        if data is None:
            return None
        string_fields = ("experiment_id", "phase_id", "phase_name")
        if (data.get("guild_id") != guild or data.get("channel_id") != channel or
            any(not isinstance(data.get(k), str) or not data[k].strip() for k in string_fields) or
            type(data.get("sequence")) is not int or data["sequence"] < 1 or not valid_utc(data.get("effective_at"))):
            raise PhaseControlError("目前階段回應格式或頻道不符；不能確認同步", True)
        return data
