"""Browser-session drafts and operation identities; never mutate template records."""
import uuid
from src.message_service import template_fields, render_template


def initialize(state):
    state.setdefault("navigation_state", {"selected": "A-1", "expanded": {"routine", "phase:0"}})
    state.setdefault("experiment_state", {"stage": None, "status": "未開始", "remaining": None})
    state.setdefault("message_drafts", {})
    state.setdefault("message_operations", {})


def draft_for(state, message):
    return state["message_drafts"].setdefault(message["message_id"], {
        "text": message["content"], "fields": {field: "" for field in template_fields(message["content"])}})


def select_message(state, message):
    draft = draft_for(state, message)
    state["selected"] = message["message_id"]
    state["draft"] = draft["text"]
    for field, value in draft["fields"].items():
        state[f"field:{message['message_id']}:{field}"] = value
    state["confirm_send"] = False


def update_text(state, message):
    draft_for(state, message)["text"] = state["draft"]


def update_fields(state, message):
    draft = draft_for(state, message)
    draft["fields"] = {field: state.get(f"field:{message['message_id']}:{field}", "")
                       for field in template_fields(message["content"])}
    draft["text"] = render_template(message["content"], draft["fields"])
    state["draft"] = draft["text"]
    state["confirm_send"] = False


def operation_id(state, message_id, channel_id, demo_mode):
    key = (message_id, channel_id, demo_mode)
    return state["message_operations"].setdefault(key, str(uuid.uuid4()))


def new_operation(state, message_id, channel_id, demo_mode):
    state["message_operations"][(message_id, channel_id, demo_mode)] = str(uuid.uuid4())
    state["confirm_send"] = False
