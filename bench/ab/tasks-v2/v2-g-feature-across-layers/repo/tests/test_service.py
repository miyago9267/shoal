import unittest
from datetime import datetime

from notes.service import NotFound
from tests.support import T0, seeded


class ServiceTest(unittest.TestCase):
    def test_newest_first_with_offset(self):
        svc = seeded(5)
        notes, total = svc.list_notes(limit=2, offset=1)
        self.assertEqual([n.title for n in notes], ["note 4", "note 3"])
        self.assertEqual(total, 5)

    def test_tag_filter(self):
        svc = seeded(6, tags_every=2)
        notes, total = svc.list_notes(tag="WORK")
        self.assertEqual([n.title for n in notes], ["note 6", "note 4", "note 2"])
        self.assertEqual(total, 3)

    def test_validation(self):
        svc = seeded(0)
        for bad in (dict(title=""), dict(title="x", tags=["no spaces"]),
                    dict(title="x", created_at=datetime(2020, 1, 1))):
            with self.assertRaises(ValueError):
                svc.create_note(**bad)
        with self.assertRaises(ValueError):
            svc.list_notes(limit=0)
        with self.assertRaises(ValueError):
            svc.list_notes(limit=101)

    def test_backdated_import_sorts_by_timestamp(self):
        svc = seeded(2)
        svc.create_note("old", created_at=T0)
        notes, _ = svc.list_notes()
        self.assertEqual([n.title for n in notes], ["note 2", "note 1", "old"])

    def test_delete(self):
        svc = seeded(1)
        svc.delete_note(1)
        with self.assertRaises(NotFound):
            svc.get_note(1)


if __name__ == "__main__":
    unittest.main()
