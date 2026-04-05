import asyncio
import random
from typing import List, Dict, Optional
from bilibili_api import user, comment, Credential
from bilibili_api.comment import CommentResourceType
from browser_fetcher import BrowserBilibiliFetcher
from config import (
    BILI_COOKIE,
    BILI_SESSDATA,
    BILI_BILI_JCT,
    BILI_BUVID3,
    BILI_BUVID4,
    BILI_DEDEUSERID,
    BILI_FETCH_MODE,
    BILI_BROWSER_EXECUTABLE,
    BILI_BROWSER_HEADLESS,
    BILI_BROWSER_TIMEOUT_MS,
    COMMENT_MAX_PAGES_AUTH,
    COMMENT_MAX_PAGES_GUEST,
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
        except Exception as e:
            if self._is_auth_error(e):
                print(f"⚠️ B站登录态校验失败: {e}")
                return None
            raise

    async def get_user_profile(self, uid: int) -> Optional[Dict]:
        """获取指定 UID 的用户信息，用于通知文案等非关键路径。"""
        try:
            info = await user.User(uid, credential=self.credential).get_user_info()
        except Exception as e:
            print(f"⚠️ 获取UP主信息失败: {e}")
            return None

        return {
            "mid": info.get("mid", uid),
            "uname": info.get("name") or info.get("uname"),
        }
    
    async def _retry_with_backoff(self, func, max_retries: int = 3, base_delay: float = 1.0):
        """
        带指数退避的重试机制
        
        Args:
            func: 要执行的异步函数
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
        
        Returns:
            函数执行结果
        
        Raises:
            最后一次异常
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                last_exception = e
                if self._is_security_block(e):
                    raise SecurityControlError(
                        f"B站触发 412 风控: {e}",
                        cooldown_seconds=120,
                    ) from e
                error_msg = str(e).lower()
                
                # 判断是否是需要重试的错误
                retryable_errors = [
                    'timeout', 'connection', 'ssl', 'reset', 'refused',
                    'too many requests', '429', '503', '502', '500',
                    'verify', 'certificate', 'handshake'
                ]
                
                is_retryable = any(err in error_msg for err in retryable_errors)
                
                if not is_retryable and attempt < max_retries - 1:
                    # 检查是否是HTML响应（包含<html或<script）
                    is_retryable = '<html' in str(e) or '<script' in str(e)
                
                if not is_retryable:
                    # 非可重试错误，直接抛出
                    raise
                
                if attempt < max_retries - 1:
                    # 计算指数退避延迟（1s, 2s, 4s...）加上随机抖动
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    print(f"  ⚠️  请求失败，{delay:.1f}秒后重试({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(delay)
                else:
                    print(f"  ❌ 重试{max_retries}次后仍然失败: {e}")
        
        raise last_exception
    
    async def get_latest_video(self, uid: int) -> Optional[Dict]:
        """
        获取UP主最新发布的视频（带重试机制）
        """
        if self.prefers_browser_fetch():
            try:
                video = await self.browser_fetcher.get_latest_video(uid)
                if video:
                    return video
                if self.fetch_mode == "browser":
                    return None
            except Exception as e:
                print(f"浏览器抓取最新视频失败: {e}")
                if self.fetch_mode == "browser":
                    return None

        async def _fetch():
            # 添加随机延迟，避免请求过于规律
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            u = user.User(uid, credential=self.credential)
            # 获取视频列表，只取最新1个
            videos = await u.get_videos(ps=1)
            
            if videos and videos.get('list', {}).get('vlist'):
                video_data = videos['list']['vlist'][0]
                return {
                    'bvid': video_data['bvid'],
                    'aid': video_data['aid'],
                    'title': video_data['title'],
                    'description': video_data.get('description', ''),
                    'created': video_data['created'],
                    'link': f"https://www.bilibili.com/video/{video_data['bvid']}",
                }
            return None
        
        try:
            return await self._retry_with_backoff(_fetch, max_retries=3, base_delay=1.0)
        except SecurityControlError:
            raise
        except Exception as e:
            print(f"获取最新视频失败: {e}")
            return None
    
    async def get_video_comments(self, aid: int) -> List[Dict]:
        """
        获取视频的评论列表（使用get_comments_lazy新接口，带重试机制）
        """
        if self.prefers_browser_fetch():
            try:
                comments = await self.browser_fetcher.get_video_comments(
                    f"https://www.bilibili.com/video/av{aid}"
                )
                if comments:
                    return comments
                if self.fetch_mode == "browser":
                    return comments
            except Exception as e:
                print(f"浏览器抓取评论失败: {e}")
                if self.fetch_mode == "browser":
                    return []

        comments = []
        seen_rpids = set()
        page = 1
        max_pages = self._get_comment_page_limit()
        pag = ""  # pagination offset
        
        async def _fetch_page(page_offset: str):
            """获取单页评论"""
            return await comment.get_comments_lazy(
                oid=aid,
                type_=CommentResourceType.VIDEO,
                offset=page_offset,
                credential=self.credential
            )
        
        try:
            while page <= max_pages:
                # 使用重试机制获取评论
                c = await self._retry_with_backoff(
                    lambda: _fetch_page(pag),
                    max_retries=3,
                    base_delay=0.5
                )
                
                # 获取下一页的offset
                if 'cursor' in c and 'pagination_reply' in c['cursor']:
                    pag = c['cursor']['pagination_reply'].get('next_offset', '')
                else:
                    pag = ""
                
                replies = c.get('replies')
                if not replies:
                    break
                
                for reply in replies:
                    comment_data = {
                        'rpid': reply['rpid'],
                        'mid': reply['member']['mid'],
                        'uname': reply['member']['uname'],
                        'content': reply['content']['message'],
                        'ctime': reply['ctime'],
                        'like': reply['count'],
                        'parent': reply.get('parent', 0),
                    }
                    if comment_data['rpid'] not in seen_rpids:
                        comments.append(comment_data)
                        seen_rpids.add(comment_data['rpid'])
                    
                    # 获取楼中楼回复
                    if reply.get('replies'):
                        for sub_reply in reply['replies']:
                            sub_comment = {
                                'rpid': sub_reply['rpid'],
                                'mid': sub_reply['member']['mid'],
                                'uname': sub_reply['member']['uname'],
                                'content': sub_reply['content']['message'],
                                'ctime': sub_reply['ctime'],
                                'like': sub_reply['count'],
                                'parent': reply['rpid'],
                            }
                            if sub_comment['rpid'] not in seen_rpids:
                                comments.append(sub_comment)
                                seen_rpids.add(sub_comment['rpid'])
                
                page += 1
                if not pag:  # 没有更多页面了
                    break
                
                # 页间延迟，避免请求过快
                await asyncio.sleep(random.uniform(0.3, 0.6))
                
        except Exception as e:
            if isinstance(e, SecurityControlError):
                raise
            print(f"获取评论失败: {e}")
        
        return comments
    
    def filter_up_comments(self, comments: List[Dict], up_uid: int) -> List[Dict]:
        """
        筛选出UP主的评论
        """
        up_comments = []
        up_uid_str = str(up_uid)
        for comment in comments:
            if str(comment['mid']) == up_uid_str:
                up_comments.append(comment)
        return sorted(up_comments, key=lambda item: item['ctime'], reverse=True)

    async def close(self):
        if self.browser_fetcher:
            await self.browser_fetcher.close()
