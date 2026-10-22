import unittest

from tick.model import Task
from tick.ordering import by_due, by_id


class OrderingTest(unittest.TestCase):
    def test_by_due(self):
        tasks = [Task(1, "a", 2, None), Task(2, "b", 1, 100), Task(3, "c", 3, 200)]
        self.assertEqual([t.id for t in by_due(tasks)], [2, 3, 1])

    def test_by_id(self):
        tasks = [Task(3, "c"), Task(1, "a"), Task(2, "b")]
        self.assertEqual([t.id for t in by_id(tasks)], [1, 2, 3])
