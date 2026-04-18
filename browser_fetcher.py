import os
import platform
from typing import Dict, List, Optional


SPACE_VIDEO_RESPONSE_KEYWORD = "/x/space/wbi/arc/search"
SPACE_DYNAMIC_RESPONSE_KEYWORD = "/x/polymer/web-dynamic/v1/feed/space"
LOGIN_STATUS_URL = "https://api.bilibili.com/x/web-interface/nav"

STEALTH_SCRIPT_TEMPLATE = """
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
});
Object.defineProperty(navigator, 'platform', {
  get: () => '__PLATFORM__',
});
Object.defineProperty(navigator, 'languages', {
  get: () => ['zh-CN', 'zh'],
});
window.chrome = window.chrome || { runtime: {} };
"""


def get_stealth_platform_value(system_name: Optional[str] = None) -> str:
    detected_system = (system_name or platform.system()).strip().lower()
    if detected_system == "windows":
        return "Win32"
    if detected_system == "darwin":
        return "MacIntel"
    return "Linux x86_64"


def build_stealth_init_script(system_name: Optional[str] = None) -> str:
    return STEALTH_SCRIPT_TEMPLATE.replace(
        "__PLATFORM__",
        get_stealth_platform_value(system_name),
    )


STEALTH_INIT_SCRIPT = build_stealth_init_script()

COMMENT_COMPONENT_EXTRACTION_SCRIPT = """
() => {
  const host = document.querySelector('bili-comments');
  if (!host || !host.shadowRoot) {
    return [];
  }

  const threads = Array.from(host.shadowRoot.querySelectorAll('bili-comment-thread-renderer'));
  return threads.map((thread) => {
    const threadData = thread.__data || null;
    const repliesRenderer = thread.shadowRoot
      ? thread.shadowRoot.querySelector('bili-comment-replies-renderer')
      : null;
    const list = repliesRenderer ? (repliesRenderer.__list || []) : [];
    const newItems = repliesRenderer ? (repliesRenderer.__newItems || []) : [];

    return {
      thread: threadData,
      replies: [...list, ...newItems],
    };
  });
}
"""


def build_playwright_cookies(cookie_string: str) -> List[Dict]:
    cookies: List[Dict] = []
    for part in (cookie_string or "").split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".bilibili.com",
                "path": "/",
            }
        )
    return cookies


def extract_latest_video_from_space_payload(payload: Dict) -> Optional[Dict]:
    vlist = payload.get("data", {}).get("list", {}).get("vlist", [])
    if not vlist:
        return None

    video_data = vlist[0]
    return {
        "bvid": video_data["bvid"],
        "aid": video_data["aid"],
        "title": video_data["title"],
        "description": video_data.get("description", ""),
        "created": video_data["created"],
        "link": f"https://www.bilibili.com/video/{video_data['bvid']}",
    }


def _normalize_single_comment(comment: Dict) -> Optional[Dict]:
    if not comment:
        return None

    member = comment.get("member", {})
    content = comment.get("content", {})
    parent = comment.get("parent", 0)
    if parent in (None, ""):
        parent = 0

    return {
        "rpid": comment["rpid"],
        "mid": member.get("mid", comment.get("mid")),
        "uname": member.get("uname", ""),
        "content": content.get("message", ""),
        "ctime": comment.get("ctime", 0),
        "like": comment.get("like", comment.get("count", 0)),
        "parent": parent,
    }


def normalize_comment_component_payloads(payloads: List[Dict]) -> List[Dict]:
    comments: List[Dict] = []
    seen_rpids = set()

    for payload in payloads:
        thread_comment = _normalize_single_comment(payload.get("thread"))
        if thread_comment and thread_comment["rpid"] not in seen_rpids:
            comments.append(thread_comment)
            seen_rpids.add(thread_comment["rpid"])

        for reply in payload.get("replies", []):
            reply_comment = _normalize_single_comment(reply)
            if reply_comment and reply_comment["rpid"] not in seen_rpids:
                comments.append(reply_comment)
                seen_rpids.add(reply_comment["rpid"])

    return comments


def _normalize_bilibili_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.bilibili.com{url}"
    return url


