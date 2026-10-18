import csv
import io

TABLES = {"operations", "observations", "sessions"}


def export_csv(db, table, session_id):
    if table not in TABLES:
        raise ValueError("不支援的匯出類型")
    with db.connect() as conn:
        cursor = conn.execute(f"SELECT * FROM {table} WHERE session_id=?", (session_id,))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([d[0] for d in cursor.description])
        writer.writerows(tuple(row) for row in cursor)
    return output.getvalue().encode("utf-8-sig")


def channel_records(db, table, channel_id):
    if table == "operations":
        return db.rows("SELECT * FROM operations WHERE discord_channel_id=? ORDER BY timestamp_utc DESC", (channel_id,))
    if table == "observations":
        return db.rows("SELECT o.*, s.discord_channel_id FROM observations o JOIN sessions s ON o.session_id=s.session_id WHERE s.discord_channel_id=? ORDER BY o.timestamp_utc DESC", (channel_id,))
    raise ValueError("不支援的頻道匯出類型")


def export_channel_csv(db, table, channel_id):
    if table == "operations":
        sql = "SELECT * FROM operations WHERE discord_channel_id=? ORDER BY timestamp_utc"
    elif table == "observations":
        sql = "SELECT o.*, s.discord_channel_id FROM observations o JOIN sessions s ON o.session_id=s.session_id WHERE s.discord_channel_id=? ORDER BY o.timestamp_utc"
    else:
        raise ValueError("不支援的頻道匯出類型")
    with db.connect() as conn:
        cursor = conn.execute(sql, (channel_id,))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([d[0] for d in cursor.description])
        writer.writerows(tuple(row) for row in cursor)
    return output.getvalue().encode("utf-8-sig")
