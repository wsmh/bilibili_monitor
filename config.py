import os
from datetime import datetime, time as dt_time
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


def _parse_time_env(name: str, default: str) -> dt_time:
    value = os.getenv(name, default).strip()
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"{name} 必须是 HH:MM 格式，当前值: {value!r}") from exc

# ============================================
# 私密配置 - 请在 .env 文件中设置这些值
# ============================================

# B站UP主配置（请在 .env 文件中设置 UP_UID）
UP_UID = int(os.getenv("UP_UID", "0"))

# 飞书机器人配置（请在 .env 文件中设置 FEISHU_WEBHOOK）
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")

# B站登录态配置
# 推荐直接填浏览器复制出来的完整 Cookie 字符串，优先级高于下面的单项字段。
BILI_COOKIE = os.getenv("BILI_COOKIE", "")
BILI_SESSDATA = os.getenv("BILI_SESSDATA", "")
BILI_BILI_JCT = os.getenv("BILI_BILI_JCT", "")
BILI_BUVID3 = os.getenv("BILI_BUVID3", "")
BILI_BUVID4 = os.getenv("BILI_BUVID4", "")
BILI_DEDEUSERID = os.getenv("BILI_DEDEUSERID", "")

# ============================================
# 一般配置 - 可以通过环境变量或 .env 修改
# ============================================

# 抓取模式配置
# browser: 优先使用真实浏览器上下文抓取，最适合规避 412
# api: 仅使用 bilibili-api / HTTP 接口
# auto: 先尝试 browser，失败后回退 api
BILI_FETCH_MODE = os.getenv("BILI_FETCH_MODE", "browser").strip().lower()
BILI_BROWSER_EXECUTABLE = os.getenv(
    "BILI_BROWSER_EXECUTABLE",
    "",
).strip()
BILI_BROWSER_HEADLESS = os.getenv("BILI_BROWSER_HEADLESS", "true").strip().lower() != "false"
BILI_BROWSER_TIMEOUT_MS = int(os.getenv("BILI_BROWSER_TIMEOUT_MS", "30000"))

# 监控配置
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "10"))  # 检查间隔（秒）
SECURITY_COOLDOWN_SECONDS = int(os.getenv("SECURITY_COOLDOWN_SECONDS", "120"))
COMMENT_MAX_PAGES_AUTH = int(os.getenv("COMMENT_MAX_PAGES_AUTH", "2"))
COMMENT_MAX_PAGES_GUEST = int(os.getenv("COMMENT_MAX_PAGES_GUEST", "1"))
DATA_FILE = os.getenv("DATA_FILE", "notified_comments.json")  # 已通知评论记录文件

# 轮询时段配置
PEAK_START = _parse_time_env("PEAK_START", "09:20")
PEAK_END = _parse_time_env("PEAK_END", "09:40")
PEAK_INTERVAL_SECONDS = int(os.getenv("PEAK_INTERVAL_SECONDS", "30"))

MORNING_START = _parse_time_env("MORNING_START", "09:40")
MORNING_END = _parse_time_env("MORNING_END", "11:30")
MORNING_INTERVAL_SECONDS = int(os.getenv("MORNING_INTERVAL_SECONDS", "180"))

AFTERNOON_START = _parse_time_env("AFTERNOON_START", "13:00")
AFTERNOON_END = _parse_time_env("AFTERNOON_END", "15:00")
AFTERNOON_INTERVAL_SECONDS = int(os.getenv("AFTERNOON_INTERVAL_SECONDS", "180"))

DEFAULT_INTERVAL_SECONDS = int(os.getenv("DEFAULT_INTERVAL_SECONDS", "1800"))
