import uuid
from datetime import datetime, timedelta, timezone
import sqlite3
import streamlit as st
from src.config import ROOT, load_config
from src.database import Database
from src.discord_client import DiscordClient
from src.session_service import SessionService
from src.logging_service import LoggingService
from src.message_service import STAGES, load_messages, filter_messages
from src.export_service import export_csv

st.set_page_config(page_title="AI 引導員 Wizard 控制台", layout="wide")
st.title("AI Facilitator · Wizard 控制台")
try:
    config = load_config()
    db = Database(config.database_path)
    templates = load_messages()
except Exception:
    st.error("設定、資料庫或訊息庫載入失敗。請依 README 檢查 .env、資料夾權限及 messages.json。")
    st.stop()
sessions = SessionService(db)
logger = LoggingService(db, DiscordClient(config.token), config.demo_mode)
st.info("DEMO 模式：只儲存模擬紀錄，絕不呼叫 Discord API。" if config.demo_mode else "正式模式：確認後將傳送至 Discord。")
if not config.demo_mode and not config.token:
    st.error("正式模式尚未設定 DISCORD_BOT_TOKEN；請在本機 .env 設定後重新啟動。")


def taiwan(value):
    return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S %z") if value else "—"


def safe_action(fn):
    try:
        fn()
        st.rerun()
    except (ValueError, sqlite3.Error):
        st.error("操作無法完成：請確認 Session 狀態、欄位、ID 是否重複及資料庫權限。")

with st.sidebar:
    st.header("實驗控制")
    existing_sessions = sessions.list()
    used_channels = {s["discord_channel_id"] for s in existing_sessions}
    available_channels = {name: cid for name, cid in config.channels.items() if cid not in used_channels}
    with st.expander("建立實驗場次（Session）"):
        if not available_channels:
            st.info("所有已設定頻道都已綁定場次。請選擇既有場次；新實驗請先在 .env 新增另一個文字頻道並重啟。")
        else:
            with st.form("create_session", clear_on_submit=True):
                new_channel_name = st.selectbox("新場次 Discord 頻道", list(available_channels))
                new_id = st.text_input("Session ID（留空自動產生）")
                name = st.text_input("實驗場次名稱")
                phase = st.text_input("研究階段", "正式實驗")
                condition = st.text_input("實驗條件", "Wizard of Oz")
                notes = st.text_area("Session 備註")
                if st.form_submit_button("建立"):
                    values = [new_id, name, phase, condition, notes]
                    if config.token and any(config.token in v for v in values):
                        st.error("欄位不得包含 Bot Token")
                    else:
                        def create_session():
                            st.session_state["selected_session"] = sessions.create(
                                name, phase, condition, available_channels[new_channel_name], notes, new_id or None)
                        safe_action(create_session)
    all_sessions = sessions.list()
    sid = st.selectbox("選擇實驗場次（Session）", [s["session_id"] for s in all_sessions], key="selected_session",
                       format_func=lambda x: next(f"{s['session_name']} · {x}" for s in all_sessions if s['session_id'] == x)) if all_sessions else None
    session = sessions.get(sid) if sid else None
    chosen_channel = session["discord_channel_id"] if session else None
    channel_name = next((name for name, cid in config.channels.items() if cid == chosen_channel), "未設定頻道")
    channel_configured = chosen_channel in config.channels.values()
    if session:
        st.write(f"綁定頻道：{channel_name}（{chosen_channel}）")
        if not channel_configured:
            st.warning("此場次的頻道不在 .env 設定中，請補回原頻道 ID 並重啟，才能繼續發送。")
        if sum(s["discord_channel_id"] == chosen_channel for s in all_sessions) > 1:
            st.warning("舊資料有多個場次共用此頻道，紀錄已保留。請核對所選場次；新場次不再允許重複綁定。")
        st.caption(f"開始（台灣）：{taiwan(session['start_time'])}\n結束：{taiwan(session['end_time'])}")
        if st.button("開始 Session", disabled=bool(session["start_time"])):
            safe_action(lambda: sessions.start(sid))
        if st.button("結束 Session", disabled=not session["start_time"] or bool(session["end_time"])):
            safe_action(lambda: sessions.end(sid))
    stage_choice = st.selectbox("CPS 階段", ["全部", *STAGES])
    stage = None if stage_choice == "全部" else stage_choice
    substages = STAGES[stage] if stage else [s for items in STAGES.values() for s in items]
    sub_choice = st.selectbox("CPS 子階段", ["全部", *substages])
    kind = st.selectbox("介入類型", ["全部", "routine", "special"], format_func=lambda x: {"全部":"全部", "routine":"常態流程", "special":"特殊介入"}[x])
    query = st.text_input("訊息搜尋")

