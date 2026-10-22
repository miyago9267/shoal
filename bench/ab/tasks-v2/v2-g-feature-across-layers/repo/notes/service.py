"""Business rules: validation, defaults and listing."""
import re
from datetime import datetime, timezone

MAX_LIMIT = 100
DEFAULT_LIMIT = 20
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class NotFound(LookupError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


class NoteService:
    def __init__(self, repo, clock=None):
        self.repo = repo
        self.clock = clock or utc_now

    def create_note(self, title, body="", tags=(), created_at=None):
        """``created_at`` lets imports keep their original timestamp."""
        title = (title or "").strip()
        if not title:
            raise ValueError("title is required")
        if len(title) > 200:
            raise ValueError("title is too long")
        clean = sorted({self._check_tag(t) for t in tags})
        when = created_at or self.clock()
        if when.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return self.repo.add(title, body or "", when, clean)

    def get_note(self, note_id):
        note = self.repo.get(note_id)
        if note is None:
            raise NotFound(note_id)
        return note

    def delete_note(self, note_id):
        if not self.repo.delete(note_id):
            raise NotFound(note_id)

    def list_notes(self, tag=None, limit=DEFAULT_LIMIT, offset=0):
        """Return ``(notes, total)`` for one page, newest first."""
        limit = self._check_limit(limit)
        if offset < 0:
            raise ValueError("offset must not be negative")
        if tag is not None:
            tag = self._check_tag(tag)
        return self.repo.list(tag=tag, limit=limit, offset=offset), self.repo.count(tag)

    @staticmethod
    def _check_limit(limit):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        return limit

    @staticmethod
    def _check_tag(tag):
        tag = str(tag).strip().lower()
        if not _TAG_RE.match(tag):
            raise ValueError(f"invalid tag {tag!r}")
        return tag
