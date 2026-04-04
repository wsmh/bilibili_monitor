import json
import os
from typing import Set, Dict


class CommentStorage:
    """评论存储管理"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.notified_rpids: Set[int] = set()
        self.current_video_bvid: str = None
        self._load()
    
    def _load(self):
        """从文件加载已通知的评论ID"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.notified_rpids = set(data.get('rpids', []))
                    self.current_video_bvid = data.get('current_video_bvid')
                    print(f"📂 已加载 {len(self.notified_rpids)} 条历史评论记录")
            except Exception as e:
                print(f"⚠️ 加载历史记录失败: {e}")
                self.notified_rpids = set()
        else:
            print("📂 没有找到历史记录文件，将创建新文件")
            self.notified_rpids = set()
    
    def _save(self):
        """保存已通知的评论ID到文件"""
        try:
            directory = os.path.dirname(self.filepath)
            if directory:
                os.makedirs(directory, exist_ok=True)
            data = {
                'rpids': list(self.notified_rpids),
                'current_video_bvid': self.current_video_bvid
            }
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存历史记录失败: {e}")
    
    def is_new_video(self, bvid: str) -> bool:
        """检查是否是新视频"""
        return self.current_video_bvid != bvid
    
    def switch_video(self, bvid: str):
        """切换到新视频，清空旧记录"""
        if self.current_video_bvid != bvid:
            print(f"🎬 检测到新视频: {bvid}")
            print(f"🗑️ 清空旧视频的评论记录")
            self.notified_rpids.clear()
            self.current_video_bvid = bvid
            self._save()
    
    def is_notified(self, rpid: int) -> bool:
        """检查评论是否已通知过"""
        return rpid in self.notified_rpids
    
    def mark_notified(self, rpid: int):
        """标记评论为已通知"""
        self.notified_rpids.add(rpid)
        self._save()
    
    def mark_multiple_notified(self, rpids: list):
        """批量标记评论为已通知"""
        self.notified_rpids.update(rpids)
        self._save()
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_notified': len(self.notified_rpids),
            'current_video': self.current_video_bvid
        }
