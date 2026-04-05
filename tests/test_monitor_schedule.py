import unittest
from datetime import datetime, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch

from monitor import (
    AFTERNOON_INTERVAL_SECONDS,
    AFTERNOON_START,
    AFTERNOON_END,
    BilibiliMonitor,
    DEFAULT_INTERVAL_SECONDS,
    MORNING_INTERVAL_SECONDS,
    MORNING_START,
    MORNING_END,
    PEAK_END,
    PEAK_INTERVAL_SECONDS,
    PEAK_START,
    get_check_interval_for_datetime,
)


class MonitorScheduleTestCase(unittest.TestCase):
    def test_peak_window_uses_thirty_seconds(self):
        dt = datetime(2026, 4, 1, 9, 25, 0)

        self.assertEqual(get_check_interval_for_datetime(dt), 30)

    def test_morning_and_afternoon_windows_use_three_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 9, 40, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 10, 45, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 14, 0, 0)), 180)

    def test_other_times_use_thirty_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 8, 30, 0)), 1800)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 16, 0, 0)), 1800)

    def test_schedule_can_be_overridden_from_config_constants(self):
        with patch("monitor.PEAK_START", dt_time(8, 0)), patch(
            "monitor.PEAK_END", dt_time(8, 20)
        ), patch("monitor.PEAK_INTERVAL_SECONDS", 15), patch(
            "monitor.MORNING_START", dt_time(8, 20)
        ), patch(
            "monitor.MORNING_END", dt_time(10, 0)
        ), patch(
            "monitor.MORNING_INTERVAL_SECONDS", 120
        ), patch(
            "monitor.AFTERNOON_START", dt_time(14, 0)
        ), patch(
            "monitor.AFTERNOON_END", dt_time(16, 0)
        ), patch(
            "monitor.AFTERNOON_INTERVAL_SECONDS", 240
        ), patch("monitor.DEFAULT_INTERVAL_SECONDS", 900):
            self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 8, 10, 0)), 15)
            self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 9, 0, 0)), 120)
            self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 15, 0, 0)), 240)
            self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 18, 0, 0)), 900)


class MonitorStartupBannerTestCase(unittest.TestCase):
    @patch("builtins.print")
    @patch("monitor.CommentStorage")
    @patch("monitor.FeishuBot")
    @patch("monitor.BilibiliAPI")
    def test_startup_banner_masks_webhook_and_uses_thirty_second_schedule(
        self,
        mock_bilibili_api,
        mock_feishu_bot,
        mock_comment_storage,
        mock_print,
    ):
        api_instance = mock_bilibili_api.return_value
        api_instance.has_auth.return_value = True
        api_instance.fetch_mode = "browser"
        mock_feishu_bot.return_value = MagicMock()
        mock_comment_storage.return_value = MagicMock()

        with patch(
            "monitor.FEISHU_WEBHOOK",
            "https://open.feishu.cn/open-apis/bot/v2/hook/super-secret-token",
        ):
            BilibiliMonitor()

        printed_output = "\n".join(
            " ".join(str(arg) for arg in call.args)
            for call in mock_print.call_args_list
        )

        self.assertIn("飞书Webhook: 已配置", printed_output)
        self.assertIn("09:20-09:40 每30秒", printed_output)
        self.assertNotIn("super-secret-token", printed_output)
        self.assertNotIn("open.feishu.cn/open-apis/bot/v2/hook", printed_output)

    @patch("builtins.print")
    @patch("monitor.CommentStorage")
    @patch("monitor.FeishuBot")
    @patch("monitor.BilibiliAPI")
    def test_startup_banner_uses_configured_schedule_text(
        self,
        mock_bilibili_api,
        mock_feishu_bot,
        mock_comment_storage,
        mock_print,
    ):
        api_instance = mock_bilibili_api.return_value
        api_instance.has_auth.return_value = False
        api_instance.fetch_mode = "browser"
        mock_feishu_bot.return_value = MagicMock()
        mock_comment_storage.return_value = MagicMock()

        with patch("monitor.PEAK_START", dt_time(8, 0)), patch(
            "monitor.PEAK_END", dt_time(8, 20)
        ), patch("monitor.PEAK_INTERVAL_SECONDS", 15), patch(
            "monitor.MORNING_START", dt_time(8, 20)
        ), patch(
            "monitor.MORNING_END", dt_time(10, 0)
        ), patch(
            "monitor.MORNING_INTERVAL_SECONDS", 120
        ), patch(
            "monitor.AFTERNOON_START", dt_time(14, 0)
        ), patch(
            "monitor.AFTERNOON_END", dt_time(16, 0)
        ), patch(
            "monitor.AFTERNOON_INTERVAL_SECONDS", 240
        ), patch("monitor.DEFAULT_INTERVAL_SECONDS", 900):
            BilibiliMonitor()

        printed_output = "\n".join(
            " ".join(str(arg) for arg in call.args)
            for call in mock_print.call_args_list
        )

        self.assertIn("08:00-08:20 每15秒", printed_output)
        self.assertIn("08:20-10:00 每2分钟", printed_output)
        self.assertIn("14:00-16:00 每4分钟", printed_output)
        self.assertIn("其余每15分钟", printed_output)


