import uuid
from src.database import utc_now
from src.discord_client import SendResult


class LoggingService:
    def __init__(self, db, client, demo_mode=True):
        self.db, self.client, self.demo_mode = db, client, demo_mode

    def get_operation(self, operation_id):
        rows = self.db.rows("SELECT * FROM operations WHERE operation_id=?", (operation_id,))
        return rows[0] if rows else None

    def send(self, operation_id, session_id, template, text, channel_id, notes=""):
        if not text.strip() or len(text.encode("utf-16-le")) // 2 > 2000:
            raise ValueError("訊息不可空白，且不可超過 2000 個 UTF-16 字元")
        token = getattr(self.client, "token", "")
        if token and any(token in value for value in [text, template["content"], notes]):
            raise ValueError("內容含有 Bot Token，已禁止儲存與發送")
        # BEGIN IMMEDIATE + PRIMARY KEY prevents concurrent duplicate calls, even across processes.
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if existing:
                return dict(existing)
            session = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if not session or not session["start_time"] or session["end_time"]:
                raise ValueError("請先開始 Session；已結束的 Session 不可發送")
            if session["discord_channel_id"] != channel_id:
                raise ValueError("目標頻道與 Session 不符，請建立另一個 Session")
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                operation_id, session_id, utc_now(), template["message_id"], template["template_version"],
                template["cps_stage"], template["cps_substage"], template["intervention_type"],
                template["content"], text, int(text != template["content"]), channel_id, None, "PENDING", None, notes))
        # PENDING is committed before any external side effect. No automatic retry.
        if self.demo_mode:
            result = SendResult("DEMO")
        else:
            try:
                result = self.client.send(channel_id, text, operation_id)
            except Exception:
                result = SendResult("UNKNOWN", error="發送發生非預期錯誤，請至 Discord 核對；禁止直接重試")
        with self.db.connect() as db:
            db.execute("UPDATE operations SET send_status=?, discord_message_id=?, error_message=? WHERE operation_id=?",
                       (result.status, result.message_id, result.error.replace(token, "[REDACTED]") if token and result.error else result.error, operation_id))
        return self.get_operation(operation_id)

    def observe(self, session_id, stage, problem, intervened, reason="", notes=""):
        token = getattr(self.client, "token", "")
        if token and any(token in v for v in [problem, reason, notes]):
            raise ValueError("觀察內容含有 Bot Token")
        if not problem.strip() or (not intervened and not reason.strip()):
            raise ValueError("請輸入觀察問題；未介入時請填寫原因")
        with self.db.connect() as db:
            db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?)", (
                str(uuid.uuid4()), session_id, utc_now(), stage, problem, int(intervened), reason, notes))
