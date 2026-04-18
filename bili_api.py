import asyncio
import random
from typing import Dict, List, Optional

import requests
from bilibili_api import Credential, comment, user
from bilibili_api.comment import CommentResourceType

from browser_fetcher import (
    BrowserBilibiliFetcher,
    extract_latest_post_from_space_dynamic_payload,
)
from config import (
    BILI_BILI_JCT,
    BILI_BROWSER_EXECUTABLE,
    BILI_BROWSER_HEADLESS,
    BILI_BROWSER_TIMEOUT_MS,
    BILI_BUVID3,
    BILI_BUVID4,
    BILI_COOKIE,
    BILI_DEDEUSERID,
    BILI_FETCH_MODE,
    BILI_SESSDATA,
    COMMENT_MAX_PAGES_AUTH,
    COMMENT_MAX_PAGES_GUEST,
)


SPACE_DYNAMIC_FEED_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
SPACE_DYNAMIC_FEATURES = (
    "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,forwardListHidden,"
    "decorationCard,commentsNewVersion,onlyfansAssetsV2,ugcDelete,onlyfansQaCard"
)


class SecurityControlError(Exception):
    """B站安全风控错误"""

    def __init__(self, message: str, cooldown_seconds: int = 120):
        super().__init__(message)
        self.cooldown_seconds = cooldown_seconds


