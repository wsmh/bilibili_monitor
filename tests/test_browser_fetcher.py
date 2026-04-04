import unittest

from browser_fetcher import (
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


if __name__ == "__main__":
    unittest.main()
