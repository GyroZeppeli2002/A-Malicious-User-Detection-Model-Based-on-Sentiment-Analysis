from app import create_app, db
from app.models.danmu import Danmu
from app.models.video import Video
from app.models.author import Author
from datetime import datetime
import os

app = create_app()

with app.app_context():
    print("创建数据库表...")
    db.create_all()
    print("数据库表创建完成！")
    
    # 检查是否已有数据
    if Video.query.count() == 0:
        print("添加示例数据...")
        # 添加一些示例数据
        sample_videos = [
            {
                'bvid': 'BV1xx411c7mD',
                'title': '【演唱会纪录】周杰伦 - 魔天伦世界巡回演唱会',
                'author': '周杰伦',
                'video_type': '音乐',
                'play_count': 1245789,
                'danmaku_count': 35689,
                'like_count': 98546,
                'coin_count': 45872,
                'favorite_count': 35214,
                'share_count': 12549,
                'comment_count': 8562
            },
            {
                'bvid': 'BV1Gx411c7zK',
                'title': '【原神】新角色演示 - 魈',
                'author': '米哈游',
                'video_type': '游戏',
                'play_count': 2568974,
                'danmaku_count': 89562,
                'like_count': 256897,
                'coin_count': 89562,
                'favorite_count': 56489,
                'share_count': 25698,
                'comment_count': 15698
            },
            {
                'bvid': 'BV1hx411c7qP',
                'title': '【美食纪录片】舌尖上的中国 第一季 第一集',
                'author': 'CCTV美食',
                'video_type': '美食',
                'play_count': 1598745,
                'danmaku_count': 45698,
                'like_count': 125487,
                'coin_count': 78956,
                'favorite_count': 98745,
                'share_count': 36547,
                'comment_count': 12587
            },
            {
                'bvid': 'BV1qx411c7rX',
                'title': '【科普】宇宙的起源与演化',
                'author': '科学探索',
                'video_type': '科技',
                'play_count': 987546,
                'danmaku_count': 25698,
                'like_count': 85214,
                'coin_count': 45698,
                'favorite_count': 25478,
                'share_count': 15698,
                'comment_count': 7895
            },
            {
                'bvid': 'BV1wx411c7tZ',
                'title': '【动画】咒术回战 第一季 合集',
                'author': '哔哩哔哩番剧',
                'video_type': '动画',
                'play_count': 3569874,
                'danmaku_count': 125478,
                'like_count': 356987,
                'coin_count': 125478,
                'favorite_count': 98745,
                'share_count': 45698,
                'comment_count': 25478
            }
        ]
        
        for video_data in sample_videos:
            video = Video(**video_data)
            db.session.add(video)
            
        # 添加一些示例弹幕数据
        sample_danmus = [
            {
                'video_bvid': 'BV1xx411c7mD',
                'video_title': '【演唱会纪录】周杰伦 - 魔天伦世界巡回演唱会',
                'cid': 12345678,
                'content': '周杰伦太棒了！',
                'appear_time': 120.5,
                'mode': 1,
                'font_size': 25,
                'color': 16777215,
                'send_time': datetime.now(),
                'user_hash': 'abcdef123456',
                'row_id': 1
            },
            {
                'video_bvid': 'BV1xx411c7mD',
                'video_title': '【演唱会纪录】周杰伦 - 魔天伦世界巡回演唱会',
                'cid': 12345678,
                'content': '这首歌太经典了',
                'appear_time': 180.2,
                'mode': 1,
                'font_size': 25,
                'color': 16777215,
                'send_time': datetime.now(),
                'user_hash': 'ghijkl789012',
                'row_id': 2
            }
        ]
        
        # 先获取视频ID
        video = Video.query.filter_by(bvid='BV1xx411c7mD').first()
        if video:
            for danmu_data in sample_danmus:
                danmu_data['video_id'] = video.id
                danmu = Danmu(**danmu_data)
                db.session.add(danmu)
            
        # 添加一些UP主数据
        sample_authors = [
            {
                'uid': '123456789',
                'name': '周杰伦',
                'follower_count': 3500000,
                'video_count': 56,
                'total_play_count': 258963147
            },
            {
                'uid': '987654321',
                'name': '米哈游',
                'follower_count': 4500000,
                'video_count': 124,
                'total_play_count': 658741236
            },
            {
                'uid': '456789123',
                'name': 'CCTV美食',
                'follower_count': 2500000,
                'video_count': 368,
                'total_play_count': 458963214
            },
            {
                'uid': '741852963',
                'name': '科学探索',
                'follower_count': 1800000,
                'video_count': 253,
                'total_play_count': 325896314
            },
            {
                'uid': '963258741',
                'name': '哔哩哔哩番剧',
                'follower_count': 5200000,
                'video_count': 785,
                'total_play_count': 986532147
            }
        ]
        
        for author_data in sample_authors:
            author = Author(**author_data)
            db.session.add(author)
            
        db.session.commit()
        print("示例数据添加完成！")
    else:
        print("数据库中已存在数据，跳过添加示例数据。")