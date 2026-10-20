import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.library_service import LibraryService
from src.database import Database


def test_library_persistence_replace_delete_and_conflict(db):
    library = LibraryService(db)
    original = library.load()[0]
    updated = library.change(original, '正式標題', '新內容\n保留換行')
    assert updated['message_id'] == original['message_id']
    assert updated['template_version'] != original['template_version']
    assert LibraryService(db).load()[0] == updated
    with pytest.raises(ValueError, match='其他操作'):
        library.change(original, '過期操作', '不得覆蓋')
    library.change(updated, delete=True)
    assert original['message_id'] not in {m['message_id'] for m in LibraryService(db).load()}
    assert db.rows('SELECT * FROM operations') == []
    created = library.create('新增通用訊息', '本階段剩下〈分鐘〉分鐘', 'general')
    assert created in LibraryService(db).load()
    with pytest.raises(ValueError):
        library.change(created, '', '空標題不可儲存')
    assert created in library.load()
    for message in library.load():
        library.change(message, delete=True)
    assert LibraryService(db).load() == []
    assert library.create('重建', '內容', 'special') in library.load()


def test_ui_create_save_delete_without_sending(tmp_path, monkeypatch):
    dbpath = tmp_path / 'library-ui.sqlite3'
    monkeypatch.setenv('DATABASE_PATH', str(dbpath))
    monkeypatch.setenv('DEMO_MODE', 'true')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=15).run()
    def label(elements, name):
        return next(e for e in elements if e.label == name)
    label(app.text_input, '新增訊息標題').set_value('實驗新訊息')
    label(app.selectbox, '訊息分類').select('general')
    label(app.text_area, '新增訊息內容').set_value('新增內容')
    label(app.button, '加入訊息庫').click().run()
    assert not app.exception
    message_id = app.session_state['selected']
    assert app.session_state['navigation_state']['selected'] == 'general'
    assert app.text_area(key='draft').value == '新增內容'
    app.text_area(key='draft').set_value('編輯後的內容').run()
    label(app.button, '儲存至訊息庫（取代舊內容）').click().run()
    assert not app.exception
    library = LibraryService(Database(dbpath))
    saved = next(m for m in library.load() if m['message_id'] == message_id)
    assert saved['content'] == '編輯後的內容'
    assert '編輯後的內容' in app.button(key=message_id).label
    assert label(app.button, '刪除訊息').disabled
    app.checkbox(key='delete:' + message_id).check().run()
    label(app.button, '刪除訊息').click().run()
    assert not app.exception
    assert message_id not in {m['message_id'] for m in library.load()}
    assert Database(dbpath).rows('SELECT * FROM operations') == []
    app.run()
    assert not any(b.key == message_id for b in app.button)
