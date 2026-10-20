"""Durable channel/experiment bindings and an idempotent phase outbox."""
import json
import uuid
from src.database import utc_now
from src.phase_client import PhaseControlError
from src.navigation import STAGE_LABELS


class PhaseService:
    def __init__(self, db, client, guild_id, allowed_channels, demo_mode=True):
        self.db, self.client, self.guild_id = db, client, guild_id
        self.allowed_channels, self.demo_mode = frozenset(allowed_channels), demo_mode

    def _authorize(self, channel):
        valid_ids = all(isinstance(value, str) and value.isascii() and value.isdigit() and
                        17 <= len(value) <= 20 and 0 < int(value) < 2**64 and str(int(value)) == value
                        for value in (self.guild_id, channel))
        if channel not in self.allowed_channels or not valid_ids:
            raise ValueError("此伺服器／頻道不在主持者設定的授權範圍")

    def context(self, channel):
        self._authorize(channel)
        with self.db.connect() as db:
            db.execute("INSERT INTO phase_experiments (experiment_id,guild_id,channel_id,demo_mode) VALUES (?,?,?,?) ON CONFLICT(guild_id,channel_id,demo_mode) DO NOTHING",
                       (str(uuid.uuid4()), self.guild_id, channel, int(self.demo_mode)))
        return self.db.rows("SELECT * FROM phase_experiments WHERE guild_id=? AND channel_id=? AND demo_mode=?",
                            (self.guild_id, channel, int(self.demo_mode)))[0]

    def pending(self, channel):
        self._authorize(channel)
        rows = self.db.rows("SELECT * FROM phase_events WHERE guild_id=? AND channel_id=? AND demo_mode=? AND status NOT IN ('APPLIED','DEMO','SUPERSEDED') ORDER BY sequence LIMIT 1",
                            (self.guild_id, channel, int(self.demo_mode)))
        return rows[0] if rows else None

    def event_status(self, event_id):
        rows = self.db.rows("SELECT status FROM phase_events WHERE event_id=? AND guild_id=? AND demo_mode=?",
                            (event_id, self.guild_id, int(self.demo_mode)))
        return rows[0]["status"] if rows else None

    def prepare(self, channel, phase_name):
        if phase_name not in STAGE_LABELS.values():
            raise ValueError("請選擇既有 CPS 子階段")
        self.context(channel)
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            context = db.execute("SELECT * FROM phase_experiments WHERE guild_id=? AND channel_id=? AND demo_mode=?",
                                 (self.guild_id, channel, int(self.demo_mode))).fetchone()
            pending = db.execute("SELECT * FROM phase_events WHERE experiment_id=? AND status NOT IN ('APPLIED','DEMO','SUPERSEDED')", (context["experiment_id"],)).fetchone()
            if pending:
                if pending["phase_name"] != phase_name:
                    raise ValueError("尚有未完成的階段事件，請先重試原事件或查詢目前階段")
                return dict(pending)
            event = dict(event_id=str(uuid.uuid4()), experiment_id=context["experiment_id"], guild_id=self.guild_id,
                         channel_id=channel, phase_id=str(uuid.uuid4()), phase_name=phase_name, sequence=context["sequence"] + 1)
            db.execute("INSERT INTO phase_events (event_id,experiment_id,guild_id,channel_id,demo_mode,phase_id,phase_name,sequence,payload,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,'PENDING',?)",
                       (event["event_id"], event["experiment_id"], self.guild_id, channel, int(self.demo_mode),
                        event["phase_id"], phase_name, event["sequence"], json.dumps(event, ensure_ascii=False, sort_keys=True), utc_now()))
        return self.db.rows("SELECT * FROM phase_events WHERE event_id=?", (event["event_id"],))[0]

    def _save_current(self, channel, remote, adopt=False):
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            local = db.execute("SELECT * FROM phase_experiments WHERE guild_id=? AND channel_id=? AND demo_mode=?",
                               (self.guild_id, channel, int(self.demo_mode))).fetchone()
            if remote["experiment_id"] != local["experiment_id"]:
                count = db.execute("SELECT count(*) FROM phase_events WHERE experiment_id=?", (local["experiment_id"],)).fetchone()[0]
                if not adopt or count or local["sequence"]:
                    raise PhaseControlError("頻道已綁定不同實驗，請核對或還原原有本機資料庫，不能覆蓋")
                db.execute("UPDATE phase_experiments SET experiment_id=? WHERE experiment_id=?", (remote["experiment_id"], local["experiment_id"]))
            if remote["sequence"] < local["sequence"] or (remote["sequence"] == local["sequence"] and local["phase_id"] and remote["phase_id"] != local["phase_id"]):
                raise PhaseControlError("工具代理回報較舊或衝突的階段；保留本機最後確認狀態", True)
            db.execute("UPDATE phase_experiments SET phase_id=?,phase_name=?,sequence=?,effective_at=?,checked_at=? WHERE guild_id=? AND channel_id=? AND demo_mode=?",
                       (remote["phase_id"], remote["phase_name"], remote["sequence"], remote["effective_at"], utc_now(),
                        self.guild_id, channel, int(self.demo_mode)))
            # A fresh current-state response can reconcile a timed-out event without another transition.
            db.execute("UPDATE phase_events SET status='APPLIED',effective_at=?,error_message=NULL WHERE experiment_id=? AND phase_id=? AND sequence=?",
                       (remote["effective_at"], remote["experiment_id"], remote["phase_id"], remote["sequence"]))
            db.execute("UPDATE phase_events SET status='SUPERSEDED',error_message='目前已是後續階段，未將舊事件誤認為目前階段' WHERE experiment_id=? AND sequence<=? AND phase_id!=? AND status NOT IN ('APPLIED','DEMO')",
                       (remote["experiment_id"], remote["sequence"], remote["phase_id"]))

    def sync(self, event_id):
        rows = self.db.rows("SELECT * FROM phase_events WHERE event_id=?", (event_id,))
        if not rows:
            raise ValueError("找不到階段事件")
        event = rows[0]
        self._authorize(event["channel_id"])
        if event["guild_id"] != self.guild_id or bool(event["demo_mode"]) != self.demo_mode:
            raise ValueError("不能跨伺服器或 Demo 模式同步事件")
        payload = json.loads(event["payload"])
        with self.db.connect() as db:
            db.execute("UPDATE phase_events SET attempts=attempts+1 WHERE event_id=?", (event_id,))
        if self.demo_mode:
            if event["status"] == "DEMO":
                return self.context(event["channel_id"])
            stamp = utc_now()
            self._save_current(event["channel_id"], {**payload, "effective_at": stamp})
            with self.db.connect() as db:
                db.execute("UPDATE phase_events SET status='DEMO' WHERE event_id=?", (event_id,))
            return self.context(event["channel_id"])
        try:
            ack = self.client.apply(payload)
            remote = self.client.current(self.guild_id, event["channel_id"])
            if remote is None or remote["sequence"] < payload["sequence"]:
                raise PhaseControlError("事件已回應，但目前階段尚未確認；請查詢或重試原事件", True)
            if remote["sequence"] == payload["sequence"] and remote["phase_id"] != payload["phase_id"]:
                raise PhaseControlError("目前階段與切換事件衝突，請核對", True)
            self._save_current(event["channel_id"], remote)
            with self.db.connect() as db:
                db.execute("UPDATE phase_events SET status='APPLIED',effective_at=?,error_message=NULL WHERE event_id=?", (ack["effective_at"], event_id))
        except PhaseControlError as error:
            with self.db.connect() as db:
                db.execute("UPDATE phase_events SET status=?,error_message=? WHERE event_id=?", ("UNKNOWN" if error.uncertain else "FAILED", str(error), event_id))
            raise
        return self.context(event["channel_id"])

    def refresh(self, channel):
        local = self.context(channel)
        if self.demo_mode:
            return local
        remote = self.client.current(self.guild_id, channel)
        if remote is None:
            if local["sequence"] or self.pending(channel):
                raise PhaseControlError("工具代理未回報有效階段；保留本機紀錄，請核對資料庫與待處理事件", True)
            return local
        self._save_current(channel, remote, adopt=True)
        return self.context(channel)
