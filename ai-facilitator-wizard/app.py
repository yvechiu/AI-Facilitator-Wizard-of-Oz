import uuid
from datetime import datetime, timedelta, timezone
import sqlite3
import streamlit as st
from src.config import ROOT, load_config
from src.channel_service import ChannelService
from src.database import Database
from src.discord_client import DiscordClient
from src.logging_service import LoggingService
from src.message_service import STAGES, load_messages, filter_messages, template_fields, render_template, has_placeholders
from src.export_service import export_channel_csv, channel_records

st.set_page_config(page_title="AI 引導員 Wizard 控制台", layout="wide")
st.markdown("""<style>
.block-container {padding-top:2rem;padding-bottom:2rem;}
@media (min-width: 900px) and (min-height: 800px) {
    div[data-testid="stColumn"]:has(.st-key-wizard-preview-panel) {
        position: sticky; top: 3.5rem; align-self: flex-start;
    }
}
</style>""", unsafe_allow_html=True)
st.title("AI Facilitator · Wizard 控制台")
st.caption("選擇情境 → 選用訊息 → 預覽確認")
try:
    config = load_config()
    db = Database(config.database_path)
    templates = load_messages()
except Exception:
    st.error("設定、資料庫或訊息庫載入失敗。請依 README 檢查 .env、資料夾權限及 messages.json。")
    st.stop()
logger = LoggingService(db, DiscordClient(config.token), config.demo_mode)
channel_service = ChannelService(db, DiscordClient(config.token), config.demo_mode)
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
        st.error("操作無法完成：請確認欄位內容及資料庫權限。")

with st.sidebar:
    st.header("實驗控制")
    with st.expander("在 Discord 新增文字頻道"):
        st.caption("Bot 須先加入伺服器，並具備管理頻道、管理角色、檢視頻道及傳送訊息權限。建立時會為 Bot 設定檢視與發送權限；不會讀取參與者對話。")
        guild_id = st.text_input("Discord 伺服器 ID")
        new_channel_name = st.text_input("新增文字頻道名稱", placeholder="實驗-第一組")
        st.caption("Demo 只建立本機模擬頻道；正式模式會真正新增 Discord 頻道。參與者存取沿用伺服器預設權限，請在 Discord 核對。")
        create_context = (guild_id, new_channel_name, config.demo_mode)
        if st.session_state.get("channel_create_context") != create_context:
            st.session_state["channel_create_confirm"] = False
            st.session_state["channel_create_context"] = create_context
        create_confirmed = st.checkbox("我已確認伺服器及頻道名稱", key="channel_create_confirm")
        if "channel_operation_id" not in st.session_state:
            st.session_state["channel_operation_id"] = str(uuid.uuid4())
        channel_opid = st.session_state["channel_operation_id"]
        channel_result = channel_service.get(channel_opid)
        if st.button("模擬建立頻道" if config.demo_mode else "確認建立 Discord 文字頻道",
                     disabled=not create_confirmed or channel_result is not None):
            try:
                created = channel_service.create(channel_opid, guild_id, new_channel_name)
                if created["status"] in {"SUCCESS", "DEMO"}:
                    st.session_state["target_channel"] = created["channel_id"]
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except Exception:
                st.error("建立操作未完整完成，請先核對 Discord 頻道清單及操作狀態，勿直接重建。")
        if channel_result:
            if channel_result["status"] in {"SUCCESS", "DEMO"}:
                st.success(f"{channel_result['status']}：{channel_result['channel_name']}（{channel_result['channel_id']}）")
            else:
                st.warning(f"{channel_result['status']}：{channel_result['error'] or '結果尚未確認，請至 Discord 核對後再操作'}")
            def next_channel_operation():
                st.session_state["channel_operation_id"] = str(uuid.uuid4())
                st.session_state["channel_create_confirm"] = False
            st.button("準備建立另一個頻道（先核對上次結果）", on_click=next_channel_operation)
    channel_options = {cid: name for name, cid in config.channels.items()}
    for created_channel in channel_service.available():
        channel_options[created_channel["channel_id"]] = created_channel["channel_name"]
    if st.session_state.get("target_channel") not in channel_options:
        st.session_state["target_channel"] = next(iter(channel_options))
    chosen_channel = st.selectbox("目標 Discord 頻道", list(channel_options), key="target_channel",
                                  format_func=lambda cid: f"{channel_options[cid]}（{cid}）")
    channel_name = channel_options[chosen_channel]
    st.caption(f"頻道 ID：{chosen_channel}")

