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
        error = Exception(
            "网络错误，状态码：412 - The request was rejected because of the bilibili security control policy."
        )

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

    def test_extract_upower_qa_answers_only_keeps_up_answers_and_sorts(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="SESSDATA=test")
        data = {
            "list": [
                {
                    "qa_id": 1,
                    "upower_level": {"level_name": "高档充电", "level_type": 20, "level_price": 30000},
                    "question": {"user": {"nickname": "asker", "mid": 2}},
                    "answer": {"answer_time": 123},
                    "content_list": [
                        {
                            "id": 10,
                            "type": 1,
                            "state": 2,
                            "ptime": 111,
                            "text": "Q1",
                            "user": {"nickname": "asker", "mid": 2},
                        },
                        {
                            "id": 11,
                            "type": 2,
                            "state": 2,
                            "ptime": 222,
                            "text": "A1",
                            "user": {"nickname": "up", "mid": 9},
                        },
                        {
                            "id": 12,
                            "type": 2,
                            "state": 2,
                            "ptime": 333,
                            "text": "other",
                            "user": {"nickname": "someone", "mid": 3},
                        },
                    ],
                },
                {
                    "qa_id": 2,
                    "upower_level": {"level_name": "高档充电", "level_type": 20, "level_price": 30000},
                    "question": {"user": {"nickname": "asker2", "mid": 4}},
                    "answer": {"answer_time": 444},
                    "content_list": [
                        {
                            "id": 20,
                            "type": 2,
                            "state": 2,
                            "ptime": 555,
                            "text": "A2",
                            "user": {"nickname": "up", "mid": 9},
                        }
                    ],
                },
            ]
        }

        answers = api.extract_upower_qa_answers(data, up_mid=9)

        self.assertEqual([entry["content_id"] for entry in answers], [20, 11])
        self.assertEqual(answers[0]["question_nickname"], "asker2")
        self.assertEqual(answers[1]["question_text"], "Q1")


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

    async def test_enrich_reply_context_attaches_parent_comment_when_present(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="SESSDATA=test")
        post = {
            "comment_type": 1,
            "comment_oid": 2,
        }
        all_comments = [
            {
                "rpid": 10,
                "mid": 2,
                "uname": "someone",
                "content": "original",
                "ctime": 1,
                "like": 0,
                "parent": 0,
                "root": 0,
            }
        ]
        target_comments = [
            {
                "rpid": 11,
                "mid": 1,
                "uname": "UP",
                "content": "my reply",
                "ctime": 2,
                "like": 0,
                "parent": 10,
                "root": 10,
            }
        ]

        await api.enrich_reply_context(post, target_comments, all_comments)

        self.assertEqual(target_comments[0]["reply_to"]["content"], "original")

    async def test_enrich_reply_context_fetches_parent_comment_when_missing(self):
        api = BilibiliAPI(fetch_mode="api", cookie_string="SESSDATA=test")
        post = {
            "comment_type": 1,
            "comment_oid": 2,
        }
        target_comments = [
            {
                "rpid": 11,
                "mid": 1,
                "uname": "UP",
                "content": "my reply",
                "ctime": 2,
                "like": 0,
                "parent": 99,
                "root": 88,
            }
        ]

        with patch.object(
            api,
            "_get_reply_thread_map_via_http",
            AsyncMock(return_value={99: {"uname": "someone", "content": "original"}}),
        ):
            await api.enrich_reply_context(post, target_comments, [])

        self.assertEqual(target_comments[0]["reply_to"]["content"], "original")


class SecurityControlErrorTestCase(unittest.TestCase):
    def test_string_representation_contains_status_code(self):
        error = SecurityControlError("blocked", cooldown_seconds=120)

        self.assertIn("blocked", str(error))


if __name__ == "__main__":
    unittest.main()
