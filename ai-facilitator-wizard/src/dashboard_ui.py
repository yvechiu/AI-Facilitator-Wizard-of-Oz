"""Streamlit dashboard components using the existing session-state architecture."""
import re
import streamlit as st
from src.dashboard_state import select_message
from src.timers import initialize_timers, start_timer, stop_timer, elapsed, remaining, clock_text


def render_styles():
    st.markdown("""<style>
    .block-container {padding-top:1rem;padding-bottom:2rem;}
    div.st-key-experiment-status {border-bottom:1px solid #dce3e9;padding:0.2rem 0;}
    .st-key-experiment-status [data-testid="stVerticalBlock"] {gap:0.35rem;}
    .st-key-experiment-status [data-testid="stMetricValue"] {font-size:1.45rem;line-height:1.5;}
    [data-testid="stSidebar"] button {text-align:left;justify-content:flex-start;}
    [data-testid="stSidebar"] button[kind="primary"] {background:#e5eef5;color:#173c58;border:1px solid #93adc1;}
    [data-testid="stSidebar"] button[kind="secondary"] {border-color:transparent;background:transparent;}
    div[class*="st-key-message-card-"] button {
        width:100%;height:auto;min-height:8rem;padding:1.2rem;
        text-align:left;justify-content:flex-start;border:1px solid #d1d5db;
        border-radius:0.75rem;background:#fff;color:#173c58;
    }
    div[class*="st-key-message-card-"] button p {
        white-space:pre-wrap;overflow-wrap:anywhere;text-align:left;
    }
    div[class*="st-key-message-card-"] button:hover {border-color:#df9a32;background:#fffaf2;}
    div[class*="st-key-message-card-"] button:focus-visible {outline:2px solid #df9a32;outline-offset:3px;}
    div[class*="st-key-message-card-active-"] button {
        border:2px solid #e5a132;background:#fffaf2;
    }
    </style>""", unsafe_allow_html=True)


def start_stage_timer():
    duration = int(st.session_state["stage_minutes"]) * 60 + int(st.session_state["stage_seconds"])
    if duration > 0:
        start_timer(st.session_state["timers"], "stage", duration)


def render_status(channel_name, channel_id):
    with st.container(key="experiment-status"):
        render_timer_controls(channel_name, channel_id)


@st.fragment(run_every=1.0)
def render_timer_controls(channel_name, channel_id):
    initialize_timers(st.session_state)
    timers = st.session_state["timers"]
    overall, stage = timers["overall"], timers["stage"]
    total_column, stage_column, channel_column = st.columns([1.4, 1.6, 1.0])
    with total_column:
        st.caption("整場實驗碼表")
        clock, start, stop = st.columns([1.5, 1, 1])
        clock.metric("總經過時間", clock_text(elapsed(overall)), label_visibility="collapsed")
        start.button("開始", key="overall_start", disabled=overall["running"], use_container_width=True,
                     on_click=start_timer, args=(timers, "overall"))
        stop.button("結束", key="overall_stop", disabled=not overall["running"], use_container_width=True,
                    on_click=stop_timer, args=(timers, "overall"))
        st.caption("計時中" if overall["running"] else "已結束；再次開始會重新計時" if overall["ended_at"] is not None else "尚未開始")
    with stage_column:
        st.caption("階段倒數計時器")
        # Read settings before the controls, but render their popover in the compact footer.
        minutes = st.session_state.get("stage_minutes", 5)
        seconds = st.session_state.get("stage_seconds", 0)
        duration = int(minutes) * 60 + int(seconds)
        left = remaining(stage) if stage["started_at"] is not None else duration
        clock, start, stop = st.columns([1.5, 1, 1])
        clock.metric("階段剩餘時間", clock_text(left, round_up=True), label_visibility="collapsed")
        start.button("開始", key="stage_start", disabled=stage["running"] or duration <= 0, use_container_width=True,
                     on_click=start_stage_timer)
        stop.button("結束", key="stage_stop", disabled=not stage["running"], use_container_width=True,
                    on_click=stop_timer, args=(timers, "stage"))
        settings, status = st.columns([1.4, 2])
        with settings.popover("設定分秒", use_container_width=True):
            st.caption("設定下一次倒數時間；開始後須先按結束才能修改。")
            st.number_input("分鐘", min_value=0, max_value=9999, value=5, step=1,
                            key="stage_minutes", disabled=stage["running"])
            st.number_input("秒", min_value=0, max_value=59, value=0, step=1,
                            key="stage_seconds", disabled=stage["running"])
        if left <= 0 and stage["started_at"] is not None:
            status.caption(f"時間到 · 超時 {clock_text(-left)} · " + ("請按結束" if stage["running"] else "已結束"))
        else:
            status.caption("倒數中" if stage["running"] else "已結束" if stage["ended_at"] is not None else f"預設 {minutes} 分 {seconds} 秒")
    with channel_column:
        st.caption("Discord 目標頻道（連線未驗證）")
        st.write(channel_name)
        st.caption(channel_id)


def render_tree(tree):
    def toggle(node_id):
        expanded = st.session_state["navigation_state"]["expanded"]
        if node_id in expanded:
            expanded.remove(node_id)
        else:
            expanded.add(node_id)

    def select(leaf):
        st.session_state["navigation_state"]["selected"] = leaf
        st.session_state["confirm_send"] = False

    def nodes(items, depth=0):
        for node in items:
            navigation = st.session_state["navigation_state"]
            is_branch = "children" in node
            is_open = node["id"] in navigation["expanded"]
            prefix = ("▾ " if is_open else "▸ ") if is_branch else "• "
            display_label = node["label"].split("（")[0] if node["id"].startswith("phase:") else node["label"]
            st.button("　" * depth + prefix + display_label, key=f"tree:{node['id']}", help=node["label"],
                      type="primary" if node["id"] == navigation["selected"] else "secondary",
                      use_container_width=True, on_click=toggle if is_branch else select, args=(node["id"],))
            if is_branch and is_open:
                nodes(node["children"], depth + 1)

    st.subheader("訊息庫導覽")
    with st.container(height=500, border=False, key="navigation-tree"):
        nodes(tree)


def render_message_card(message, text, category, active=False):
    # Native button supplies keyboard access and callbacks; no HTML interpolation.
    def literal(value):
        return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", value)

    label = f"**{literal(message['title'])}**\n\n{literal(category)}\n\n{literal(text)}"
    state = "active" if active else "idle"
    with st.container(key=f"message-card-{state}-{message['message_id']}"):
        st.button(label, key=message["message_id"], use_container_width=True,
                  on_click=select_message, args=(st.session_state, message))
