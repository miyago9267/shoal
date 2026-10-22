"""Wire the layers together."""
from .db import connect
from .repository import NoteRepository
from .service import NoteService


def build_service(db_path=":memory:", clock=None):
    return NoteService(NoteRepository(connect(db_path)), clock=clock)
