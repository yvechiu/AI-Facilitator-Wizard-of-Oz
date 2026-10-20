"""Explicit host controls; browsing the message tree never calls this API."""
import streamlit as st
import sqlite3
from src.navigation import STAGE_LABELS
from src.phase_client import PhaseControlError


def render_phase_controls(service, channel):
    try:
        current = service.context(channel)
        pending = service.pending(channel)
    except (OSError, sqlite3.Error):
        st.error("無法保存或讀取階段狀態，請先檢查資料庫權限與磁碟空間。")
        return None, None
    except ValueError:
        st.warning("目前頻道不在階段控制設定的伺服器範圍，請核對 DISCORD_GUILD_ID。")
        return None, None
    st.caption(("Demo 摘要階段：" if service.demo_mode else "最後確認摘要階段：") + (current["phase_name"] or "尚未開始"))
    if pending:
        st.warning("階段同步未完成，請展開控制區重試原事件或查詢。")
    with st.popover("討論階段（摘要範圍）", use_container_width=True):
        if current["sequence"]:
            st.write("最後確認階段：" + current["phase_name"])
            st.caption(("Demo 本機模擬，未通知工具代理" if service.demo_mode else "工具代理最後確認時間（UTC）：") + ("" if service.demo_mode else current["checked_at"]))
        else:
            st.caption("尚未開始討論階段")
        if pending:
            st.warning("階段同步未完成：" + (pending["error_message"] or "事件已保存，尚未確認套用"))
            st.caption("待同步階段：" + pending["phase_name"])
        if not service.demo_mode and not service.client.configured():
            st.info("請在本機 .env 設定 TOOL_AGENT_CONTROL_URL、獨立的 PHASE_SYNC_TOKEN（至少 32 字元），並啟動工具代理控制 API。")
        choices = list(STAGE_LABELS.values())
        next_index = min(choices.index(current["phase_name"]) + 1, len(choices) - 1) if current["phase_name"] in choices else 0
        context_key = (service.guild_id, channel, service.demo_mode)
        suffix = f"{service.guild_id}:{channel}:{int(service.demo_mode)}"
        confirm_key = f"phase_confirm:{suffix}"
        choice_key = f"phase_choice:{suffix}"
        if pending:
            st.session_state[choice_key] = pending["phase_name"]
        choice = st.selectbox("要開始的討論階段", choices, index=next_index,
                              key=choice_key, disabled=bool(pending))
        intents = st.session_state.setdefault("phase_intents", {})
        if context_key not in intents or intents[context_key]["name"] != choice:
            intents[context_key] = {"name": choice, "event_id": None, "done": False}
            st.session_state[confirm_key] = False
        intent = intents[context_key]
        if pending:
            intent["event_id"] = pending["event_id"]
        if intent["event_id"] and not pending:
            resolved_status = service.event_status(intent["event_id"])
            if resolved_status in {"APPLIED", "DEMO", "SUPERSEDED"}:
                intent["done"] = True
                intent["superseded"] = resolved_status == "SUPERSEDED"
        if st.session_state.pop("phase_clear_confirm", False):
            st.session_state[confirm_key] = False
        confirmed = st.checkbox("我確認從成功同步後開始新階段，不回溯舊討論", key=confirm_key, disabled=bool(pending))
        configured = service.demo_mode or service.client.configured()
        action_label = "開始討論階段" if not current["sequence"] else "切換討論階段"
        if st.button(action_label, key="phase_apply", use_container_width=True,
                     disabled=not confirmed or not configured or bool(pending) or intent["done"]):
            try:
                if not intent["event_id"]:
                    event = service.prepare(channel, choice)
                    intent["event_id"] = event["event_id"]
                with st.spinner("正在同步階段，尚未成功前請勿開始新階段討論…"):
                    service.sync(intent["event_id"])
                intent["done"] = True
                st.session_state["phase_clear_confirm"] = True
                st.rerun()
            except PhaseControlError:
                st.rerun()  # Display the durable failed/unknown event and original-event retry.
            except Exception:
                st.error("階段操作未完整完成；請保留原事件，查詢目前階段或重試，不要另建事件。")
        if intent["done"]:
            if intent.get("superseded"):
                st.warning("原事件已被目前後續階段取代，未認定原事件成功；目前階段以上方確認狀態為準。")
            else:
                st.success("Demo 階段已模擬開始；未通知工具代理" if service.demo_mode else "事件同步已完成；目前階段以上方最後確認狀態為準")
            def prepare_again():
                intents[context_key] = {"name": choice, "event_id": None, "done": False}
                st.session_state[confirm_key] = False
            st.button("準備重新進入同名階段", key="phase_again", on_click=prepare_again,
                      help="只有再次進入同名階段時才使用；會建立新的階段 ID 與範圍。")
        if pending and st.button("重試原階段事件", key="phase_retry", disabled=not configured):
            try:
                with st.spinner("重試同一事件，不會重設已套用的階段起點…"):
                    service.sync(pending["event_id"])
                if intent["event_id"] == pending["event_id"]:
                    intent["done"] = True
                st.session_state["phase_clear_confirm"] = True
                st.rerun()
            except PhaseControlError as error:
                st.error(str(error))
            except Exception:
                st.error("重試未完整完成；事件已保留，請查詢目前階段。")
        if st.button("查詢工具代理目前階段", key="phase_refresh", disabled=not configured):
            try:
                with st.spinner("查詢目前階段，不進行切換…"):
                    service.refresh(channel)
                st.session_state["phase_clear_confirm"] = True
                st.rerun()
            except PhaseControlError as error:
                st.error(str(error))
            except Exception:
                st.error("查詢未完成，不能確認目前同步狀態。")
        st.caption("只有這裡的按鈕會開始／切換階段；訊息庫分類、摘要與計時器都不會切換。")
        with st.expander("同步資訊"):
            st.caption("實驗識別：" + current["experiment_id"])
            st.caption(f"已確認順序：{current['sequence']}；生效時間（UTC）：{current['effective_at'] or '—'}")
            if pending:
                st.caption("待處理事件：" + pending["event_id"])
        return service.context(channel), service.pending(channel)
