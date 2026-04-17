import requests
from datetime import datetime
from typing import Dict, List


class FeishuBot:
    """飞书机器人推送"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send_text(self, text: str) -> bool:
        """
        发送纯文本消息
        """
        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        return self._send(payload)
    
    def send_up_comment(self, video_info: Dict, comment: Dict) -> bool:
        """
        发送UP主评论通知（富文本卡片格式）
        """
        # 格式化时间
        comment_time = datetime.fromtimestamp(comment['ctime']).strftime('%Y-%m-%d %H:%M:%S')
        
        # 判断是评论还是回复
        if comment['parent'] == 0:
            comment_type = "💬 发表评论"
        else:
            comment_type = "↩️ 回复评论"
        
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🎬 {video_info['title'][:50]}..." if len(video_info['title']) > 50 else f"🎬 {video_info['title']}"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{comment_type}**\n🕐 {comment_time}"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"👤 **{comment['uname']}**"
                        }
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"> {comment['content']}"
                        }
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "🔗 查看视频"
                                },
                                "type": "primary",
                                "url": video_info['link']
                            }
                        ]
                    }
                ]
            }
        }
        
        return self._send(payload)
    
    def send_multiple_comments(self, video_info: Dict, comments: List[Dict]) -> bool:
        """
        发送多条评论通知
        """
        if not comments:
            return True
        
        elements = []
        
        for comment in comments:
            comment_time = datetime.fromtimestamp(comment['ctime']).strftime('%m-%d %H:%M')
            
            if comment['parent'] == 0:
                comment_type = "💬"
            else:
                comment_type = "↩️"
            
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{comment_type} **{comment_time}** | 👍 {comment['like']}\n> {comment['content']}"
                }
            })
            elements.append({
                "tag": "hr"
            })
        
        # 移除最后一个分割线
        if elements:
            elements.pop()
        
        # 添加查看视频按钮
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "🔗 查看视频"
                    },
                    "type": "primary",
                    "url": video_info['link']
                }
            ]
        })
        
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🎬 UP主发了 {len(comments)} 条新评论"
                    },
                    "template": "green"
                },
                "elements": elements
            }
        }
        
        return self._send(payload)
    
    def _send(self, payload: Dict) -> bool:
        """
        发送请求到飞书
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            result = response.json()
            
            if result.get('code') == 0:
                print(f"✅ 飞书消息发送成功")
                return True
            else:
                print(f"❌ 飞书消息发送失败: {result.get('msg')}")
                return False
                
        except Exception as e:
            print(f"❌ 发送飞书消息异常: {e}")
            return False
