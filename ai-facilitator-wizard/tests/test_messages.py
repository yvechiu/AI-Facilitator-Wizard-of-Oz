import json
import pytest
from src.message_service import load_messages, filter_messages, STAGES


def test_library_schema_and_categories():
    messages = load_messages()
    assert len(messages) >= 20
    assert len({m["message_id"] for m in messages}) == len(messages)
    assert {"討論停滯", "偏離任務", "過早收斂", "參與不平衡", "假性共識", "需要釐清問題"} <= {m["category"] for m in messages}
    assert {m["cps_substage"] for m in messages if m["intervention_type"] == "routine"} == {s for values in STAGES.values() for s in values}


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


def test_general_templates_and_fill_fields():
    from src.message_service import template_fields, render_template, has_placeholders
    general = filter_messages(load_messages(), intervention="general")
    assert len(general) == 7
    assert all(m["cps_stage"] == "跨階段" for m in general)
    template = next(m for m in general if m["message_id"] == "G03")
    assert template_fields(template["content"]) == ["當前活動", "成果要求", "操作說明"]
    incomplete = render_template(template["content"], {"當前活動": "探索資料"})
    assert has_placeholders(incomplete)
    rendered = render_template(template["content"], {"當前活動": "探索資料", "成果要求": "腳本要求", "操作說明": "腳本操作"})
    assert not has_placeholders(rendered)
    assert rendered == "目前進行的是探索資料，這一步需要完成腳本要求。請依照腳本操作進行。"
