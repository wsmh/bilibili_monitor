#!/usr/bin/env python3
import asyncio
from bili_api import BilibiliAPI
from config import UP_UID

async def test():
    print('测试获取UP主信息...')
    api = BilibiliAPI()
    print(f'登录态: {"已配置" if api.has_auth() else "未配置"}')
    
    print('获取视频列表...')
    video = await api.get_latest_video(UP_UID)
    
    if video:
        print(f'✅ 最新视频: {video["title"][:50]}...')
        print(f'   BV号: {video["bvid"]}')
        print(f'   AID: {video["aid"]}')
        
        print('\n获取评论...')
        comments = await api.get_video_comments(video['aid'])
        
        print(f'✅ 获取到 {len(comments)} 条评论')
        for comment in comments[:5]:
            print(
                f'   - rpid={comment["rpid"]} mid={comment["mid"]} '
                f'uname={comment["uname"]} ctime={comment["ctime"]}'
            )
        
        if comments:
            # 筛选UP主评论
            up_comments = api.filter_up_comments(comments, UP_UID)
            print(f'✅ UP主评论数量: {len(up_comments)}')
            
            if up_comments:
                print(f'   内容: {up_comments[0]["content"]}')
            else:
                print('   ℹ️ UP主暂未发表评论')
        else:
            print('📭 暂无评论')
    else:
        print('❌ 未获取到视频')

if __name__ == "__main__":
    asyncio.run(test())
