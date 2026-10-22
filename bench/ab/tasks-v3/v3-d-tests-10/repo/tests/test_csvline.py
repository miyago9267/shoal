import unittest

from utilkit import csvline


class CsvlineSmoke(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(csvline.split_csv_line("a,b,c"), ["a", "b", "c"])

    def test_join_quotes(self):
        self.assertEqual(csvline.join_csv_line(["a", "b,c", 'd"e']), 'a,"b,c","d""e"')
