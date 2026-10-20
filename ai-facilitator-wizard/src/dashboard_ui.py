"""Streamlit dashboard components using the existing session-state architecture."""
import streamlit as st
from src.timers import initialize_timers, start_timer, stop_timer, elapsed, remaining, clock_text


def render_styles():
    st.markdown("""<style>
    .block-container {padding-top:1rem;padding-bottom:2rem;}
    div[data-testid="stLayoutWrapper"]:has(> .st-key-experiment-status) {
        position:sticky;top:3.5rem;z-index:90;background:var(--background-color,#fff);
    }
    div.st-key-experiment-status {border-bottom:1px solid #dce3e9;padding:0.4rem 0;}
    [data-testid="stSidebar"] button {text-align:left;justify-content:flex-start;}
    [data-testid="stSidebar"] button[kind="primary"] {background:#e5eef5;color:#173c58;border:1px solid #93adc1;}
    [data-testid="stSidebar"] button[kind="secondary"] {border-color:transparent;background:transparent;}
    div[data-testid="stCode"] pre {white-space:pre-wrap;}
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
    total_column, stage_column, channel_column = st.columns([1.1, 1.7, 1.2])
    with total_column:
        st.caption("整場實驗碼表")
        st.metric("總經過時間", clock_text(elapsed(overall)), label_visibility="collapsed")
        start, stop = st.columns(2)
        start.button("開始", key="overall_start", disabled=overall["running"], use_container_width=True,
                     on_click=start_timer, args=(timers, "overall"))
        stop.button("結束", key="overall_stop", disabled=not overall["running"], use_container_width=True,
                    on_click=stop_timer, args=(timers, "overall"))
        st.caption("計時中" if overall["running"] else "已結束；再次開始會從零計時" if overall["ended_at"] is not None else "按開始後才會計時")
    with stage_column:
        st.caption("階段倒數計時器")
        minute_column, second_column = st.columns(2)
        minutes = minute_column.number_input("分鐘", min_value=0, max_value=9999, value=5, step=1,
                                             key="stage_minutes", disabled=stage["running"])
        seconds = second_column.number_input("秒", min_value=0, max_value=59, value=0, step=1,
                                              key="stage_seconds", disabled=stage["running"])
        duration = int(minutes) * 60 + int(seconds)
        left = remaining(stage) if stage["started_at"] is not None else duration
        st.metric("階段剩餘時間", clock_text(left, round_up=True), label_visibility="collapsed")
        start, stop = st.columns(2)
        start.button("開始", key="stage_start", disabled=stage["running"] or duration <= 0, use_container_width=True,
                     on_click=start_stage_timer)
        stop.button("結束", key="stage_stop", disabled=not stage["running"], use_container_width=True,
                    on_click=stop_timer, args=(timers, "stage"))
        if left <= 0 and stage["started_at"] is not None:
            st.caption(f"時間到 · 超時 {clock_text(-left)} · " + ("請按結束停止" if stage["running"] else "已結束"))
        else:
            st.caption("倒數中；按結束停止" if stage["running"] else "已結束；可設定下一次時間再開始" if stage["ended_at"] is not None else "輸入分、秒後按開始")
    with channel_column:
        st.caption("Discord 目標頻道（連線未驗證）")
        st.write(channel_name)
        st.caption(channel_id)
        st.caption("兩個計時器各自控制，不受訊息分類或頻道切換影響。")


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


def render_copy(text):
    # Streamlit's code block has a native clipboard button; text never enters executable HTML/JS.
    st.caption("按右上角複製圖示，複製下方完整文字。")
    st.code(text, language=None, wrap_lines=True)
