"""SQL access for notes. Timestamps are stored as UTC ISO-8601 strings."""
from datetime import datetime, timezone

from .models import Note


def _to_db(ts):
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _from_db(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)


class NoteRepository:
    def __init__(self, conn):
        self.conn = conn

    def add(self, title, body, created_at, tags=()):
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                (title, body, _to_db(created_at)),
            )
            note_id = cur.lastrowid
            self.conn.executemany(
                "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)",
                [(note_id, t) for t in tags],
            )
        return self.get(note_id)

    def get(self, note_id):
        row = self.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self._hydrate([row])[0] if row else None

    def delete(self, note_id):
        with self.conn:
            cur = self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0

    def _where(self, tag):
        if tag is None:
            return "", []
        return " WHERE id IN (SELECT note_id FROM note_tags WHERE tag = ?)", [tag]

    def list(self, tag=None, limit=None, offset=0):
        where, args = self._where(tag)
        sql = "SELECT * FROM notes" + where + " ORDER BY created_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args += [limit, offset]
        return self._hydrate(self.conn.execute(sql, args).fetchall())

    def count(self, tag=None):
        where, args = self._where(tag)
        return self.conn.execute("SELECT COUNT(*) FROM notes" + where, args).fetchone()[0]

    def _hydrate(self, rows):
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        tags = {}
        for t in self.conn.execute(
            f"SELECT note_id, tag FROM note_tags WHERE note_id IN ({marks}) ORDER BY tag", ids
        ):
            tags.setdefault(t["note_id"], []).append(t["tag"])
        return [
            Note(r["id"], r["title"], r["body"], _from_db(r["created_at"]), tags.get(r["id"], []))
            for r in rows
        ]