def _build_dynamic_title(item: Dict) -> str:
    modules = item.get("modules", {})
    module_dynamic = modules.get("module_dynamic", {})
    major = module_dynamic.get("major", {})
    major_type = major.get("type")

    if major_type == "MAJOR_TYPE_ARCHIVE":
        archive = major.get("archive", {})
        return archive.get("title") or "投稿视频"

    if major_type == "MAJOR_TYPE_UGC_SEASON":
        season = major.get("ugc_season", {})
        return season.get("title") or "合集更新"

    if major_type == "MAJOR_TYPE_UPOWER_COMMON":
        upower = major.get("upower_common", {})
        prefix = upower.get("title_prefix") or ""
        title = upower.get("title") or "充电专属"
        return f"{prefix}{title}".strip() or "充电专属"

    # opus 图文动态
    if major_type == "MAJOR_TYPE_OPUS":
        opus = major.get("opus", {})
        title = opus.get("title")
        if title:
            return title

    desc = module_dynamic.get("desc", {}) or {}
    text = (desc.get("text") or "").strip()
    if text:
        return text

    return "UP主动态"


def extract_latest_post_from_space_dynamic_payload(payload: Dict) -> Optional[Dict]:
    items = payload.get("data", {}).get("items", [])
    if not items:
        return None

    def pub_ts(item: Dict) -> int:
        modules = item.get("modules", {})
        author = modules.get("module_author", {})
        return int(author.get("pub_ts") or 0)

    # space feed 可能包含置顶动态，直接选 pub_ts 最大的那条
    latest_item = max(items, key=pub_ts)

    modules = latest_item.get("modules", {})
    author = modules.get("module_author", {})
    created = int(author.get("pub_ts") or 0)

    basic = latest_item.get("basic", {})
    comment_type = int(basic.get("comment_type") or 0)
    comment_oid = basic.get("comment_id_str")
    dynamic_id = latest_item.get("id_str")

    link = _normalize_bilibili_url(basic.get("jump_url") or "")
    module_dynamic = modules.get("module_dynamic", {})
    major = module_dynamic.get("major", {})
    major_type = major.get("type")

    kind = "dynamic"
    title = _build_dynamic_title(latest_item)

    video_bvid = None
    video_aid = None

    if major_type == "MAJOR_TYPE_ARCHIVE":
        archive = major.get("archive", {})
        video_bvid = archive.get("bvid")
        video_aid = archive.get("aid")
        kind = "video"
        title = archive.get("title") or title
        link = _normalize_bilibili_url(archive.get("jump_url") or link)

    if major_type == "MAJOR_TYPE_UGC_SEASON":
        season = major.get("ugc_season", {})
        video_aid = season.get("aid")
        kind = "video"
        title = season.get("title") or title
        link = _normalize_bilibili_url(season.get("jump_url") or link)

    if not link:
        # 兜底：不同 major 的 jump_url 字段结构不同
        for key in ("opus", "draw", "article", "common", "upower_common"):
            entry = major.get(key)
            if isinstance(entry, dict) and entry.get("jump_url"):
                link = _normalize_bilibili_url(entry.get("jump_url"))
                break

    if kind == "video":
        if video_aid is None and comment_type == 1 and comment_oid is not None:
            video_aid = int(comment_oid)
        if comment_oid is None and video_aid is not None:
            comment_oid = str(video_aid)

        if video_bvid:
            post_key = f"video:{video_bvid}"
        else:
            post_key = f"video:av{video_aid}" if video_aid is not None else f"dynamic:{dynamic_id}"
    else:
        post_key = f"dynamic:{dynamic_id}" if dynamic_id else f"dynamic:{comment_type}:{comment_oid}"

    if comment_oid is None:
        return None

    return {
        "kind": kind,
        "post_key": post_key,
        "title": title,
        "created": created,
        "link": link,
        "dynamic_id": dynamic_id,
        "comment_type": comment_type,
        "comment_oid": int(comment_oid),
        "bvid": video_bvid,
        "aid": int(video_aid) if video_aid is not None else None,
    }


