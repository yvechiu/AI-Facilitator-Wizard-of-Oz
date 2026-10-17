import json
import pytest
from src.message_service import load_messages, filter_messages, STAGES


def test_library_schema_and_categories():
    messages = load_messages()
    assert len(messages) >= 20
    assert len({m["message_id"] for m in messages}) == len(messages)
    assert {"討論停滯", "偏離任務", "過早收斂", "參與不平衡", "假性共識", "需要釐清問題"} <= {m["category"] for m in messages}
    assert {m["cps_substage"] for m in messages} == {s for values in STAGES.values() for s in values}


def test_filter_and_disabled():
    messages = load_messages()
    result = filter_messages(messages, "Generating Ideas", "B-1 Generating Ideas", "routine", "點子")
    assert result and all(m["cps_stage"] == "Generating Ideas" and m["intervention_type"] == "routine" for m in result)
    assert filter_messages(messages, query="不存在的搜尋字串") == []
    assert filter_messages([{**messages[0], "enabled": False}]) == []


def test_bad_template_rejected(tmp_path, template):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([template, template]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_messages(path)
