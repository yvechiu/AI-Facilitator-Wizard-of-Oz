"""Explicit library editing, separate from sending a draft to Discord."""
import sqlite3
import streamlit as st
from src.dashboard_state import select_message
from src.navigation import TYPE_LABELS, STAGE_LABELS, leaf_for


def show_library_notice():
    notice = st.session_state.pop('library_notice', None)
    if notice:
        getattr(st, notice[0])(notice[1])


def render_create(service):
    with st.popover('新增訊息'):
        with st.form('create_library_message', clear_on_submit=True):
            title = st.text_input('新增訊息標題')
            kind = st.selectbox('訊息分類', list(TYPE_LABELS), format_func=TYPE_LABELS.get)
            stage = st.selectbox('CPS 子階段（僅常態流程使用）', list(STAGE_LABELS), format_func=STAGE_LABELS.get)
            content = st.text_area('新增訊息內容', help='可使用〈欄位名稱〉建立發送前填寫的欄位。')
            submitted = st.form_submit_button('加入訊息庫')
        if submitted:
            try:
                message = service.create(title, content, kind, stage)
                st.session_state['navigation_state']['selected'] = leaf_for(message)
                st.session_state['message_search'] = ''
                st.session_state['search_all'] = False
                select_message(st.session_state, message)
                st.session_state['library_notice'] = ('success', '已新增至訊息庫。')
                st.rerun()
            except (ValueError, sqlite3.Error) as error:
                st.error(str(error) if isinstance(error, ValueError) else '儲存失敗，請檢查資料庫權限。')


def _change(service, selected, delete=False):
    try:
        if delete and not st.session_state.get('delete:' + selected['message_id']):
            return
        updated = service.change(selected, st.session_state.get('title:' + selected['message_id'], ''),
                                 st.session_state.get('draft', ''), delete)
        st.session_state['message_drafts'].pop(selected['message_id'], None)
        st.session_state['confirm_send'] = False
        st.session_state['delete:' + selected['message_id']] = False
        if updated:
            select_message(st.session_state, updated)
        else:
            st.session_state.pop('selected', None)
            st.session_state.pop('draft', None)
        st.session_state['library_notice'] = ('success', '已從訊息庫刪除。' if delete else '已更新訊息庫，舊內容已取代。')
    except (ValueError, sqlite3.Error) as error:
        st.session_state['library_notice'] = ('error', str(error) if isinstance(error, ValueError) else '儲存失敗，請檢查資料庫權限。')


def render_library_actions(service, selected):
    with st.expander('管理此訊息'):
        st.text_input('訊息標題', value=selected['title'], key='title:' + selected['message_id'])
        st.caption('儲存會以目前「發送內容」取代模板；已填入的欄位值也會存為固定文字。只要暫時修改發送內容時，不必儲存。')
        st.button('儲存至訊息庫（取代舊內容）', on_click=_change, args=(service, selected))
        confirmed = st.checkbox('確定從訊息庫刪除此訊息', key='delete:' + selected['message_id'])
        st.button('刪除訊息', disabled=not confirmed, on_click=_change, args=(service, selected, True))
        st.caption('變更會保存在本機資料庫，重新啟動後仍有效；既有發送紀錄不受影響。')
