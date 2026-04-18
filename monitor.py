#!/usr/bin/env python3
import asyncio
import time
from datetime import datetime, time as dt_time

from bili_api import BilibiliAPI, SecurityControlError
from config import (
    AFTERNOON_END,
    AFTERNOON_INTERVAL_SECONDS,
    AFTERNOON_START,
    DATA_FILE,
    DEFAULT_INTERVAL_SECONDS,
    FEISHU_WEBHOOK,
    MORNING_END,
    MORNING_INTERVAL_SECONDS,
    MORNING_START,
    PEAK_END,
    PEAK_INTERVAL_SECONDS,
    PEAK_START,
    SECURITY_COOLDOWN_SECONDS,
    TRACKED_THREAD_MAX_PAGES,
    TRACKED_THREAD_MAX_ROOTS,
    TRACKED_THREAD_SCAN_ENABLED,
    UP_UID,
)
from feishu_bot import FeishuBot
from storage import CommentStorage


def get_check_interval_for_datetime(current: datetime) -> int:
    now = current.time()

    if PEAK_START <= now < PEAK_END:
        return PEAK_INTERVAL_SECONDS
    if MORNING_START <= now < MORNING_END:
        return MORNING_INTERVAL_SECONDS
    if AFTERNOON_START <= now < AFTERNOON_END:
        return AFTERNOON_INTERVAL_SECONDS
    return DEFAULT_INTERVAL_SECONDS


def format_schedule_time(value: dt_time) -> str:
    return value.strftime("%H:%M")


def format_interval_label(seconds: int) -> str:
    if seconds % 60 == 0:
        return f"{seconds // 60}分钟"
    return f"{seconds}秒"


def get_check_schedule_description() -> str:
    return (
        f"{format_schedule_time(PEAK_START)}-{format_schedule_time(PEAK_END)} 每{format_interval_label(PEAK_INTERVAL_SECONDS)}, "
        f"{format_schedule_time(MORNING_START)}-{format_schedule_time(MORNING_END)} 每{format_interval_label(MORNING_INTERVAL_SECONDS)}, "
        f"{format_schedule_time(AFTERNOON_START)}-{format_schedule_time(AFTERNOON_END)} 每{format_interval_label(AFTERNOON_INTERVAL_SECONDS)}, "
        f"其余每{format_interval_label(DEFAULT_INTERVAL_SECONDS)}"
    )


def get_masked_webhook_status(webhook_url: str) -> str:
    return "已配置" if webhook_url.strip() else "未配置"


def format_monitored_up_label(uid: int, profile) -> str:
    if profile and profile.get("uname"):
        resolved_uid = profile.get("mid") or uid
        return f"{profile['uname']} (UID: {resolved_uid})"
    return str(uid)


def get_post_kind_label(kind: str) -> str:
    return "视频" if kind == "video" else "动态"


def get_post_kind_emoji(kind: str) -> str:
    return "🎬" if kind == "video" else "📝"


