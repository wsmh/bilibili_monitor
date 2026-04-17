import unittest
from unittest.mock import patch

from feishu_bot import FeishuBot


class FeishuBotTestCase(unittest.TestCase):
    def test_send_multiple_comments_keeps_full_comment_content(self):
        """Ensure multi-comment cards preserve the full comment body."""
        captured_payload = {}

        def fake_send(_, payload):
            captured_payload["payload"] = payload
            return True

        bot = FeishuBot("https://example.com/hook")
        long_comment = "long-comment-" * 12

        with patch.object(FeishuBot, "_send", autospec=True, side_effect=fake_send):
            result = bot.send_multiple_comments(
                {
                    "title": "Video",
                    "link": "https://www.bilibili.com/video/BV1xx411c7mD",
                },
                [
                    {
                        "ctime": 1710000000,
                        "parent": 0,
                        "like": 3,
                        "content": long_comment,
                    }
                ],
            )

        self.assertTrue(result)
        content = captured_payload["payload"]["card"]["elements"][0]["text"]["content"]
        self.assertTrue(content.startswith("\U0001f4ac **"))
        self.assertIn(" | \U0001f44d 3\n> ", content)
        self.assertTrue(content.endswith(f"> {long_comment}"))


if __name__ == "__main__":
    unittest.main()
