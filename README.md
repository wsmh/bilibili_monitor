# B站 UP 主评论监控

## 作用

- 监控指定 `UP_UID` 的最新发布内容（优先从空间动态流获取：视频 / 动态 / 充电相关内容）
- 检测到发布新内容时发送飞书通知
- 检测到该 UP 主在该内容下发表评论或回复时发送飞书通知

## 运行前准备

1. **复制环境变量模板**

   ```bash
   cp .env.example .env
   ```

2. **编辑 `.env` 文件**，填入以下必需配置：
   - `UP_UID`：要监控的 UP 主 UID
   - `FEISHU_WEBHOOK`：飞书机器人 Webhook 地址
   - `BILI_COOKIE`：B站登录 Cookie（从浏览器开发者工具复制）

3. **安装依赖**（首次运行）
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

## 推荐启动方式

```bash
cd ~/bilibili_monitor

source venv/bin/activate
python monitor.py
```

Windows 下可以用：

```powershell
cd C:\path\to\bilibili_monitor

.\venv\Scripts\Activate.ps1
python monitor.py
```

默认抓取模式已经切到 `browser`。

- 会优先启动本机 Chrome，用真实浏览器上下文访问 B站
- 如果没有显式配置 `BILI_BROWSER_EXECUTABLE`，程序会自动探测常见的 Chrome / Chromium 安装路径
- 最新内容优先通过空间「动态」页实际发出的网络响应获取（更容易覆盖充电专属/仅粉丝可见等内容），失败会回退到公开视频列表
- 评论优先通过页面 `bili-comments` 组件里的结构化数据获取（视频/动态通用），失败会回退到 B 站 reply 接口
- 当直连 API 经常触发 `412` 时，浏览器模式通常更稳

充电专属内容需要配置 `BILI_COOKIE`，且该 Cookie 对应的账号必须具备查看该 UP 充电内容的权限，否则评论区可能返回空或报权限不足。

如果你想强制改回 API 模式，修改 `.env` 文件：

```bash
BILI_FETCH_MODE=api
```

## 测试接口

```bash
cd ~/bilibili_monitor

source venv/bin/activate
python test_api.py
```

Windows 下测试可以用：

```powershell
cd C:\path\to\bilibili_monitor

.\venv\Scripts\Activate.ps1
python test_api.py
```

如果自动探测不到浏览器，可以在 `.env` 中手动指定，例如：

```env
BILI_BROWSER_EXECUTABLE=C:\Program Files\Google\Chrome\Application\chrome.exe
```

如果不填 `BILI_COOKIE` 也能运行，但常见现象是：

- B站评论区会出现"登录后查看更多评论"的限制
- 能抓到的评论窗口更小
- 对"UP 主回复旧评论"的覆盖会更弱

## 轮询策略

- 默认配置下：
- `09:20 - 09:40`：每 30 秒检测一次
- `09:40 - 11:30`：每 3 分钟检测一次
- `13:00 - 15:00`：每 3 分钟检测一次
- 其他时间：每 30 分钟检测一次
- 上述时间段和间隔都可以在 `.env` 中修改

## Cookie 失效提示

- 程序启动时会尝试校验登录态
- 如果检测到 Cookie 已配置但登录态失效，会在控制台和飞书里提示
- 一旦失效，重新从浏览器复制新的 Cookie 并重启程序即可

## 配置文件说明

所有配置都通过 `.env` 文件管理，主要配置项：

| 配置项                  | 说明                       | 默认值  |
| ----------------------- | -------------------------- | ------- |
| `UP_UID`                | 监控的 UP 主 UID           | 必填    |
| `FEISHU_WEBHOOK`        | 飞书机器人 Webhook         | 必填    |
| `BILI_COOKIE`           | B站完整 Cookie 字符串      | 必填    |
| `BILI_FETCH_MODE`       | 抓取模式：browser/api/auto | browser |
| `BILI_BROWSER_EXECUTABLE` | 浏览器路径，留空则自动探测 | 自动探测 |
| `CHECK_INTERVAL`        | 检查间隔（秒）             | 10      |
| `BILI_BROWSER_HEADLESS` | 是否无头模式               | true    |
| `PEAK_START`            | 高峰时段开始时间（HH:MM）  | 09:20   |
| `PEAK_END`              | 高峰时段结束时间（HH:MM）  | 09:40   |
| `PEAK_INTERVAL_SECONDS` | 高峰时段检查间隔（秒）     | 30      |
| `MORNING_START`         | 上午常规时段开始时间       | 09:40   |
| `MORNING_END`           | 上午常规时段结束时间       | 11:30   |
| `MORNING_INTERVAL_SECONDS` | 上午常规时段检查间隔（秒） | 180   |
| `AFTERNOON_START`       | 下午常规时段开始时间       | 13:00   |
| `AFTERNOON_END`         | 下午常规时段结束时间       | 15:00   |
| `AFTERNOON_INTERVAL_SECONDS` | 下午常规时段检查间隔（秒） | 180 |
| `DEFAULT_INTERVAL_SECONDS` | 其他时间检查间隔（秒）   | 1800    |

**注意**：`.env` 文件包含敏感信息，已被 `.gitignore` 忽略，不会提交到 Git。
