import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from monitor import BilibiliMonitor, get_check_interval_for_datetime


class MonitorScheduleTestCase(unittest.TestCase):
    def test_peak_window_uses_thirty_seconds(self):
        dt = datetime(2026, 4, 1, 9, 25, 0)

        self.assertEqual(get_check_interval_for_datetime(dt), 30)

    def test_morning_and_afternoon_windows_use_three_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 9, 5, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 10, 45, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 14, 0, 0)), 180)

    def test_other_times_use_thirty_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 8, 30, 0)), 1800)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 16, 0, 0)), 1800)


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


if __name__ == "__main__":
    unittest.main()
