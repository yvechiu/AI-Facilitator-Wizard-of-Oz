import json
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Config:
    demo_mode: bool
    token: str
    channels: dict[str, str]
    database_path: Path
    tool_agent_user_id: str = ""


def load_config() -> Config:
    load_dotenv(ROOT / ".env", override=False)
    mode = os.getenv("DEMO_MODE", "true").strip().lower()
    if mode not in {"true", "false"}:
        raise ValueError("DEMO_MODE 只能填 true 或 false")
    channels = json.loads(os.getenv("DISCORD_CHANNELS", '{"示範頻道":"123456789012345678"}'))
    if not isinstance(channels, dict) or not channels:
        raise ValueError("DISCORD_CHANNELS 必須是非空的 JSON 物件")
    if any(not isinstance(k, str) or not isinstance(v, str) or not v.isascii() or not v.isdigit() or not 17 <= len(v) <= 20 for k, v in channels.items()):
        raise ValueError("頻道 ID 必須為 17 至 20 位數的字串")
    tool_id = os.getenv("TOOL_AGENT_USER_ID", "").strip()
    if tool_id and (not tool_id.isascii() or not tool_id.isdigit() or not 17 <= len(tool_id) <= 20):
        raise ValueError("TOOL_AGENT_USER_ID 必須為工具代理的 17 至 20 位使用者 ID")
    path = Path(os.getenv("DATABASE_PATH", "runtime/experiments.sqlite3"))
    return Config(mode == "true", os.getenv("DISCORD_BOT_TOKEN", ""), channels, path if path.is_absolute() else ROOT / path, tool_id)
