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
