"""Local persistent library overrides; shipped JSON and operation history stay intact."""
import json
import uuid
from src.message_service import load_messages, validate_messages


class LibraryService:
    def __init__(self, database):
        self.db = database
        self.base = load_messages()

    def _load(self, connection):
        messages = {m['message_id']: m for m in self.base}
        for row in connection.execute('SELECT * FROM message_library'):
            if row['deleted']:
                messages.pop(row['message_id'], None)
            else:
                messages[row['message_id']] = json.loads(row['payload'])
        return validate_messages(list(messages.values()))

    def load(self):
        with self.db.connect() as connection:
            return self._load(connection)

    def create(self, title, content, kind, stage=None):
        from src.message_service import STAGES
        group = next((group for group, stages in STAGES.items() if stage in stages), None)
        if kind == 'routine' and group is None:
            raise ValueError('請選擇有效的 CPS 子階段')
        message = dict(message_id='U' + uuid.uuid4().hex[:12].upper(), title=title.strip(),
                       content=content.strip(), intervention_type=kind,
                       cps_stage=group if kind == 'routine' else '跨階段',
                       cps_substage=stage if kind == 'routine' else '特殊情境' if kind == 'special' else '通用訊息',
                       category={'routine': '常態流程', 'special': '特殊情境', 'general': '通用訊息'}.get(kind, kind),
                       trigger_condition='研究者自行選用', observable_indicators='研究者自行判斷',
                       wizard_notes='研究者新增模板', enabled=True, template_version='1')
        validate_messages([message])
        with self.db.connect() as connection:
            connection.execute('INSERT INTO message_library(message_id,payload) VALUES (?,?)',
                               (message['message_id'], json.dumps(message, ensure_ascii=False)))
        return message

    def change(self, original, title=None, content=None, delete=False):
        with self.db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            current = next((m for m in self._load(connection) if m['message_id'] == original['message_id']), None)
            if current != original:
                raise ValueError('訊息已被其他操作更新或刪除，請重新選取最新訊息後再操作。')
            updated = None
            if not delete:
                updated = {**current, 'title': title.strip(), 'content': content.strip(),
                           'template_version': str(uuid.uuid4())}
                validate_messages([updated])
            connection.execute('INSERT INTO message_library(message_id,payload,deleted) VALUES (?,?,?) '
                               'ON CONFLICT(message_id) DO UPDATE SET payload=excluded.payload,deleted=excluded.deleted',
                               (original['message_id'], json.dumps(updated, ensure_ascii=False) if updated else None, int(delete)))
        return updated
