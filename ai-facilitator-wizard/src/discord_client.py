from dataclasses import dataclass
import requests


@dataclass(frozen=True)
class SendResult:
    status: str
    message_id: str | None = None
    error: str | None = None


class DiscordClient:
    def __init__(self, token, http=None):
        self.token = token
        self.http = http if http is not None else requests.Session()

    def send(self, channel_id, content, operation_id):
        if not self.token:
            return SendResult("FAILED", error="尚未設定 Bot Token")
        try:
            response = self.http.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {self.token}"},
                json={"content": content, "allowed_mentions": {"parse": [], "replied_user": False},
                      "nonce": operation_id.replace("-", "")[:25], "enforce_nonce": True},
                timeout=(5, 15), allow_redirects=False,
            )
        except requests.Timeout:
            return SendResult("UNKNOWN", error="請求逾時；請至 Discord 核對，禁止直接重試此操作")
        except requests.RequestException:
            return SendResult("UNKNOWN", error="連線中斷，無法確認是否送出；請至 Discord 核對")
        if response.status_code == 429:
            wait = ""
            try:
                seconds = response.json().get("retry_after")
                if isinstance(seconds, (int, float)) and 0 <= seconds <= 86400:
                    wait = f"；至少等待 {seconds:g} 秒"
            except (ValueError, AttributeError, TypeError):
                pass
            return SendResult("FAILED", error=f"Discord Rate Limit（HTTP 429）{wait}；等待限流解除後再建立新操作")
        if response.status_code >= 500:
            return SendResult("UNKNOWN", error="Discord 伺服器錯誤；無法確認是否送出，請人工核對")
        if response.status_code != 200:
            return SendResult("FAILED", error=f"Discord 拒絕請求（HTTP {response.status_code}）；請檢查 Bot 權限、頻道及 Token")
        try:
            mid = response.json()["id"]
            if not isinstance(mid, str) or not mid.isascii() or not mid.isdigit():
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            return SendResult("UNKNOWN", error="Discord 回應缺少有效訊息 ID；請人工核對")
        return SendResult("SUCCESS", message_id=mid)
