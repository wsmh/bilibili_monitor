import requests
from datetime import datetime
from typing import Dict, List


def resolve_resource_labels(resource_info: Dict) -> Dict[str, str]:
    kind = (resource_info or {}).get("kind") or "video"
    if kind == "dynamic":
        return {
            "prefix": "📝",
            "button": "🔗 查看动态",
            "template": "purple",
        }
    return {
        "prefix": "🎬",
        "button": "🔗 查看视频",
        "template": "blue",
    }


def build_reply_to_markdown(reply_to: Dict) -> str:
    if not reply_to:
        return ""

    content = (reply_to.get("content") or "").strip()
    if not content:
        return ""

    uname = (reply_to.get("uname") or "").strip()
    if uname:
        return f"回复 **{uname}**：\n> {content}"
    return f"回复原评论：\n> {content}"


def truncate_text(value: str, limit: int) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def format_currency_cent(value) -> str:
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return ""

    if cents <= 0:
        return ""

    if cents % 100 == 0:
        return f"¥{cents // 100}"
    return f"¥{cents / 100:.2f}"


class FeishuBot:
    """飞书机器人推送"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_text(self, text: str) -> bool:
        """发送纯文本消息"""

        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        return self._send(payload)

    def send_up_comment(self, resource_info: Dict, comment: Dict) -> bool:
        """发送UP主评论通知（富文本卡片格式）"""

        labels = resolve_resource_labels(resource_info)

        comment_time = datetime.fromtimestamp(comment["ctime"]).strftime("%Y-%m-%d %H:%M:%S")

        if comment["parent"] == 0:
            comment_type = "💬 发表评论"
        else:
            comment_type = "↩️ 回复评论"

        title = resource_info.get("title", "")

        elements: List[Dict] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{comment_type}**\n🕐 {comment_time}",
                },
            }
        ]

        reply_to_md = build_reply_to_markdown(comment.get("reply_to"))
        if reply_to_md:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": reply_to_md,
                    },
                }
            )

        elements.extend(
            [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"👤 **{comment['uname']}**",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"> {comment['content']}",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": labels["button"],
                            },
                            "type": "primary",
                            "url": resource_info["link"],
                        }
                    ],
                },
            ]
        )

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": (
                            f"{labels['prefix']} {title[:50]}..."
                            if len(title) > 50
                            else f"{labels['prefix']} {title}"
                        ),
                    },
                    "template": labels["template"],
                },
                "elements": elements,
            },
        }

        return self._send(payload)

    def send_multiple_comments(self, resource_info: Dict, comments: List[Dict]) -> bool:
        """发送多条评论通知"""

        if not comments:
            return True

        labels = resolve_resource_labels(resource_info)

        elements: List[Dict] = []

        for comment in comments:
            comment_time = datetime.fromtimestamp(comment["ctime"]).strftime("%m-%d %H:%M")

            if comment["parent"] == 0:
                comment_type = "💬"
            else:
                comment_type = "↩️"

            reply_to_md = build_reply_to_markdown(comment.get("reply_to"))
            if reply_to_md:
                content = (
                    f"{comment_type} **{comment_time}** | 👍 {comment['like']}\n"
                    f"{reply_to_md}\n"
                    f"> {comment['content']}"
                )
            else:
                content = f"{comment_type} **{comment_time}** | 👍 {comment['like']}\n> {comment['content']}"

            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content,
                    },
                }
            )
            elements.append({"tag": "hr"})

        if elements:
            elements.pop()

        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": labels["button"],
                        },
                        "type": "primary",
                        "url": resource_info["link"],
                    }
                ],
            }
        )

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{labels['prefix']} UP主发了 {len(comments)} 条新评论",
                    },
                    "template": "green",
                },
                "elements": elements,
            },
        }

        return self._send(payload)

    def send_upower_qa_answer(self, up_label: str, answer: Dict) -> bool:
        """发送充电问答（upower）UP 回复通知。"""

        answer_time_value = int(answer.get("answer_time") or 0)
        answer_time = (
            datetime.fromtimestamp(answer_time_value).strftime("%Y-%m-%d %H:%M:%S")
            if answer_time_value
            else ""
        )

        level_name = (answer.get("level_name") or "").strip()
        level_price = format_currency_cent(answer.get("level_price"))
        level_label = ""
        if level_name and level_price:
            level_label = f"{level_name} ({level_price})"
        elif level_name:
            level_label = level_name

        question_nickname = (answer.get("question_nickname") or "").strip() or "匿名"
        question_text = truncate_text(answer.get("question_text"), 600)
        answer_text = truncate_text(answer.get("answer_text"), 800)
        qa_id = answer.get("qa_id")

        meta_parts = []
        if answer_time:
            meta_parts.append(f"🕐 {answer_time}")
        if level_label:
            meta_parts.append(f"⭐ {level_label}")
        if qa_id is not None:
            meta_parts.append(f"🆔 qa_id={qa_id}")

        elements: List[Dict] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(meta_parts) if meta_parts else "（无元信息）",
                },
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"🙋 **{question_nickname}**：\n> {question_text or '（无文本）'}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"✅ **{up_label}** 回复：\n> {answer_text or '（无文本）'}",
                },
            },
        ]

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "💡 充电问答新回复"},
                    "template": "orange",
                },
                "elements": elements,
            },
        }

        return self._send(payload)

    def send_multiple_upower_qa_answers(self, up_label: str, answers: List[Dict]) -> bool:
        if not answers:
            return True

        elements: List[Dict] = []
        for answer in answers:
            answer_time_value = int(answer.get("answer_time") or 0)
            answer_time = (
                datetime.fromtimestamp(answer_time_value).strftime("%m-%d %H:%M")
                if answer_time_value
                else ""
            )
            qa_id = answer.get("qa_id")
            question_nickname = (answer.get("question_nickname") or "").strip() or "匿名"
            answer_text = truncate_text(answer.get("answer_text"), 350)

            header = " ".join(
                part
                for part in [
                    f"🕐 {answer_time}" if answer_time else "",
                    f"qa_id={qa_id}" if qa_id is not None else "",
                ]
                if part
            )

            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{header}**\n"
                            f"🙋 {question_nickname}\n"
                            f"> {answer_text or '（无文本）'}"
                        ).strip(),
                    },
                }
            )
            elements.append({"tag": "hr"})

        if elements:
            elements.pop()

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"💡 充电问答：{up_label} 新回复 {len(answers)} 条",
                    },
                    "template": "orange",
                },
                "elements": elements,
            },
        }

        return self._send(payload)

    def _send(self, payload: Dict) -> bool:
        """发送请求到飞书"""

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            result = response.json()

            if result.get("code") == 0:
                print("✅ 飞书消息发送成功")
                return True

            print(f"❌ 飞书消息发送失败: {result.get('msg')}")
            return False

        except Exception as exc:
            print(f"❌ 发送飞书消息异常: {exc}")
            return False
