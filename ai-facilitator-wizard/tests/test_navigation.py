from copy import deepcopy
import pytest
from src.message_service import load_messages
from src.navigation import navigation_tree, leaf_for, search_messages, breadcrumb


def leaves(tree):
    return [leaf for node in tree for leaf in (leaves(node["children"]) if "children" in node else [node["id"]])]


def test_all_existing_messages_mapped_without_mutation():
    messages = load_messages()
    original = deepcopy(messages)
    tree = navigation_tree(messages)
    leaf_ids = leaves(tree)
    assigned = [leaf_for(m) for m in messages]
    assert set(assigned) <= set(leaf_ids)
    assert "unmapped" not in assigned
    mapped = [m["message_id"] for leaf in leaf_ids for m in search_messages(messages, leaf)]
    assert sorted(mapped) == sorted(m["message_id"] for m in messages if m["enabled"])
    assert messages == original
    assert "C-2" not in leaf_ids
    assert breadcrumb("special", tree) == "特殊情境介入"
    assert leaf_for(next(m for m in messages if m["category"] == "偏離任務")) == "special"


def test_unknown_messages_retained_for_human_review():
    message = {**load_messages()[0], "message_id": "new-special", "intervention_type": "routine", "cps_substage": "未知階段", "category": "尚未分類"}
    assert leaf_for(message) == "unmapped"
    assert "unmapped" in leaves(navigation_tree([message]))
    assert search_messages([message], "unmapped") == [message]


@pytest.mark.parametrize("query", ["開啟挑戰探索", "每位成員", "常態流程引導", "A-1 建構機會"])
def test_search_title_content_and_tags(query):
    assert search_messages(load_messages(), "A-1", query)
    assert all(m["intervention_type"] == "general" for m in search_messages(load_messages(), "general", query))
    assert search_messages(load_messages(), "general", query, all_library=True)


def test_search_displayed_category_alias():
    matches = search_messages(load_messages(), "special", "討論偏題")
    assert matches and all(m["category"] == "偏離任務" for m in matches)
