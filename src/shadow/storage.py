"""Local SQLite history; incomplete observations are labeled explicitly."""
from datetime import datetime, timezone
import csv
import json
import sqlite3
import threading


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY, identity TEXT, name TEXT, path TEXT,
                reported_start TEXT, observed_start TEXT, observed_end TEXT,
                status TEXT, duration_seconds INTEGER);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        self.interrupt("interrupted")

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.lock:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)",
                                (key, json.dumps(value)))

    def start(self, app):
        with self.lock:
            with self.db:
                self.db.execute("""INSERT INTO sessions
                    (identity, name, path, reported_start, observed_start, status)
                    VALUES (?, ?, ?, ?, ?, 'active')""",
                    (app.identity, app.name, app.path, app.started, utcnow()))

    def stop(self, app):
        now = utcnow()
        with self.lock:
            row = self.db.execute("""SELECT id, observed_start FROM sessions
                WHERE identity=? AND status='active' ORDER BY id DESC LIMIT 1""",
                (app.identity,)).fetchone()
            if row is None:
                return 0
            duration = max(0, int((datetime.fromisoformat(now) -
                                  datetime.fromisoformat(row["observed_start"])).total_seconds()))
            with self.db:
                self.db.execute("""UPDATE sessions SET observed_end=?, status='stopped',
                    duration_seconds=? WHERE id=?""", (now, duration, row["id"]))
        return duration

    def interrupt(self, reason):
        with self.lock:
            with self.db:
                self.db.execute("UPDATE sessions SET status=?, observed_end=? WHERE status='active'",
                                (reason, utcnow()))

    def rows(self, limit=500):
        with self.lock:
            return self.db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def export(self, path):
        with self.lock:
            cursor = self.db.execute("SELECT * FROM sessions ORDER BY id")
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            # Prevent spreadsheet formula execution when opening exported text fields.
            def safe(value):
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    return "'" + value
                return value
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns)
                writer.writerows([safe(value) for value in row] for row in rows)

    def close(self):
        with self.lock:
            self.db.close()
