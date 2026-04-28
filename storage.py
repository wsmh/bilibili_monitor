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

        # 充电问答（upower）模块：用 answer content_id 去重
        self.notified_upower_answer_ids: List[int] = []
        self._notified_upower_answer_id_set: Set[int] = set()
        self.upower_initialized: bool = False

        self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            print("📂 没有找到历史记录文件，将创建新文件")
            self.notified_rpids = set()
            self.current_post_key = None
            self.tracked_roots = []
            self.notified_upower_answer_ids = []
            self._notified_upower_answer_id_set = set()
            self.upower_initialized = False
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            print(f"⚠️ 加载历史记录失败: {exc}")
            self.notified_rpids = set()
            self.current_post_key = None
            self.tracked_roots = []
            self.notified_upower_answer_ids = []
            self._notified_upower_answer_id_set = set()
            self.upower_initialized = False
            return

        # 新格式
        if "current_post_key" in data:
            self.current_post_key = data.get("current_post_key")
            self.notified_rpids = set(data.get("rpids", []))
            self.tracked_roots = [int(x) for x in data.get("tracked_roots", []) if str(x).isdigit()]

            self.notified_upower_answer_ids = [
                int(x)
                for x in data.get("upower_answer_ids", [])
                if str(x).isdigit()
            ]
            self._notified_upower_answer_id_set = set(self.notified_upower_answer_ids)
            self.upower_initialized = bool(data.get("upower_initialized", False))

            print(
                f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录，"
                f"{len(self.notified_upower_answer_ids)} 条充电问答记录"
            )
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
                "upower_answer_ids": self.notified_upower_answer_ids,
                "upower_initialized": self.upower_initialized,
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
    # Upower QA dedup
    # ----------------------------

    def is_upower_answer_notified(self, content_id: int) -> bool:
        return int(content_id) in self._notified_upower_answer_id_set

    def mark_upower_answer_notified(self, content_id: int, max_items: int):
        content_id = int(content_id)
        if content_id in self._notified_upower_answer_id_set:
            return

        self._notified_upower_answer_id_set.add(content_id)
        self.notified_upower_answer_ids.insert(0, content_id)

        if max_items > 0 and len(self.notified_upower_answer_ids) > max_items:
            removed = self.notified_upower_answer_ids[max_items:]
            self.notified_upower_answer_ids = self.notified_upower_answer_ids[:max_items]
            for item in removed:
                self._notified_upower_answer_id_set.discard(int(item))

        self._save()

    def mark_multiple_upower_answers_notified(self, content_ids: List[int], max_items: int):
        changed = False
        for content_id in content_ids:
            content_id = int(content_id)
            if content_id in self._notified_upower_answer_id_set:
                continue

            self._notified_upower_answer_id_set.add(content_id)
            self.notified_upower_answer_ids.insert(0, content_id)
            changed = True

        if not changed:
            return

        if max_items > 0 and len(self.notified_upower_answer_ids) > max_items:
            removed = self.notified_upower_answer_ids[max_items:]
            self.notified_upower_answer_ids = self.notified_upower_answer_ids[:max_items]
            for item in removed:
                self._notified_upower_answer_id_set.discard(int(item))

        self._save()

    def set_upower_initialized(self, value: bool = True):
        value = bool(value)
        if self.upower_initialized == value:
            return
        self.upower_initialized = value
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
            "total_upower_answers": len(self.notified_upower_answer_ids),
        }
