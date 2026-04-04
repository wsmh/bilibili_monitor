# B站 UP 主评论监控

## 作用

- 监控指定 `UP_UID` 的最新视频
- 检测到新视频时发送飞书通知
- 检测到该 UP 主在最新视频下发表评论或回复时发送飞书通知

## 运行前准备

1. 在 `config.py` 里设置目标 `UP_UID`
2. 准备你自己的 B站登录 Cookie
3. 用环境变量传入 Cookie，避免把敏感信息写进代码

## 推荐启动方式

```bash
cd /Users/trevo1zzz/study/code/time/bilibili_monitor

export BILI_COOKIE='在这里粘贴完整 Cookie'
./venv/bin/python monitor.py
```

默认抓取模式已经切到 `browser`。

- 会优先启动本机 Chrome，用真实浏览器上下文访问 B站
- 最新视频通过空间页实际发出的网络响应获取
- 评论通过视频页 `bili-comments` 组件里的结构化数据获取
- 当直连 API 经常触发 `412` 时，浏览器模式通常更稳

如果你想强制改回 API 模式：

```bash
export BILI_FETCH_MODE='api'
./venv/bin/python monitor.py
```

## 测试接口

```bash
cd /Users/trevo1zzz/study/code/time/bilibili_monitor

export BILI_COOKIE='在这里粘贴完整 Cookie'
./venv/bin/python test_api.py
```

如果不填 `BILI_COOKIE` 也能运行，但常见现象是：

- B站评论区会出现“登录后查看更多评论”的限制
- 能抓到的评论窗口更小
- 对“UP 主回复旧评论”的覆盖会更弱

## 轮询策略

- `09:20 - 09:40`：每 10 秒检测一次
- `09:00 - 11:30`：每 3 分钟检测一次
- `13:00 - 15:00`：每 3 分钟检测一次
- 其他时间：每 30 分钟检测一次

## Cookie 失效提示

- 程序启动时会尝试校验登录态
- 如果检测到 Cookie 已配置但登录态失效，会在控制台和飞书里提示
- 一旦失效，重新从浏览器复制新的 Cookie 并重启程序即可