def get_browser_executable_candidates(system_name: Optional[str] = None) -> List[str]:
    detected_system = (system_name or platform.system()).strip().lower()
    if detected_system == "windows":
        candidates: List[str] = []
        windows_roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        browser_suffixes = [
            ("Google", "Chrome", "Application", "chrome.exe"),
            ("Chromium", "Application", "chrome.exe"),
        ]
        for root in windows_roots:
            if not root:
                continue
            for suffix in browser_suffixes:
                candidates.append(os.path.join(root, *suffix))
        return candidates

    return [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]


class BrowserBilibiliFetcher:
    def __init__(
        self,
        cookie_string: str = "",
        executable_path: str = "",
        headless: bool = True,
        timeout_ms: int = 30000,
    ):
        self.cookie_string = cookie_string or ""
        self.executable_path = self._resolve_executable_path(executable_path)
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._cookies_added = False

    def is_available(self) -> bool:
        return True

    def _resolve_executable_path(self, executable_path: str) -> str:
        if executable_path and os.path.exists(executable_path):
            return executable_path
        return self._detect_chrome_path()

    def _detect_chrome_path(self) -> str:
        for candidate in get_browser_executable_candidates():
            if os.path.exists(candidate):
                return candidate
        return ""

    async def _ensure_context(self):
        if self._context:
            return self._context

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_options = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self.executable_path:
            launch_options["executable_path"] = self.executable_path
        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context(
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 2000},
        )
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)

        if self.cookie_string and not self._cookies_added:
            cookies = build_playwright_cookies(self.cookie_string)
            if cookies:
                await self._context.add_cookies(cookies)
                self._cookies_added = True

        return self._context

    async def get_latest_video(self, uid: int) -> Optional[Dict]:
        context = await self._ensure_context()
        page = await context.new_page()
        try:
            async with page.expect_response(
                lambda response: SPACE_VIDEO_RESPONSE_KEYWORD in response.url
                and f"mid={uid}" in response.url,
                timeout=self.timeout_ms,
            ) as response_info:
                await page.goto(
                    f"https://space.bilibili.com/{uid}/video",
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

            response = await response_info.value
            payload = await response.json()
            return extract_latest_video_from_space_payload(payload)
        finally:
            await page.close()

    async def get_latest_post(self, uid: int) -> Optional[Dict]:
        """从空间动态页抓取“最新发布内容”。

        相比 /video 列表，space feed 往往更容易覆盖：动态、合集更新、充电相关内容等。
        """

        context = await self._ensure_context()
        page = await context.new_page()
        try:
            async with page.expect_response(
                lambda response: SPACE_DYNAMIC_RESPONSE_KEYWORD in response.url
                and f"host_mid={uid}" in response.url,
                timeout=self.timeout_ms,
            ) as response_info:
                await page.goto(
                    f"https://space.bilibili.com/{uid}/dynamic",
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

            response = await response_info.value
            payload = await response.json()
            return extract_latest_post_from_space_dynamic_payload(payload)
        finally:
            await page.close()

    async def get_page_comments(self, link: str) -> List[Dict]:
        context = await self._ensure_context()
        page = await context.new_page()
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.72)")
            await page.wait_for_function(
                """
                () => {
                  const host = document.querySelector('bili-comments');
                  return Boolean(
                    host &&
                    host.shadowRoot &&
                    host.shadowRoot.querySelectorAll('bili-comment-thread-renderer').length > 0
                  );
                }
                """,
                timeout=self.timeout_ms,
            )
            await page.wait_for_timeout(1500)
            payloads = await page.evaluate(COMMENT_COMPONENT_EXTRACTION_SCRIPT)
            return normalize_comment_component_payloads(payloads)
        finally:
            await page.close()

    async def get_video_comments(self, video_link: str) -> List[Dict]:
        # backward compatible wrapper
        return await self.get_page_comments(video_link)

    async def get_login_hint(self) -> Optional[Dict]:
        cookies = build_playwright_cookies(self.cookie_string)
        if not cookies:
            return None

        context = await self._ensure_context()
        page = await context.new_page()
        try:
            response = await page.goto(
                LOGIN_STATUS_URL,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            if not response:
                return None

            payload = await response.json()
            data = payload.get("data", {})
            if payload.get("code") != 0 or not data.get("isLogin"):
                return None

            return {
                "mid": data.get("mid"),
                "uname": data.get("uname"),
            }
        finally:
            await page.close()

    async def close(self):
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