# Buttons retain navigation values independently of widget cleanup when switching sections.
for key, default in {"nav_group": "routine", "nav_stage": "Understanding the Challenge",
                     "nav_substage": STAGES["Understanding the Challenge"][0], "nav_special": "討論停滯"}.items():
    st.session_state.setdefault(key, default)


def navigate(key, value):
    st.session_state[key] = value
    st.session_state.pop("selected", None)
    st.session_state["confirm_send"] = False
    st.session_state["message_search"] = ""


def nav_buttons(options, state_key):
    for start in range(0, len(options), 3):
        row = options[start:start + 3]
        columns = st.columns(len(row))
        for column, (value, label) in zip(columns, row):
            column.button(label, key=f"{state_key}:{value}", use_container_width=True,
                          type="primary" if st.session_state[state_key] == value else "secondary",
                          on_click=navigate, args=(state_key, value))


nav_buttons([("routine", "常態流程引導"), ("special", "特殊情境介入"), ("general", "通用訊息")], "nav_group")
labels = {"Understanding the Challenge": "理解挑戰", "Generating Ideas": "產生點子", "Preparing for Action": "行動準備"}
sub_labels = dict(zip([sub for items in STAGES.values() for sub in items],
                     ["A-1 建構機會", "A-2 探索資料", "A-3 陳述問題", "B-1 產生點子", "C-1 發展解決方案"]))
group = st.session_state["nav_group"]
if group == "routine":
    nav_buttons(list(labels.items()), "nav_stage")
    stage = st.session_state["nav_stage"]
    if len(STAGES[stage]) > 1:
        nav_buttons([(sub, sub_labels[sub]) for sub in STAGES[stage]], "nav_substage")
        substage = st.session_state["nav_substage"]
    else:
        substage = STAGES[stage][0]
    matches = filter_messages(templates, stage=stage, substage=substage, intervention="routine")
    location = f"常態流程引導 / {labels[stage]} / {sub_labels[substage]}"
elif group == "special":
    categories = list(dict.fromkeys(m["category"] for m in templates if m["intervention_type"] == "special" and m["enabled"]))
    if categories and st.session_state["nav_special"] not in categories:
        st.session_state["nav_special"] = categories[0]
    if categories:
        nav_buttons([(category, category) for category in categories], "nav_special")
    matches = [m for m in filter_messages(templates, intervention="special") if m["category"] == st.session_state["nav_special"]]
    location = f"特殊情境介入 / {st.session_state['nav_special']}"
else:
    matches = filter_messages(templates, intervention="general")
    location = "通用訊息 / 跨階段使用"

with st.expander("找不到訊息？跨分類搜尋"):
    query = st.text_input("搜尋所有訊息", key="message_search", placeholder="輸入內容、情境或標題")
if query.strip():
    matches = filter_messages(templates, query=query.strip())
    location = "跨分類搜尋結果"
st.caption(f"{location} · {len(matches)} 則訊息")
browse, preview = st.columns([1.15, 1], gap="large")
with browse:
    st.subheader("選用訊息")
    if not matches:
        st.info("此分類或搜尋沒有符合的訊息。")
    for m in matches:
        with st.container(border=True):
            st.markdown(f"**{m['title']}**")
            st.caption("使用時機：" + m["trigger_condition"])
            if query.strip():
                st.caption({"routine": "常態流程引導", "special": "特殊情境介入", "general": "通用訊息"}[m["intervention_type"]] + " / " + m["category"])
            st.write(m["content"])
            if st.button("選用／重新載入", key=m["message_id"], use_container_width=True):
                st.session_state["selected"] = m["message_id"]
                st.session_state["draft"] = m["content"]
                st.session_state["operation_id"] = str(uuid.uuid4())
                st.session_state["confirm_send"] = False
                st.session_state.pop("confirm_context", None)
                st.session_state.pop("field_signature", None)
