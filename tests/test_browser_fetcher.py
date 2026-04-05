import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from browser_fetcher import (
    BrowserBilibiliFetcher,
    build_playwright_cookies,
    extract_latest_video_from_space_payload,
    normalize_comment_component_payloads,
)


class BrowserFetcherHelpersTestCase(unittest.TestCase):
    def test_build_playwright_cookies_from_cookie_string(self):
        cookies = build_playwright_cookies(
            "SESSDATA=test_sess; bili_jct=test_jct; DedeUserID=123"
        )

        self.assertEqual([cookie["name"] for cookie in cookies], ["SESSDATA", "bili_jct", "DedeUserID"])
        self.assertTrue(all(cookie["domain"] == ".bilibili.com" for cookie in cookies))
        self.assertTrue(all(cookie["path"] == "/" for cookie in cookies))

    def test_extract_latest_video_from_space_payload(self):
        payload = {
            "data": {
                "list": {
                    "vlist": [
                        {
                            "bvid": "BV1xx411c7mD",
                            "aid": 123456,
                            "title": "最新视频",
                            "description": "desc",
                            "created": 1770000000,
                        }
                    ]
                }
            }
        }

        video = extract_latest_video_from_space_payload(payload)

        self.assertEqual(video["bvid"], "BV1xx411c7mD")
        self.assertEqual(video["aid"], 123456)
        self.assertEqual(video["link"], "https://www.bilibili.com/video/BV1xx411c7mD")

    def test_normalize_comment_component_payloads_flattens_threads_and_replies(self):
        payloads = [
            {
                "thread": {
                    "rpid": 100,
                    "mid": 1,
                    "member": {"mid": "1", "uname": "UP主"},
                    "content": {"message": "主评论"},
                    "ctime": 1000,
                    "like": 2,
                    "parent": 0,
                },
                "replies": [
                    {
                        "rpid": 101,
                        "mid": 2,
                        "member": {"mid": "2", "uname": "路人"},
                        "content": {"message": "回复"},
                        "ctime": 1001,
                        "like": 0,
                        "parent": 100,
                    }
                ],
            }
        ]

        comments = normalize_comment_component_payloads(payloads)

        self.assertEqual([comment["rpid"] for comment in comments], [100, 101])
        self.assertEqual(comments[0]["uname"], "UP主")
        self.assertEqual(comments[1]["parent"], 100)


class BrowserFetcherLoginHintTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_login_hint_returns_none_when_nav_api_reports_logged_out(self):
        fetcher = BrowserBilibiliFetcher(cookie_string="DedeUserID=123")
        response = SimpleNamespace(
            json=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "isLogin": False,
                        "mid": 123,
                        "uname": "tester",
                    },
                }
            )
        )
        page = SimpleNamespace(goto=AsyncMock(return_value=response), close=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))

        with patch.object(fetcher, "_ensure_context", AsyncMock(return_value=context)):
            result = await fetcher.get_login_hint()

        self.assertIsNone(result)
        page.goto.assert_awaited_once()
        page.close.assert_awaited_once()

    async def test_get_login_hint_returns_account_info_when_nav_api_reports_logged_in(self):
        fetcher = BrowserBilibiliFetcher(cookie_string="DedeUserID=123")
        response = SimpleNamespace(
            json=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "isLogin": True,
                        "mid": 123,
                        "uname": "tester",
                    },
                }
            )
        )
        page = SimpleNamespace(goto=AsyncMock(return_value=response), close=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))

        with patch.object(fetcher, "_ensure_context", AsyncMock(return_value=context)):
            result = await fetcher.get_login_hint()

        self.assertEqual(result, {"mid": 123, "uname": "tester"})
        page.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
