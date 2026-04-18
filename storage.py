import json
import os
from typing import Dict, List, Optional, Set


class CommentStorage:
    """评论存储管理

    设计目标：只关注“当前最新内容”的 UP 主评论去重。

    - 当监控到发布了新内容（视频/动态/充电相关动态等）时，会切换 current_post_key
      并清空已通知的 rpid 集合。
    - 为兼容旧版本数据文件，会在加载时识别 legacy 字段。
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.notified_rpids: Set[int] = set()
        self.current_post_key: Optional[str] = None
        self._load()

    def _load(self):
        """从文件加载已通知的评论ID"""
        if not os.path.exists(self.filepath):
            print("📂 没有找到历史记录文件，将创建新文件")
            self.notified_rpids = set()
            self.current_post_key = None
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            print(f"⚠️ 加载历史记录失败: {exc}")
            self.notified_rpids = set()
            self.current_post_key = None
            return

        # 新格式
        if "current_post_key" in data:
            self.current_post_key = data.get("current_post_key")
            self.notified_rpids = set(data.get("rpids", []))
            print(f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录")
            return

        # 旧格式：仅支持视频
        self.notified_rpids = set(data.get("rpids", []))
        legacy_bvid = data.get("current_video_bvid")
        self.current_post_key = f"video:{legacy_bvid}" if legacy_bvid else None
        print(f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录")

    def _save(self):
        """保存已通知的评论ID到文件"""
        try:
            directory = os.path.dirname(self.filepath)
            if directory:
                os.makedirs(directory, exist_ok=True)

            data: Dict = {
                "rpids": list(self.notified_rpids),
                "current_post_key": self.current_post_key,
            }

            # 为了让旧版本还能读取（可选）
            if self.current_post_key and self.current_post_key.startswith("video:"):
                data["current_video_bvid"] = self.current_post_key.split(":", 1)[1]

            with open(self.filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"⚠️ 保存历史记录失败: {exc}")

    def is_new_post(self, post_key: str) -> bool:
        """检查是否是新内容"""
        return self.current_post_key != post_key

    def switch_post(self, post_key: str):
        """切换到新内容，清空旧记录"""
        if self.current_post_key == post_key:
            return

        print(f"🆕 检测到新内容: {post_key}")
        print("🗑️ 清空旧内容的评论记录")
        self.notified_rpids.clear()
        self.current_post_key = post_key
        self._save()

    # ----------------------------
    # Backward-compatible helpers
    # ----------------------------

    def is_new_video(self, bvid: str) -> bool:
        return self.is_new_post(f"video:{bvid}")

    def switch_video(self, bvid: str):
        self.switch_post(f"video:{bvid}")

    def is_notified(self, rpid: int) -> bool:
        """检查评论是否已通知过"""
        return rpid in self.notified_rpids

    def mark_notified(self, rpid: int):
        """标记评论为已通知"""
        self.notified_rpids.add(rpid)
        self._save()

    def mark_multiple_notified(self, rpids: List[int]):
        """批量标记评论为已通知"""
        self.notified_rpids.update(rpids)
        self._save()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_notified": len(self.notified_rpids),
            "current_post_key": self.current_post_key,
        }