class BilibiliAPI:
    """B站API封装 - 使用 bilibili-api-python 库"""

    def __init__(
        self,
        cookie_string: str = BILI_COOKIE,
        sessdata: str = BILI_SESSDATA,
        bili_jct: str = BILI_BILI_JCT,
        buvid3: str = BILI_BUVID3,
        buvid4: str = BILI_BUVID4,
        dedeuserid: str = BILI_DEDEUSERID,
        fetch_mode: str = BILI_FETCH_MODE,
        browser_executable: str = BILI_BROWSER_EXECUTABLE,
        browser_headless: bool = BILI_BROWSER_HEADLESS,
        browser_timeout_ms: int = BILI_BROWSER_TIMEOUT_MS,
    ):
        self.cookie_string = (cookie_string or "").strip()
        self.cookie_fields = self._parse_cookie_string(self.cookie_string)
        self.fetch_mode = (fetch_mode or "browser").strip().lower()
        self.credential = Credential(
            sessdata=self._pick_cookie_value("SESSDATA", sessdata),
            bili_jct=self._pick_cookie_value("bili_jct", bili_jct),
            buvid3=self._pick_cookie_value("BUVID3", buvid3),
            buvid4=self._pick_cookie_value("BUVID4", buvid4),
            dedeuserid=self._pick_cookie_value("DedeUserID", dedeuserid),
        )
        self.browser_fetcher = BrowserBilibiliFetcher(
            cookie_string=self.cookie_string,
            executable_path=browser_executable,
            headless=browser_headless,
            timeout_ms=browser_timeout_ms,
        )
        # 浏览器User-Agent列表，用于轮换
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ]
        print(f"🌐 B站抓取模式: {self.fetch_mode}")
        if self.fetch_mode in {"browser", "auto"}:
            if self.browser_fetcher.executable_path:
                print(f"🧭 浏览器抓取已启用: {self.browser_fetcher.executable_path}")
            else:
                print("🧭 浏览器抓取已启用: 使用 Playwright 自带 Chromium 或默认浏览器")
        if self.has_auth():
            print("🔐 已启用 B站登录态，请求将携带 Cookie")
        else:
            print("⚠️ 当前未配置 B站登录态，将仅抓取 1 页最新评论，稳定性和准确率会受限")

    def _get_random_ua(self) -> str:
        """获取随机User-Agent"""

        return random.choice(self.user_agents)

    def _parse_cookie_string(self, cookie_string: str) -> Dict[str, str]:
        cookie_dict: Dict[str, str] = {}
        if not cookie_string:
            return cookie_dict

        for part in cookie_string.split(";"):
            item = part.strip()
            if not item or "=" not in item:
                continue
            key, value = item.split("=", 1)
            normalized_key = key.strip()
            cookie_dict[normalized_key] = value.strip()
            cookie_dict[normalized_key.lower()] = value.strip()
        return cookie_dict

    def _pick_cookie_value(self, key: str, explicit_value: str) -> Optional[str]:
        value = explicit_value if explicit_value else self.cookie_fields.get(key)
        if not value:
            value = self.cookie_fields.get(key.lower())
        return value or None

    def has_auth(self) -> bool:
        return bool(self.credential.sessdata)

    def prefers_browser_fetch(self) -> bool:
        return self.fetch_mode in {"browser", "auto"} and self.browser_fetcher.is_available()

    def _get_comment_page_limit(self) -> int:
        return COMMENT_MAX_PAGES_AUTH if self.has_auth() else COMMENT_MAX_PAGES_GUEST

    def _is_security_block(self, error: Exception) -> bool:
        error_text = str(error).lower()
        return (
            "412" in error_text
            or "security control policy" in error_text
            or "访问请求被拒绝" in error_text
            or "the request was rejected because of the bilibili security control policy" in error_text
        )

    def _is_auth_error(self, error: Exception) -> bool:
        error_text = str(error).lower()
        return (
            "credential" in error_text
            or "sessdata" in error_text
            or "登录" in str(error)
            or "not logged in" in error_text
            or "账号未登录" in str(error)
        )

    async def validate_login(self) -> Optional[Dict]:
        """验证当前登录态是否可用"""

        if self.prefers_browser_fetch():
            return await self.browser_fetcher.get_login_hint()

        if not self.has_auth():
            return None

        try:
            info = await user.get_self_info(self.credential)
            return {
                "mid": info.get("mid"),
                "uname": info.get("name") or info.get("uname"),
            }
        except Exception as exc:
            if self._is_auth_error(exc):
                print(f"⚠️ B站登录态校验失败: {exc}")
                return None
            raise

    async def get_user_profile(self, uid: int) -> Optional[Dict]:
        """获取指定 UID 的用户信息，用于通知文案等非关键路径。"""

        try:
            info = await user.User(uid, credential=self.credential).get_user_info()
        except Exception as exc:
            print(f"⚠️ 获取UP主信息失败: {exc}")
            return None

        return {
            "mid": info.get("mid", uid),
            "uname": info.get("name") or info.get("uname"),
        }

    async def _retry_with_backoff(self, func, max_retries: int = 3, base_delay: float = 1.0):
        """带指数退避的重试机制"""

        last_exception = None

        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as exc:
                last_exception = exc
                if self._is_security_block(exc):
                    raise SecurityControlError(
                        f"B站触发 412 风控: {exc}",
                        cooldown_seconds=120,
                    ) from exc

                error_msg = str(exc).lower()

                retryable_errors = [
                    "timeout",
                    "connection",
                    "ssl",
                    "reset",
                    "refused",
                    "too many requests",
                    "429",
                    "503",
                    "502",
                    "500",
                    "verify",
                    "certificate",
                    "handshake",
                ]

                is_retryable = any(err in error_msg for err in retryable_errors)

                if not is_retryable and attempt < max_retries - 1:
                    is_retryable = "<html" in str(exc) or "<script" in str(exc)

                if not is_retryable:
                    raise

                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                    print(f"  ⚠️  请求失败，{delay:.1f}秒后重试({attempt + 1}/{max_retries}): {exc}")
                    await asyncio.sleep(delay)
                else:
                    print(f"  ❌ 重试{max_retries}次后仍然失败: {exc}")

        raise last_exception

    async def get_latest_video(self, uid: int) -> Optional[Dict]:
        """获取UP主最新发布的视频（带重试机制）"""

        if self.prefers_browser_fetch():
            try:
                video = await self.browser_fetcher.get_latest_video(uid)
                if video:
                    return video
                if self.fetch_mode == "browser":
                    return None
            except Exception as exc:
                print(f"浏览器抓取最新视频失败: {exc}")
                if self.fetch_mode == "browser":
                    return None

        async def _fetch():
            await asyncio.sleep(random.uniform(0.1, 0.3))

            u = user.User(uid, credential=self.credential)
            videos = await u.get_videos(ps=1)

            if videos and videos.get("list", {}).get("vlist"):
                video_data = videos["list"]["vlist"][0]
                return {
                    "bvid": video_data["bvid"],
                    "aid": video_data["aid"],
                    "title": video_data["title"],
                    "description": video_data.get("description", ""),
                    "created": video_data["created"],
                    "link": f"https://www.bilibili.com/video/{video_data['bvid']}",
                }
            return None

        try:
            return await self._retry_with_backoff(_fetch, max_retries=3, base_delay=1.0)
        except SecurityControlError:
            raise
        except Exception as exc:
            print(f"获取最新视频失败: {exc}")
            return None

    async def _get_latest_post_from_space_feed(self, uid: int) -> Optional[Dict]:
        if not self.has_auth() or not self.cookie_string:
            return None

        def _do_request() -> Dict:
            headers = {
                "User-Agent": self._get_random_ua(),
                "Referer": f"https://space.bilibili.com/{uid}/dynamic",
                "Cookie": self.cookie_string,
            }
            response = requests.get(
                SPACE_DYNAMIC_FEED_URL,
                params={
                    "host_mid": str(uid),
                    "platform": "web",
                    "features": SPACE_DYNAMIC_FEATURES,
                },
                headers=headers,
                timeout=10,
            )
            if response.status_code == 412:
                raise Exception("412 - The request was rejected because of the bilibili security control policy")
            response.raise_for_status()
            return response.json()

        payload = await self._retry_with_backoff(
            lambda: asyncio.to_thread(_do_request),
            max_retries=3,
            base_delay=0.5,
        )

        if payload.get("code") != 0:
            code = payload.get("code")
            if code == -101:
                return None
            raise Exception(f"space feed api failed: code={code} message={payload.get('message')}")

        return extract_latest_post_from_space_dynamic_payload(payload)

    async def get_latest_post(self, uid: int) -> Optional[Dict]:
        """获取 UP 主最新发布内容（视频/动态/充电相关动态）。

        优先从空间动态页抓取（更容易覆盖充电/专属内容），失败则回退到公开视频列表。
        """

        if self.prefers_browser_fetch():
            try:
                post = await self.browser_fetcher.get_latest_post(uid)
                if post:
                    return post
            except Exception as exc:
                print(f"浏览器抓取空间动态失败: {exc}")

        try:
            post = await self._get_latest_post_from_space_feed(uid)
            if post:
                return post
        except Exception as exc:
            print(f"API抓取空间动态失败: {exc}")

        video = await self.get_latest_video(uid)
        if not video:
            return None

        return {
            "kind": "video",
            "post_key": f"video:{video['bvid']}",
            "title": video["title"],
            "created": int(video.get("created") or 0),
            "link": video["link"],
            "dynamic_id": None,
            "comment_type": 1,
            "comment_oid": int(video["aid"]),
            "bvid": video["bvid"],
            "aid": int(video["aid"]),
        }

    async def get_video_comments(self, aid: int) -> List[Dict]:
        """获取视频的评论列表（使用get_comments_lazy新接口，带重试机制）"""

        if self.prefers_browser_fetch():
            try:
                comments = await self.browser_fetcher.get_video_comments(
                    f"https://www.bilibili.com/video/av{aid}"
                )
                if comments:
                    return comments
                if self.fetch_mode == "browser":
                    return comments
            except Exception as exc:
                print(f"浏览器抓取评论失败: {exc}")
                if self.fetch_mode == "browser":
                    return []

        comments_acc: List[Dict] = []
        seen_rpids = set()
        page = 1
        max_pages = self._get_comment_page_limit()
        pag = ""  # pagination offset

        async def _fetch_page(page_offset: str):
            return await comment.get_comments_lazy(
                oid=aid,
                type_=CommentResourceType.VIDEO,
                offset=page_offset,
                credential=self.credential,
            )

        try:
            while page <= max_pages:
                c = await self._retry_with_backoff(
                    lambda: _fetch_page(pag),
                    max_retries=3,
                    base_delay=0.5,
                )

                if "cursor" in c and "pagination_reply" in c["cursor"]:
                    pag = c["cursor"]["pagination_reply"].get("next_offset", "")
                else:
                    pag = ""

                replies = c.get("replies")
                if not replies:
                    break

                for reply in replies:
                    comment_data = {
                        "rpid": reply["rpid"],
                        "mid": reply["member"]["mid"],
                        "uname": reply["member"]["uname"],
                        "content": reply["content"]["message"],
                        "ctime": reply["ctime"],
                        "like": reply["count"],
                        "parent": reply.get("parent", 0),
                        "root": reply.get("root", 0) or 0,
                        "dialog": reply.get("dialog", 0) or 0,
                    }
                    if comment_data["rpid"] not in seen_rpids:
                        comments_acc.append(comment_data)
                        seen_rpids.add(comment_data["rpid"])

                    if reply.get("replies"):
                        for sub_reply in reply["replies"]:
                            sub_comment = {
                                "rpid": sub_reply["rpid"],
                                "mid": sub_reply["member"]["mid"],
                                "uname": sub_reply["member"]["uname"],
                                "content": sub_reply["content"]["message"],
                                "ctime": sub_reply["ctime"],
                                "like": sub_reply["count"],
                                "parent": sub_reply.get("parent", reply["rpid"]) or reply["rpid"],
                                "root": sub_reply.get("root", reply["rpid"]) or reply["rpid"],
                                "dialog": sub_reply.get("dialog", 0) or 0,
                            }
                            if sub_comment["rpid"] not in seen_rpids:
                                comments_acc.append(sub_comment)
                                seen_rpids.add(sub_comment["rpid"])

                page += 1
                if not pag:
                    break

                await asyncio.sleep(random.uniform(0.3, 0.6))

        except Exception as exc:
            if isinstance(exc, SecurityControlError):
                raise
            print(f"获取评论失败: {exc}")

        return comments_acc

    async def _get_reply_comments_via_http(self, oid: int, type_code: int) -> List[Dict]:
        """通过 /x/v2/reply 获取评论（适用于动态/相簿/专栏等）。"""

        comments_acc: List[Dict] = []
        seen_rpids = set()
        page = 1
        max_pages = self._get_comment_page_limit()

        def _do_request(pn: int) -> Dict:
            headers = {
                "User-Agent": self._get_random_ua(),
                "Referer": "https://www.bilibili.com",
            }
            if self.cookie_string:
                headers["Cookie"] = self.cookie_string

            response = requests.get(
                "https://api.bilibili.com/x/v2/reply",
                params={
                    "type": type_code,
                    "oid": oid,
                    "sort": 0,
                    "nohot": 1,
                    "ps": 20,
                    "pn": pn,
                },
                headers=headers,
                timeout=10,
            )
            if response.status_code == 412:
                raise Exception("412 - The request was rejected because of the bilibili security control policy")
            response.raise_for_status()
            return response.json()

        try:
            while page <= max_pages:
                payload = await self._retry_with_backoff(
                    lambda: asyncio.to_thread(_do_request, page),
                    max_retries=3,
                    base_delay=0.5,
                )

                if payload.get("code") != 0:
                    code = payload.get("code")
                    if code in {12002, 12009, -404}:
                        break
                    raise Exception(f"reply api failed: code={code} message={payload.get('message')}")

                data = payload.get("data") or {}
                replies = data.get("replies") or []
                if not replies:
                    break

                for reply in replies:
                    comment_data = {
                        "rpid": reply["rpid"],
                        "mid": reply.get("member", {}).get("mid"),
                        "uname": reply.get("member", {}).get("uname", ""),
                        "content": reply.get("content", {}).get("message", ""),
                        "ctime": reply.get("ctime", 0),
                        "like": reply.get("like", reply.get("count", 0)),
                        "parent": reply.get("parent", 0) or 0,
                        "root": reply.get("root", 0) or 0,
                        "dialog": reply.get("dialog", 0) or 0,
                    }
                    if comment_data["rpid"] not in seen_rpids:
                        comments_acc.append(comment_data)
                        seen_rpids.add(comment_data["rpid"])

                    for sub_reply in reply.get("replies") or []:
                        sub_comment = {
                            "rpid": sub_reply["rpid"],
                            "mid": sub_reply.get("member", {}).get("mid"),
                            "uname": sub_reply.get("member", {}).get("uname", ""),
                            "content": sub_reply.get("content", {}).get("message", ""),
                            "ctime": sub_reply.get("ctime", 0),
                            "like": sub_reply.get("like", sub_reply.get("count", 0)),
                            "parent": sub_reply.get("parent", reply["rpid"]) or reply["rpid"],
                            "root": sub_reply.get("root", reply["rpid"]) or reply["rpid"],
                            "dialog": sub_reply.get("dialog", 0) or 0,
                        }
                        if sub_comment["rpid"] not in seen_rpids:
                            comments_acc.append(sub_comment)
                            seen_rpids.add(sub_comment["rpid"])

                page += 1
                await asyncio.sleep(random.uniform(0.3, 0.6))

        except SecurityControlError:
            raise
        except Exception as exc:
            print(f"获取评论失败: {exc}")

        return comments_acc

    async def _get_reply_thread_map_via_http(
        self,
        oid: int,
        type_code: int,
        root_rpid: int,
        max_pages: int = 3,
    ) -> Dict[int, Dict]:
        """获取某个 root 评论线程下的评论映射，用于补齐“回复原文”。"""

        def _do_request(pn: int) -> Dict:
            headers = {
                "User-Agent": self._get_random_ua(),
                "Referer": "https://www.bilibili.com",
            }
            if self.cookie_string:
                headers["Cookie"] = self.cookie_string

            response = requests.get(
                "https://api.bilibili.com/x/v2/reply/reply",
                params={
                    "type": type_code,
                    "oid": oid,
                    "root": root_rpid,
                    "ps": 20,
                    "pn": pn,
                },
                headers=headers,
                timeout=10,
            )
            if response.status_code == 412:
                raise Exception("412 - The request was rejected because of the bilibili security control policy")
            response.raise_for_status()
            return response.json()

        def _normalize(item: Dict) -> Dict:
            member = item.get("member", {})
            content = item.get("content", {})
            return {
                "rpid": item.get("rpid"),
                "mid": member.get("mid"),
                "uname": member.get("uname", ""),
                "content": content.get("message", ""),
                "ctime": item.get("ctime", 0),
                "like": item.get("like", item.get("count", 0)),
                "parent": item.get("parent", 0) or 0,
                "root": item.get("root", 0) or 0,
                "dialog": item.get("dialog", 0) or 0,
            }

        mapping: Dict[int, Dict] = {}
        page = 1

        while page <= max_pages:
            payload = await self._retry_with_backoff(
                lambda: asyncio.to_thread(_do_request, page),
                max_retries=3,
                base_delay=0.5,
            )

            if payload.get("code") != 0:
                break

            data = payload.get("data") or {}

            root_item = data.get("root")
            if isinstance(root_item, dict) and root_item.get("rpid"):
                normalized = _normalize(root_item)
                if normalized.get("rpid") is not None:
                    mapping[int(normalized["rpid"])] = normalized

            replies = data.get("replies") or []
            if not replies:
                break

            for reply in replies:
                if not isinstance(reply, dict) or not reply.get("rpid"):
                    continue
                normalized = _normalize(reply)
                mapping[int(normalized["rpid"])] = normalized

                for sub_reply in reply.get("replies") or []:
                    if not isinstance(sub_reply, dict) or not sub_reply.get("rpid"):
                        continue
                    normalized_sub = _normalize(sub_reply)
                    mapping[int(normalized_sub["rpid"])] = normalized_sub

            page += 1

        return mapping

    async def enrich_reply_context(
        self,
        post: Dict,
        target_comments: List[Dict],
        all_comments: List[Dict],
    ) -> None:
        """如果 UP 主评论是回复，则补齐其回复的原评论内容。"""

        if not target_comments:
            return

        comment_type = int(post.get("comment_type") or 0)
        comment_oid = post.get("comment_oid")
        if not comment_type or comment_oid is None:
            return

        mapping: Dict[int, Dict] = {
            int(item["rpid"]): item
            for item in all_comments
            if isinstance(item, dict) and item.get("rpid") is not None
        }

        thread_cache: Dict[int, Dict[int, Dict]] = {}

        for item in target_comments:
            parent = int(item.get("parent") or 0)
            if parent == 0:
                continue

            parent_comment = mapping.get(parent)
            if parent_comment:
                item["reply_to"] = {
                    "uname": parent_comment.get("uname", ""),
                    "content": parent_comment.get("content", ""),
                }
                continue

            root = int(item.get("root") or 0)
            if root == 0:
                item["reply_to"] = {"uname": "", "content": "（未获取到被回复的原评论）"}
                continue

            thread_map = thread_cache.get(root)
            if thread_map is None:
                try:
                    thread_map = await self._get_reply_thread_map_via_http(
                        int(comment_oid),
                        comment_type,
                        root,
                    )
                except Exception as exc:
                    print(f"获取回复上下文失败(root={root}): {exc}")
                    thread_map = {}
                thread_cache[root] = thread_map

            parent_comment = thread_map.get(parent)
            if parent_comment:
                item["reply_to"] = {
                    "uname": parent_comment.get("uname", ""),
                    "content": parent_comment.get("content", ""),
                }
            else:
                item["reply_to"] = {"uname": "", "content": "（未获取到被回复的原评论）"}

    async def get_post_comments(self, post: Dict) -> List[Dict]:
        """获取某条内容（视频/动态）下的评论。"""

        if post.get("kind") == "video" and post.get("aid") is not None:
            return await self.get_video_comments(int(post["aid"]))

        comment_type = int(post.get("comment_type") or 0)
        comment_oid = post.get("comment_oid")
        if not comment_type or comment_oid is None:
            return []

        # 动态/相簿/专栏等，优先尝试页面抓取（成功率高），失败回退 /x/v2/reply
        if self.prefers_browser_fetch() and post.get("link"):
            try:
                comments = await self.browser_fetcher.get_page_comments(post["link"])
                if comments or self.fetch_mode == "browser":
                    return comments
            except Exception as exc:
                print(f"浏览器抓取评论失败: {exc}")
                if self.fetch_mode == "browser":
                    return []

        return await self._get_reply_comments_via_http(int(comment_oid), comment_type)

    def filter_up_comments(self, comments: List[Dict], up_uid: int) -> List[Dict]:
        """筛选出UP主的评论"""

        up_comments = []
        up_uid_str = str(up_uid)
        for comment_item in comments:
            if str(comment_item.get("mid")) == up_uid_str:
                up_comments.append(comment_item)
        return sorted(up_comments, key=lambda item: item.get("ctime", 0), reverse=True)

    async def close(self):
        if self.browser_fetcher:
            await self.browser_fetcher.close()
