import unittest

from hq import router
from hq.errors import ValidationError


class UploadTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("upload", {"filename": "a.png", "size": 10, "content_type": "image/png"}), {"filename": "a.png", "size": 10, "content_type": "image/png"})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("upload", {"filename": "../x", "size": 10, "content_type": "image/png"})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("upload", {"filename": "a.exe", "size": 10, "content_type": "application/x-msdownload"})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("upload", {"filename": "a", "size": 0, "content_type": "text/plain"})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("upload", {"filename": "", "size": 1, "content_type": "text/plain"})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("upload", [])
