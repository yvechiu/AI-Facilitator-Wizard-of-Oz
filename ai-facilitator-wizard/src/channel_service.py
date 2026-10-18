import uuid
from src.database import utc_now


class ChannelService:
    def __init__(self, db, client, demo_mode=True):
        self.db, self.client, self.demo_mode = db, client, demo_mode

    def get(self, operation_id):
        rows = self.db.rows("SELECT * FROM channel_operations WHERE operation_id=?", (operation_id,))
        return rows[0] if rows else None

    def available(self):
        return self.db.rows("SELECT * FROM channel_operations WHERE demo_mode=? AND status IN ('SUCCESS','DEMO') ORDER BY timestamp_utc", (int(self.demo_mode),))

    def create(self, operation_id, guild_id, name):
        guild_id, name = guild_id.strip(), name.strip()
        if not guild_id.isascii() or not guild_id.isdigit() or not 17 <= len(guild_id) <= 20:
            raise ValueError("請輸入 17 至 20 位數的 Discord 伺服器 ID")
        if not name or len(name) > 100:
            raise ValueError("頻道名稱需為 1 至 100 字")
        token = getattr(self.client, "token", "")
        if token and token in name:
            raise ValueError("頻道名稱不得包含 Bot Token")
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM channel_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if previous:
                return dict(previous)
            db.execute("INSERT INTO channel_operations VALUES (?,?,?,?,?,NULL,'PENDING',NULL)",
                       (operation_id, utc_now(), guild_id, name, int(self.demo_mode)))
        if self.demo_mode:
            result = {"status": "DEMO", "channel_id": str(10**17 + uuid.uuid4().int % (9 * 10**17))}
        else:
            try:
                result = self.client.create_text_channel(guild_id, name)
            except Exception:
                result = {"status": "UNKNOWN", "error": "建立結果無法確認，請到 Discord 核對"}
        with self.db.connect() as db:
            db.execute("UPDATE channel_operations SET channel_id=?,status=?,error=? WHERE operation_id=?",
                       (result.get("channel_id"), result["status"], result.get("error"), operation_id))
        return self.get(operation_id)