browse, preview = st.columns([1, 1])
with browse:
    st.subheader("預設訊息")
    matches = filter_messages(templates, stage, None if sub_choice == "全部" else sub_choice, None if kind == "全部" else kind, query)
    st.caption(f"找到 {len(matches)} 則啟用模板")
    for m in matches:
        with st.container(border=True):
            st.markdown(f"**{m['title']}** · {m['category']}")
            st.caption(f"{m['cps_substage']}｜{m['trigger_condition']}")
            if st.button("選用／重新載入", key=m["message_id"]):
                st.session_state["selected"] = m["message_id"]
                st.session_state["draft"] = m["content"]
                st.session_state["operation_id"] = str(uuid.uuid4())
                st.session_state["confirm_send"] = False
                st.session_state.pop("confirm_context", None)
with preview:
    st.subheader("預覽與發送")
    selected = next((m for m in templates if m["message_id"] == st.session_state.get("selected")), None)
    if not selected:
        st.write("請先從左方選用訊息。")
    else:
        st.markdown(f"**{selected['title']}** · 版本 {selected['template_version']}")
        st.write("可觀察徵象：", selected["observable_indicators"])
        st.caption("Wizard 備註：" + selected["wizard_notes"])
        text = st.text_area("發送內容（可編輯）", key="draft", height=180)
        send_notes = st.text_input("本次操作備註")
        st.write(f"目標：{channel_name}（{chosen_channel}）")
        st.caption(f"原始模板：{selected['content']}")
        opid = st.session_state["operation_id"]
        previous = logger.get_operation(opid)
        context = (sid, chosen_channel, text, send_notes, config.demo_mode)
        if st.session_state.get("confirm_context") != context:
            st.session_state["confirm_send"] = False
            st.session_state["confirm_context"] = context
        confirmed = st.checkbox("我已確認 Session、目標頻道及訊息內容", key="confirm_send")
        valid = bool(session and session["start_time"] and not session["end_time"] and channel_configured)
        if not valid:
            st.warning("請先建立並開始實驗場次，並確認其綁定頻道仍在 .env 設定中。")
        if st.button("確認模擬發送" if config.demo_mode else "確認發送 Discord", type="primary", disabled=not confirmed or not valid or previous is not None):
            try:
                result = logger.send(opid, sid, selected, text, chosen_channel, send_notes)
                st.rerun()
            except Exception:
                st.error("操作未完整完成。請查詢下方紀錄；若為 PENDING 或 UNKNOWN，請先人工核對 Discord，勿直接重送。")
        if previous:
            status = previous["send_status"]
            if status in {"SUCCESS", "DEMO"}:
                st.success(f"{status} · Discord Message ID：{previous['discord_message_id'] or '—'}")
            else:
                st.warning(f"{status}：{previous['error_message'] or '尚未確認，可能於送出期間中斷，請人工核對'}")
            def next_operation():
                st.session_state["operation_id"] = str(uuid.uuid4())
                st.session_state["confirm_send"] = False
            st.button("準備下一次操作（必要時先核對 Discord）", on_click=next_operation)

if session:
    st.divider()
    st.subheader("Wizard 觀察紀錄")
    with st.form("observation", clear_on_submit=True):
        obs_stage = st.selectbox("觀察 CPS 階段", list(STAGES))
        problem = st.text_input("觀察到的互動問題")
        intervened = st.checkbox("已介入")
        reason = st.text_input("未介入原因（未勾選時必填）")
        obs_notes = st.text_area("自由備註")
        if st.form_submit_button("儲存觀察"):
            safe_action(lambda: logger.observe(sid, obs_stage, problem, intervened, reason, obs_notes))
    st.subheader("本 Session 紀錄與匯出")
    rows = db.rows("SELECT * FROM operations WHERE session_id=? ORDER BY timestamp_utc DESC", (sid,))
    st.dataframe([{**r, "台灣時間": taiwan(r["timestamp_utc"])} for r in rows], use_container_width=True)
    if any(r["send_status"] in {"PENDING", "UNKNOWN"} for r in rows):
        st.warning("存在 PENDING／UNKNOWN：可能已送達，請人工核對 Discord；系統不會自動重試。")
    for table, label in [("operations", "發送紀錄"), ("observations", "觀察紀錄"), ("sessions", "Session 基本資料")]:
        st.download_button(f"匯出 {label} CSV", export_csv(db, table, sid), file_name=f"{table}.csv", mime="text/csv")

with st.expander("資料庫維護"):
    st.caption(f"本地資料庫：{config.database_path}")
    if st.button("檢查資料完整性"):
        if db.integrity_check():
            st.success("SQLite 完整性檢查通過")
        else:
            st.error("資料完整性檢查失敗，請保留原檔並還原備份")
    if st.button("建立本地備份"):
        try:
            destination = ROOT / "backups" / f"experiments-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3"
            db.backup(destination)
            st.success(f"已備份至 {destination}")
        except Exception:
            st.error("備份失敗，請檢查空間與寫入權限")
