import unittest
from datetime import datetime

from monitor import get_check_interval_for_datetime


class MonitorScheduleTestCase(unittest.TestCase):
    def test_peak_window_uses_ten_seconds(self):
        dt = datetime(2026, 4, 1, 9, 25, 0)

        self.assertEqual(get_check_interval_for_datetime(dt), 10)

    def test_morning_and_afternoon_windows_use_three_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 9, 5, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 10, 45, 0)), 180)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 14, 0, 0)), 180)

    def test_other_times_use_thirty_minutes(self):
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 8, 30, 0)), 1800)
        self.assertEqual(get_check_interval_for_datetime(datetime(2026, 4, 1, 16, 0, 0)), 1800)


if __name__ == "__main__":
    unittest.main()