class BilibiliMonitor:
    """B站UP主评论监控器"""

    def __init__(self):
        self.bilibili = BilibiliAPI()
        self.feishu = FeishuBot(FEISHU_WEBHOOK)
        self.storage = CommentStorage(DATA_FILE)
        self.running = True
        self.cooldown_until = 0.0
        self.last_block_alert_at = 0.0
        self.login_status_checked = False

        print("=" * 60)
        print("🎬 B站UP主评论监控器")
        print("=" * 60)
        print(f"👤 监控UP主UID: {UP_UID}")
        print(f"🤖 飞书Webhook: {get_masked_webhook_status(FEISHU_WEBHOOK)}")
        print(f"⏱️  检查策略: {get_check_schedule_description()}")
        print(f"💾 数据文件: {DATA_FILE}")
        print(f"🔐 B站登录态: {'已配置' if self.bilibili.has_auth() else '未配置'}")
        print(f"🌐 抓取模式: {self.bilibili.fetch_mode}")
        print("=" * 60)

    async def run(self):
        """运行监控循环"""

        print("\n🚀 启动监控...\n")
        await self._check_login_status()
        monitored_up_label = format_monitored_up_label(
            UP_UID,
            await self.bilibili.get_user_profile(UP_UID),
        )

        self.feishu.send_text(
            "🚀 B站评论监控已启动\n"
            f"👤 监控UP主: {monitored_up_label}\n"
            f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        check_count = 0

        try:
            while self.running:
                now = time.time()
                if now < self.cooldown_until:
                    wait_seconds = max(1, int(self.cooldown_until - now))
                    print(f"\n🛡️ 风控冷却中，还需等待 {wait_seconds} 秒")
                    await asyncio.sleep(
                        min(wait_seconds, get_check_interval_for_datetime(datetime.now()))
                    )
                    continue

                check_count += 1
                print(
                    f"\n🔍 第 {check_count} 次检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

                await self._check_once()

                next_interval = get_check_interval_for_datetime(datetime.now())
                print(f"⏳ 当前时段下次检查间隔: {next_interval} 秒")
                await asyncio.sleep(next_interval)

        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            self.feishu.send_text(
                "👋 B站评论监控已停止\n"
                f"📊 共检查 {check_count} 次\n"
                f"⏰ 停止时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        finally:
            await self.bilibili.close()

    async def _check_once(self):
        """执行一次检查"""

        try:
            post = await self.bilibili.get_latest_post(UP_UID)
            if not post:
                print("❌ 无法获取最新内容")
                return

            kind = post.get("kind") or "video"
            kind_label = get_post_kind_label(kind)
            kind_emoji = get_post_kind_emoji(kind)

            title = post.get("title") or ""
            link = post.get("link") or ""

            print(f"{kind_emoji} 最新{kind_label}: {title[:50]}...")
            print(f"🔗 链接: {link}")

            post_key = post.get("post_key")
            if post_key and self.storage.is_new_post(post_key):
                self.storage.switch_post(post_key)
                self.feishu.send_text(
                    f"{kind_emoji} 检测到UP主发布新{kind_label}！\n" f"📌 {title}\n" f"🔗 {link}"
                )

            comments = await self.bilibili.get_post_comments(post)
            if not comments:
                print("📭 暂无评论")
                return

            print(f"💬 本轮获取到 {len(comments)} 条最新评论/回复")

            tracked_up_comments = []
            if TRACKED_THREAD_SCAN_ENABLED:
                tracked_up_comments = await self.bilibili.get_up_replies_from_tracked_threads(
                    post,
                    self.storage.get_tracked_roots(),
                    UP_UID,
                    TRACKED_THREAD_MAX_PAGES,
                )

            up_comments = self.bilibili.filter_up_comments(comments, UP_UID)
            if tracked_up_comments:
                merged = {comment["rpid"]: comment for comment in up_comments}
                for comment in tracked_up_comments:
                    merged.setdefault(comment["rpid"], comment)
                up_comments = sorted(
                    merged.values(),
                    key=lambda item: item.get("ctime", 0),
                    reverse=True,
                )

            if not up_comments:
                print("📝 UP主暂未发表评论")
                return

            # 记录被回复的根评论，后续补齐同线程多次回复
            if TRACKED_THREAD_SCAN_ENABLED:
                roots = []
                for comment in up_comments:
                    parent = int(comment.get("parent") or 0)
                    if parent == 0:
                        continue
                    root = int(comment.get("root") or parent)
                    roots.append(root)
                if roots:
                    self.storage.track_roots(roots, TRACKED_THREAD_MAX_ROOTS)

            print(f"📝 找到 {len(up_comments)} 条UP主评论")

            new_comments = [
                comment for comment in up_comments if not self.storage.is_notified(comment["rpid"])
            ]

            if not new_comments:
                print("✅ 没有新评论需要通知")
                return

            print(f"🆕 发现 {len(new_comments)} 条新评论")

            post_info = {
                "kind": kind,
                "title": title,
                "link": link,
                "comment_type": post.get("comment_type"),
                "comment_oid": post.get("comment_oid"),
            }

            await self.bilibili.enrich_reply_context(post, new_comments, comments)

            if len(new_comments) == 1:
                success = self.feishu.send_up_comment(post_info, new_comments[0])
                if success:
                    self.storage.mark_notified(new_comments[0]["rpid"])
            else:
                success = self.feishu.send_multiple_comments(post_info, new_comments)
                if success:
                    rpids = [comment["rpid"] for comment in new_comments]
                    self.storage.mark_multiple_notified(rpids)

        except SecurityControlError as exc:
            self.cooldown_until = time.time() + SECURITY_COOLDOWN_SECONDS
            print(f"🛡️ 触发 B站风控，进入 {SECURITY_COOLDOWN_SECONDS} 秒冷却: {exc}")
            if time.time() - self.last_block_alert_at > SECURITY_COOLDOWN_SECONDS:
                self.feishu.send_text(
                    "⚠️ B站评论监控触发风控\n"
                    f"👤 UP主: {UP_UID}\n"
                    f"⏸️ 冷却时间: {SECURITY_COOLDOWN_SECONDS} 秒\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self.last_block_alert_at = time.time()
        except Exception as exc:
            print(f"❌ 检查过程出错: {exc}")

    async def _check_login_status(self):
        if self.login_status_checked:
            return

        self.login_status_checked = True
        info = await self.bilibili.validate_login()
        if info:
            print(f"✅ B站登录态有效，当前账号: {info['uname']} ({info['mid']})")
            return

        if self.bilibili.has_auth():
            warning = (
                "⚠️ 已检测到 B站 Cookie，但登录态校验失败。\n" "可能是 Cookie 已过期，评论抓取准确率会下降。"
            )
            print(warning)
            self.feishu.send_text(warning)
        else:
            print("⚠️ 未配置 B站 Cookie，将以匿名模式运行")

    def stop(self):
        """停止监控"""

        self.running = False


async def main():
    monitor = BilibiliMonitor()
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
