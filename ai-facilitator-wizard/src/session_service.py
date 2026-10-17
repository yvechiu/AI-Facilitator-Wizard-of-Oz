import uuid
from src.database import utc_now


class SessionService:
    def __init__(self, db):
        self.db = db

    def create(self, name, study_phase, condition, channel_id, notes="", session_id=None):
        if not name.strip() or not channel_id.strip():
            raise ValueError("請輸入 Session 名稱及頻道")
        sid = session_id.strip() if session_id else str(uuid.uuid4())
        if not sid:
            raise ValueError("Session ID 不可空白")
        with self.db.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,NULL,?)", (sid, name, study_phase, condition, channel_id, notes))
        return sid

    def list(self):
        return self.db.rows("SELECT * FROM sessions ORDER BY rowid DESC")

    def get(self, sid):
        rows = self.db.rows("SELECT * FROM sessions WHERE session_id=?", (sid,))
        if not rows:
            raise ValueError("找不到 Session")
        return rows[0]

    def start(self, sid):
        with self.db.connect() as db:
            if db.execute("UPDATE sessions SET start_time=? WHERE session_id=? AND start_time IS NULL AND end_time IS NULL", (utc_now(), sid)).rowcount != 1:
                raise ValueError("Session 已開始、已結束或不存在")

    def end(self, sid):
        with self.db.connect() as db:
            if db.execute("UPDATE sessions SET end_time=? WHERE session_id=? AND start_time IS NOT NULL AND end_time IS NULL", (utc_now(), sid)).rowcount != 1:
                raise ValueError("Session 尚未開始、已結束或不存在")
