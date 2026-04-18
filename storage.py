import json
import os
from typing import Dict, List, Optional, Set


class CommentStorage:
    """评论存储管理

    设计目标：只关注“当前最新内容”的 UP 主评论去重。

    - 当监控到发布了新内容（视频/动态/充电相关动态等）时，会切换 current_post_key
      并清空已通知的 rpid 集合。
    - tracked_roots 用于补齐“UP 在同一个评论线程下多次回复”的场景：
      记录最近若干个被回复的 root 评论 rpid，后续轮询时可额外扫描这些线程。
    - 为兼容旧版本数据文件，会在加载时识别 legacy 字段。
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.notified_rpids: Set[int] = set()
        self.current_post_key: Optional[str] = None
        self.tracked_roots: List[int] = []
        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            print("📂 没有找到历史记录文件，将创建新文件")
            self.notified_rpids = set()
            self.current_post_key = None
            self.tracked_roots = []
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            print(f"⚠️ 加载历史记录失败: {exc}")
            self.notified_rpids = set()
            self.current_post_key = None
            self.tracked_roots = []
            return

        # 新格式
        if "current_post_key" in data:
            self.current_post_key = data.get("current_post_key")
            self.notified_rpids = set(data.get("rpids", []))
            self.tracked_roots = [int(x) for x in data.get("tracked_roots", []) if str(x).isdigit()]
            print(f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录")
            return

        # 旧格式：仅支持视频
        self.notified_rpids = set(data.get("rpids", []))
        legacy_bvid = data.get("current_video_bvid")
        self.current_post_key = f"video:{legacy_bvid}" if legacy_bvid else None
        self.tracked_roots = []
        print(f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录")

    def _save(self):
        try:
            directory = os.path.dirname(self.filepath)
            if directory:
                os.makedirs(directory, exist_ok=True)

            data: Dict = {
                "rpids": list(self.notified_rpids),
                "current_post_key": self.current_post_key,
                "tracked_roots": self.tracked_roots,
            }

            # 为了让旧版本还能读取（可选）
            if self.current_post_key and self.current_post_key.startswith("video:"):
                data["current_video_bvid"] = self.current_post_key.split(":", 1)[1]

            with open(self.filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"⚠️ 保存历史记录失败: {exc}")

    def is_new_post(self, post_key: str) -> bool:
        return self.current_post_key != post_key

    def switch_post(self, post_key: str):
        if self.current_post_key == post_key:
            return

        print(f"🆕 检测到新内容: {post_key}")
        print("🗑️ 清空旧内容的评论记录")
        self.notified_rpids.clear()
        self.tracked_roots.clear()
        self.current_post_key = post_key
        self._save()

    # ----------------------------
    # Backward-compatible helpers
    # ----------------------------

    def is_new_video(self, bvid: str) -> bool:
        return self.is_new_post(f"video:{bvid}")

    def switch_video(self, bvid: str):
        self.switch_post(f"video:{bvid}")

    # ----------------------------
    # Dedup
    # ----------------------------

    def is_notified(self, rpid: int) -> bool:
        return rpid in self.notified_rpids

    def mark_notified(self, rpid: int):
        self.notified_rpids.add(rpid)
        self._save()

    def mark_multiple_notified(self, rpids: List[int]):
        self.notified_rpids.update(rpids)
        self._save()

    # ----------------------------
    # Thread tracking
    # ----------------------------

    def get_tracked_roots(self) -> List[int]:
        return list(self.tracked_roots)

    def track_root(self, root_rpid: int, max_roots: int):
        if not root_rpid:
            return

        root_rpid = int(root_rpid)
        self.tracked_roots = [value for value in self.tracked_roots if value != root_rpid]
        self.tracked_roots.insert(0, root_rpid)
        if max_roots > 0:
            self.tracked_roots = self.tracked_roots[:max_roots]
        self._save()

    def track_roots(self, roots: List[int], max_roots: int):
        for root in roots:
            self.track_root(root, max_roots)

    def get_stats(self) -> Dict:
        return {
            "total_notified": len(self.notified_rpids),
            "current_post_key": self.current_post_key,
            "tracked_roots": self.tracked_roots,
        }