with preview, st.container(key="wizard-preview-panel"):
    st.subheader("預覽與發送")
    selected = next((m for m in templates if m["message_id"] == st.session_state.get("selected")), None)
    if not selected:
        st.write("請先從左方選用訊息。")
    else:
        st.markdown(f"**{selected['title']}**")
        fields = template_fields(selected["content"])
        values = {}
        if fields:
            st.caption("填寫欄位後自動產生訊息；再次變更欄位會重新產生內容，請最後再手動微調。")
        for field in fields:
            values[field] = st.text_input(field, key=f"field:{selected['message_id']}:{field}")
            if field in {"成果要求", "操作說明"}:
                st.caption("請直接引用原階段腳本，不臨場增加要求。")
            elif field == "目前提出的成果":
                st.caption("請引用成員明確提出的內容，不自行整合成新結論。")
        signature = (selected["message_id"], tuple(values.items()))
        if st.session_state.get("field_signature") != signature:
            st.session_state["draft"] = render_template(selected["content"], values)
            st.session_state["field_signature"] = signature
        with st.expander("使用說明與模板資訊"):
            st.write(selected["observable_indicators"])
            st.write(selected["wizard_notes"])
            st.caption(f"{selected['message_id']} · 版本 {selected['template_version']} · {selected['cps_substage']}")
        if selected["message_id"] == "G04":
            st.info("＠工具代理僅為文字，不會通知或啟動另一隻 Bot。")
        text = st.text_area("發送內容（可編輯）", key="draft", height=180)
        send_notes = st.text_input("本次操作備註")
        st.write(f"目標：{channel_name}（{chosen_channel}）")
        ready = all(value.strip() for value in values.values()) and not has_placeholders(text)
        ready = ready and bool(text.strip()) and len(text.encode("utf-16-le")) // 2 <= 2000
        if not ready:
            st.warning("請填妥所有模板欄位，移除〈佔位文字〉，並確認內容不空白且在 2000 字元限制內。")
        target = (chosen_channel, config.demo_mode)
        if st.session_state.get("operation_target") != target:
            st.session_state["operation_id"] = str(uuid.uuid4())
            st.session_state["operation_target"] = target
            st.session_state["confirm_send"] = False
        opid = st.session_state["operation_id"]
        previous = logger.get_operation(opid)
        context = (chosen_channel, text, send_notes, config.demo_mode)
        if st.session_state.get("confirm_context") != context:
            st.session_state["confirm_send"] = False
            st.session_state["confirm_context"] = context
        confirmed = st.checkbox("我已確認目標頻道及訊息內容", key="confirm_send")
        if st.button("確認模擬發送" if config.demo_mode else "確認發送 Discord", type="primary", disabled=not confirmed or not ready or previous is not None):
            try:
                result = logger.send_to_channel(opid, chosen_channel, selected, text, send_notes)
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

with st.expander("Wizard 觀察紀錄與本頻道匯出"):
    st.subheader("Wizard 觀察紀錄")
    with st.form("observation", clear_on_submit=True):
        obs_stage = st.selectbox("觀察 CPS 階段", list(STAGES))
        problem = st.text_input("觀察到的互動問題")
        intervened = st.checkbox("已介入")
        reason = st.text_input("未介入原因（未勾選時必填）")
        obs_notes = st.text_area("自由備註")
        if st.form_submit_button("儲存觀察"):
            safe_action(lambda: logger.observe_channel(chosen_channel, obs_stage, problem, intervened, reason, obs_notes))
    st.subheader("本頻道紀錄與匯出")
    rows = channel_records(db, "operations", chosen_channel)
    st.dataframe([{**r, "台灣時間": taiwan(r["timestamp_utc"])} for r in rows], use_container_width=True)
    if any(r["send_status"] in {"PENDING", "UNKNOWN"} for r in rows):
        st.warning("存在 PENDING／UNKNOWN：可能已送達，請人工核對 Discord；系統不會自動重試。")
    for table, label in [("operations", "發送紀錄"), ("observations", "觀察紀錄")]:
        st.download_button(f"匯出 {label} CSV", export_channel_csv(db, table, chosen_channel), file_name=f"{chosen_channel}-{table}.csv", mime="text/csv")

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
