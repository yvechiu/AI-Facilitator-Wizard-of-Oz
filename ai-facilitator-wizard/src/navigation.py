"""Presentation-only classification. Message JSON and experiment stages stay unchanged."""
from src.message_service import STAGES

STAGE_LABELS = dict(zip([s for group in STAGES.values() for s in group],
                       ["A-1 建構機會", "A-2 探索資料", "A-3 陳述問題", "B-1 產生點子", "C-1 發展解決方案"]))
PHASE_LABELS = ["理解挑戰（Understanding the Challenge）", "產生點子（Generating Ideas）", "行動準備（Preparing for Action）"]
SPECIAL = [
    ("stall", "討論停滯", ["討論停滯"]),
    ("offtopic", "討論偏題", ["偏離任務", "討論偏題"]),
    ("converge", "過早收斂", ["過早收斂"]),
    ("participation", "參與不平衡", ["參與不平衡"]),
    ("consensus", "假性共識", ["假性共識"]),
    ("clarify", "需要釐清問題（既有分類）", ["需要釐清問題"]),
]
GENERAL = [
    ("time", "時間提醒", ["G01"]),
    ("help", "操作協助", ["G02"]),
    ("confirm", "成果確認", ["G05", "G06"]),
    ("flow", "流程說明", ["G03", "G07"]),
    ("other", "其他通用訊息", ["G04"]),
]
TYPE_LABELS = {"routine": "常態流程引導", "special": "特殊情境介入", "general": "通用訊息"}


def leaf_for(message):
    kind = message["intervention_type"]
    if kind == "routine" and message["cps_substage"] in STAGE_LABELS:
        return message["cps_substage"].split()[0]
    if kind in {"special", "general"}:
        return kind
    return "unmapped"


def navigation_tree(messages):
    phases = []
    for index, ((_, substages), label) in enumerate(zip(STAGES.items(), PHASE_LABELS)):
        phases.append({"id": f"phase:{index}", "label": label, "children": [
            {"id": sub.split()[0], "label": STAGE_LABELS[sub]} for sub in substages]})
    tree = [
        {"id": "routine", "label": TYPE_LABELS["routine"], "children": phases},
        {"id": "special", "label": TYPE_LABELS["special"]},
        {"id": "general", "label": TYPE_LABELS["general"]},
    ]
    if any(leaf_for(m) == "unmapped" for m in messages):
        tree.append({"id": "unmapped", "label": "待確認分類（保留原訊息）"})
    return tree


def breadcrumb(leaf, tree):
    for node in tree:
        if node["id"] == leaf:
            return node["label"]
        if "children" in node:
            found = breadcrumb(leaf, node["children"])
            if found:
                label = node["label"].split("（")[0] if node["id"].startswith("phase:") else node["label"]
                return f"{label} / {found}"
    return ""


def search_messages(messages, leaf, query="", all_library=False):
    query = query.strip().casefold()
    tree = navigation_tree(messages)
    return [m for m in messages if m["enabled"] and (all_library or leaf_for(m) == leaf)
            and query in " ".join([m["title"], m["content"], m["category"],
                                   " ".join(label for _, label, aliases in SPECIAL if m["category"] in aliases), TYPE_LABELS[m["intervention_type"]],
                                   STAGE_LABELS.get(m["cps_substage"], m["cps_substage"]), breadcrumb(leaf_for(m), tree)]).casefold()]
