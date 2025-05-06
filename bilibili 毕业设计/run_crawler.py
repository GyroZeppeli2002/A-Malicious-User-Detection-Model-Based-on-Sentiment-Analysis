import os
import sys
import argparse

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 导入前设置环境变量，禁用 Socket.IO 服务器
os.environ['DISABLE_SOCKETIO_SERVER'] = 'true'

from app import create_app, socketio
from app.utils.crawler import BilibiliCrawler

# 确保 socketio 可用
import app.utils.crawler as crawler_module
crawler_module.socketio = socketio

def main():
    """运行爬虫的主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='B站爬虫工具')
    parser.add_argument('--limit', type=int, default=5, help='爬取视频数量')
    parser.add_argument('--bvid', type=str, help='指定BV号爬取弹幕')
    parser.add_argument('--url', type=str, help='指定视频URL爬取弹幕')
    parser.add_argument('--no-csv', action='store_true', help='不保存到CSV文件')
    parser.add_argument('--no-db', action='store_true', help='不保存到数据库')
    
    args = parser.parse_args()
    
    print("=== B站爬虫独立运行模式 ===")
    
    # 创建应用实例
    app = create_app()
    
    # 创建爬虫实例并传入应用
    crawler = BilibiliCrawler(app=app)
    
    # 在应用上下文中运行爬虫
    with app.app_context():
        if args.bvid:
            # 爬取指定BV号的弹幕
            print(f"\n爬取视频 {args.bvid} 的弹幕...")
            danmu_list = crawler.crawl_video_danmu(
                args.bvid, 
                save_to_csv=not args.no_csv, 
                save_to_db=not args.no_db
            )
            
            if danmu_list:
                print(f"成功爬取 {len(danmu_list)} 条弹幕")
            else:
                print("未获取到弹幕数据")
        elif args.url:
            # 爬取指定URL的弹幕
            print(f"\n爬取视频 {args.url} 的弹幕...")
            danmu_list = crawler.crawl_video_danmu(
                args.url, 
                save_to_csv=not args.no_csv, 
                save_to_db=not args.no_db
            )
            
            if danmu_list:
                print(f"成功爬取 {len(danmu_list)} 条弹幕")
            else:
                print("未获取到弹幕数据")
        else:
            # 爬取热门视频
            print(f"\n爬取热门视频 (数量: {args.limit})...")
            videos = crawler.crawl_videos(limit=args.limit)
            
            if videos:
                print(f"\n成功爬取 {len(videos)} 个视频")
                
                # 选择第一个视频爬取弹幕
                first_video = videos[0]
                print(f"\n爬取视频《{first_video['title']}》的弹幕...")
                danmu_list = crawler.crawl_video_danmu(
                    first_video['bvid'], 
                    save_to_csv=not args.no_csv, 
                    save_to_db=not args.no_db
                )
                
                if danmu_list:
                    print(f"成功爬取 {len(danmu_list)} 条弹幕")
                else:
                    print("未获取到弹幕数据")
            else:
                print("未获取到视频数据")

if __name__ == "__main__":
    main() 