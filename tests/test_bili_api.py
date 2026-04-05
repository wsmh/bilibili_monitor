import unittest
from unittest.mock import AsyncMock, patch

from bili_api import BilibiliAPI, SecurityControlError


class BilibiliAPITestCase(unittest.TestCase):
    def test_filter_up_comments_only_keeps_matching_uid_and_sorts_by_time(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")
        comments = [
            {"rpid": 3, "mid": "1", "ctime": 100, "content": "old"},
            {"rpid": 2, "mid": 9, "ctime": 200, "content": "other"},
            {"rpid": 1, "mid": 1, "ctime": 300, "content": "new"},
        ]

        result = api.filter_up_comments(comments, 1)

        self.assertEqual([comment["rpid"] for comment in result], [1, 3])

    def test_security_block_detection_matches_412_html(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")
        error = Exception("网络错误，状态码：412 - The request was rejected because of the bilibili security control policy.")

        self.assertTrue(api._is_security_block(error))

    def test_guest_mode_only_fetches_single_comment_page(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")

        self.assertEqual(api._get_comment_page_limit(), 1)

    def test_cookie_string_enables_authenticated_mode(self):
        api = BilibiliAPI(
            cookie_string="SESSDATA=test_sess; bili_jct=test_jct; DedeUserID=123; buvid3=test_buvid3",
            fetch_mode="api",
        )

        self.assertTrue(api.has_auth())
        self.assertEqual(api._get_comment_page_limit(), 2)
        self.assertEqual(api.credential.buvid3, "test_buvid3")


class BilibiliAPIAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_latest_video_propagates_security_control_error(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")

        with patch.object(
            api,
            "_retry_with_backoff",
            AsyncMock(side_effect=SecurityControlError("blocked")),
        ):
            with self.assertRaises(SecurityControlError):
                await api.get_latest_video(1)

    async def test_get_video_comments_propagates_security_control_error(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")

        with patch.object(
            api,
            "_retry_with_backoff",
            AsyncMock(side_effect=SecurityControlError("blocked")),
        ):
            with self.assertRaises(SecurityControlError):
                await api.get_video_comments(1)

    async def test_get_user_profile_returns_normalized_name_and_uid(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="")
        mocked_user = AsyncMock()
        mocked_user.get_user_info.return_value = {
            "mid": 1671203508,
            "name": "洪洪火火复盘",
        }

        with patch("bili_api.user.User", return_value=mocked_user):
            profile = await api.get_user_profile(1671203508)

        self.assertEqual(
            profile,
            {"mid": 1671203508, "uname": "洪洪火火复盘"},
        )


class SecurityControlErrorTestCase(unittest.TestCase):
    def test_string_representation_contains_status_code(self):
        error = SecurityControlError("blocked", cooldown_seconds=120)

        self.assertIn("blocked", str(error))


if __name__ == "__main__":
    unittest.main()
