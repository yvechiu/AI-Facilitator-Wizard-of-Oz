import json
import re
from pathlib import Path

REQUIRED = {"message_id", "title", "cps_stage", "cps_substage", "intervention_type", "category",
            "trigger_condition", "observable_indicators", "content", "wizard_notes", "enabled", "template_version"}
STAGES = {
    "Understanding the Challenge": ["A-1 Constructing Opportunities", "A-2 Exploring Data", "A-3 Framing Problems"],
    "Generating Ideas": ["B-1 Generating Ideas"],
    "Preparing for Action": ["C-1 Developing Solutions"],
}


def load_messages(path=None):
    path = path or Path(__file__).resolve().parents[1] / "data/messages.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("訊息庫必須為非空陣列")
    seen = set()
    for m in data:
        if not isinstance(m, dict) or not REQUIRED <= m.keys():
            raise ValueError("模板缺少必要欄位")
        if any(not isinstance(m[k], str) or not m[k].strip() for k in REQUIRED - {"enabled"}):
            raise ValueError("模板文字欄位必須為非空字串")
        if type(m["enabled"]) is not bool or m["intervention_type"] not in {"routine", "special", "general"}:
            raise ValueError("模板 enabled 或介入類型錯誤")
        cross_stage = (m["cps_stage"] == "跨階段" and
                       (m["intervention_type"], m["cps_substage"]) in {("general", "通用訊息"), ("special", "特殊情境")})
        if not cross_stage and m["cps_substage"] not in STAGES.get(m["cps_stage"], []):
            raise ValueError("模板 CPS 階段錯誤")
        if m["message_id"] in seen or len(m["content"].encode("utf-16-le")) // 2 > 2000:
            raise ValueError("模板 ID 重複或內容超過 Discord 上限")
        seen.add(m["message_id"])
    return data


def filter_messages(messages, stage=None, substage=None, intervention=None, query=""):
    return [m for m in messages if m["enabled"] and (not stage or m["cps_stage"] == stage)
            and (not substage or m["cps_substage"] == substage)
            and (not intervention or m["intervention_type"] == intervention)
            and query.casefold() in " ".join(str(v) for v in m.values()).casefold()]


def template_fields(content):
    return list(dict.fromkeys(re.findall(r"〈([^〈〉]+)〉", content)))


def render_template(content, values):
    return re.sub(r"〈([^〈〉]+)〉", lambda match: values.get(match[1], "").strip() or match[0], content)


def has_placeholders(content):
    return "〈" in content or "〉" in content
