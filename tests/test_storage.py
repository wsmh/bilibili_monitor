import os
import tempfile
import unittest

from storage import CommentStorage


class CommentStorageTestCase(unittest.TestCase):
    def test_upower_initialized_persists_and_dedups(self):
        with tempfile.TemporaryDirectory() as directory:
            filepath = os.path.join(directory, "data.json")

            storage = CommentStorage(filepath)
            self.assertFalse(storage.upower_initialized)

            storage.mark_multiple_upower_answers_notified([1, 2], max_items=10)
            storage.set_upower_initialized(True)

            reloaded = CommentStorage(filepath)
            self.assertTrue(reloaded.upower_initialized)
            self.assertTrue(reloaded.is_upower_answer_notified(1))
            self.assertTrue(reloaded.is_upower_answer_notified(2))


if __name__ == "__main__":
    unittest.main()
