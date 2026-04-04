#!/usr/bin/env python3
import asyncio
import time
from datetime import datetime, time as dt_time
from bili_api import BilibiliAPI, SecurityControlError
from feishu_bot import FeishuBot
from storage import CommentStorage
from config import (
    UP_UID,
    FEISHU_WEBHOOK,
    DATA_FILE,
    SECURITY_COOLDOWN_SECONDS,
)


def get_check_interval_for_datetime(current: datetime) -> int:
    now = current.time()
    peak_start = dt_time(9, 20)
    peak_end = dt_time(9, 40)
    daytime_morning_start = dt_time(9, 0)
    daytime_morning_end = dt_time(11, 30)
    daytime_afternoon_start = dt_time(13, 0)
    daytime_afternoon_end = dt_time(15, 0)

    if peak_start <= now <= peak_end:
        return 30
    if daytime_morning_start <= now <= daytime_morning_end:
        return 180
    if daytime_afternoon_start <= now <= daytime_afternoon_end:
        return 180
    return 1800


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
        print(f"🤖 飞书Webhook: {FEISHU_WEBHOOK[:50]}...")
        print("⏱️  检查策略: 09:20-09:40 每10秒, 09:00-11:30/13:00-15:00 每3分钟, 其余每30分钟")
        print(f"💾 数据文件: {DATA_FILE}")
        print(f"🔐 B站登录态: {'已配置' if self.bilibili.has_auth() else '未配置'}")
        print(f"🌐 抓取模式: {self.bilibili.fetch_mode}")
        print("=" * 60)
    
    async def run(self):
        """运行监控循环"""
        print("\n🚀 启动监控...\n")
        await self._check_login_status()
        
        # 发送启动通知
        self.feishu.send_text(
            f"🚀 B站评论监控已启动\n"
            f"👤 监控UP主: {UP_UID}\n"
            f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        check_count = 0
        
        try:
            while self.running:
                now = time.time()
                if now < self.cooldown_until:
                    wait_seconds = max(1, int(self.cooldown_until - now))
                    print(f"\n🛡️ 风控冷却中，还需等待 {wait_seconds} 秒")
                    await asyncio.sleep(min(wait_seconds, get_check_interval_for_datetime(datetime.now())))
                    continue

                check_count += 1
                print(f"\n🔍 第 {check_count} 次检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                await self._check_once()
                
                # 等待下次检查
                next_interval = get_check_interval_for_datetime(datetime.now())
                print(f"⏳ 当前时段下次检查间隔: {next_interval} 秒")
                await asyncio.sleep(next_interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 监控已停止")
            self.feishu.send_text(
                f"👋 B站评论监控已停止\n"
                f"📊 共检查 {check_count} 次\n"
                f"⏰ 停止时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        finally:
            await self.bilibili.close()
    
    async def _check_once(self):
        """执行一次检查"""
        try:
            # 1. 获取最新视频
            video = await self.bilibili.get_latest_video(UP_UID)
            if not video:
                print("❌ 无法获取最新视频")
                return
            
            print(f"🎬 最新视频: {video['title'][:50]}...")
            print(f"🔗 链接: {video['link']}")
            
            # 2. 检查是否为新视频
            if self.storage.is_new_video(video['bvid']):
                self.storage.switch_video(video['bvid'])
                # 新视频发送通知
                self.feishu.send_text(
                    f"🎬 检测到UP主发布新视频！\n"
                    f"📺 {video['title']}\n"
                    f"🔗 {video['link']}"
                )
            
            # 3. 获取视频评论
            comments = await self.bilibili.get_video_comments(video['aid'])
            if not comments:
                print("📭 暂无评论")
                return
            
            print(f"💬 本轮获取到 {len(comments)} 条最新评论/回复")
            
            # 4. 筛选UP主的评论
            up_comments = self.bilibili.filter_up_comments(comments, UP_UID)
            if not up_comments:
                print("📝 UP主暂未发表评论")
                return
            
            print(f"📝 找到 {len(up_comments)} 条UP主评论")
            
            # 5. 筛选出新评论（未通知过的）
            new_comments = [c for c in up_comments if not self.storage.is_notified(c['rpid'])]
            
            if not new_comments:
                print("✅ 没有新评论需要通知")
                return
            
            print(f"🆕 发现 {len(new_comments)} 条新评论")
            
            # 6. 发送通知
            video_info = {
                'bvid': video['bvid'],
                'title': video['title'],
                'link': video['link'],
            }
            
            if len(new_comments) == 1:
                success = self.feishu.send_up_comment(video_info, new_comments[0])
                if success:
                    self.storage.mark_notified(new_comments[0]['rpid'])
            else:
                success = self.feishu.send_multiple_comments(video_info, new_comments)
                if success:
                    rpids = [c['rpid'] for c in new_comments]
                    self.storage.mark_multiple_notified(rpids)
        except SecurityControlError as e:
            self.cooldown_until = time.time() + SECURITY_COOLDOWN_SECONDS
            print(f"🛡️ 触发 B站风控，进入 {SECURITY_COOLDOWN_SECONDS} 秒冷却: {e}")
            if time.time() - self.last_block_alert_at > SECURITY_COOLDOWN_SECONDS:
                self.feishu.send_text(
                    f"⚠️ B站评论监控触发风控\n"
                    f"👤 UP主: {UP_UID}\n"
                    f"⏸️ 冷却时间: {SECURITY_COOLDOWN_SECONDS} 秒\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self.last_block_alert_at = time.time()
        except Exception as e:
            print(f"❌ 检查过程出错: {e}")

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
                "⚠️ 已检测到 B站 Cookie，但登录态校验失败。\n"
                "可能是 Cookie 已过期，评论抓取准确率会下降。"
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
