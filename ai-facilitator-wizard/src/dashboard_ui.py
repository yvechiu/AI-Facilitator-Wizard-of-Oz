"""Streamlit dashboard components using the existing session-state architecture."""
import streamlit as st
from src.navigation import STAGE_LABELS


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


def render_status(experiment, channel_name, channel_id):
    with st.container(key="experiment-status"):
        columns = st.columns([1.3, 0.8, 0.9, 1.5])
        stage = experiment.get("stage")
        label = next((label for label in STAGE_LABELS.values() if label.split()[0] == stage), stage)
        columns[0].caption("目前實驗階段")
        columns[0].write(label or "尚未設定")
        columns[1].caption("實驗狀態")
        columns[1].write(experiment.get("status", "未開始"))
        columns[2].caption("階段剩餘時間")
        remaining = experiment.get("remaining")
        columns[2].write(remaining if remaining is not None else "—（尚無計時功能）")
        columns[3].caption("Discord 目標頻道（連線未驗證）")
        columns[3].write(channel_name)
        columns[3].caption(channel_id)
    st.caption("實驗階段／狀態為預留顯示位置；目前未啟用管理或計時功能。瀏覽訊息不會變更實驗狀態。")


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