class MonitorStartupNotificationTestCase(unittest.IsolatedAsyncioTestCase):
    @patch("monitor.CommentStorage")
    @patch("monitor.FeishuBot")
    @patch("monitor.BilibiliAPI")
    async def test_run_startup_message_uses_up_name_and_uid_when_available(
        self,
        mock_bilibili_api,
        mock_feishu_bot,
        mock_comment_storage,
    ):
        api_instance = mock_bilibili_api.return_value
        api_instance.has_auth.return_value = True
        api_instance.fetch_mode = "browser"
        api_instance.close = AsyncMock()
        api_instance.get_user_profile = AsyncMock(
            return_value={"mid": 1671203508, "uname": "洪洪火火复盘"}
        )
        feishu_instance = mock_feishu_bot.return_value
        feishu_instance.send_text = MagicMock(return_value=True)
        mock_comment_storage.return_value = MagicMock()

        monitor = BilibiliMonitor()
        monitor.running = False
        monitor._check_login_status = AsyncMock()

        with patch("monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 4, 5, 9, 47, 34)
            await monitor.run()

        feishu_instance.send_text.assert_called_with(
            "🚀 B站评论监控已启动\n"
            "👤 监控UP主: 洪洪火火复盘 (UID: 1671203508)\n"
            "⏰ 启动时间: 2026-04-05 09:47:34"
        )
        api_instance.close.assert_awaited_once()

    @patch("monitor.CommentStorage")
    @patch("monitor.FeishuBot")
    @patch("monitor.BilibiliAPI")
    async def test_run_startup_message_falls_back_to_uid_when_name_unavailable(
        self,
        mock_bilibili_api,
        mock_feishu_bot,
        mock_comment_storage,
    ):
        api_instance = mock_bilibili_api.return_value
        api_instance.has_auth.return_value = True
        api_instance.fetch_mode = "browser"
        api_instance.close = AsyncMock()
        api_instance.get_user_profile = AsyncMock(return_value=None)
        feishu_instance = mock_feishu_bot.return_value
        feishu_instance.send_text = MagicMock(return_value=True)
        mock_comment_storage.return_value = MagicMock()

        monitor = BilibiliMonitor()
        monitor.running = False
        monitor._check_login_status = AsyncMock()

        with patch("monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 4, 5, 9, 47, 34)
            await monitor.run()

        feishu_instance.send_text.assert_called_with(
            "🚀 B站评论监控已启动\n"
            "👤 监控UP主: 1671203508\n"
            "⏰ 启动时间: 2026-04-05 09:47:34"
        )
        api_instance.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
