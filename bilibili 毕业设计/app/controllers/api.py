from flask import Blueprint, jsonify, request, current_app
from app.utils.crawler import BilibiliCrawler
import threading
import uuid
import time
from datetime import datetime

api_bp = Blueprint('api', __name__, url_prefix='/api')

# 存储爬虫任务状态
crawl_tasks = {}

@api_bp.route('/crawl/start', methods=['POST'])
def start_crawl():
    """启动爬虫任务"""
    try:
        data = request.json
        task_type = data.get('type', 'popular')
        limit = data.get('limit', 10)
        bvid = data.get('bvid')
        url = data.get('url')
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        crawl_tasks[task_id] = {
            'status': 'pending',
            'type': task_type,
            'start_time': datetime.now(),
            'percent': 0,
            'current': 0,
            'total': limit if task_type in ['popular', 'batch_danmu'] else 1,
            'log': [
                {
                    'time': datetime.now(),
                    'message': f'爬虫任务已创建: {task_type}',
                    'type': 'info'
                }
            ]
        }
        
        # 启动爬虫线程
        thread = threading.Thread(
            target=run_crawler_task,
            args=(task_id, task_type, limit, bvid, url)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': '爬虫任务已启动',
            'task_id': task_id
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@api_bp.route('/crawl/progress/<task_id>', methods=['GET'])
def get_crawl_progress(task_id):
    """获取爬虫任务进度"""
    if task_id not in crawl_tasks:
        return jsonify({
            'status': 'error',
            'message': '任务不存在'
        }), 404
    
    return jsonify(crawl_tasks[task_id])

def run_crawler_task(task_id, task_type, limit, bvid, url):
    """运行爬虫任务"""
    try:
        # 更新任务状态
        crawl_tasks[task_id]['status'] = 'running'
        add_task_log(task_id, f'开始执行爬虫任务: {task_type}', 'info')
        
        # 创建爬虫实例
        crawler = BilibiliCrawler(app=current_app)
        
        # 设置进度回调
        def progress_callback(current, total, item=None):
            percent = round(current / total * 100, 1) if total > 0 else 0
            crawl_tasks[task_id].update({
                'current': current,
                'total': total,
                'percent': percent,
                'current_item': item
            })
            
            if item:
                add_task_log(task_id, f'正在爬取: {item.get("title", "未知视频")}', 'info')
        
        # 根据任务类型执行不同的爬虫操作
        results = None
        
        if task_type == 'popular':
            # 爬取热门视频
            add_task_log(task_id, f'开始爬取热门视频，数量: {limit}', 'info')
            
            # 设置爬虫的进度回调
            crawler.set_progress_callback(progress_callback)
            
            # 执行爬取
            results = crawler.crawl_videos(limit=limit)
            
            if results:
                add_task_log(task_id, f'成功爬取 {len(results)} 个热门视频', 'success')
                crawl_tasks[task_id].update({
                    'status': 'completed',
                    'count': len(results),
                    'percent': 100
                })
            else:
                add_task_log(task_id, '未获取到热门视频数据', 'danger')
                crawl_tasks[task_id].update({
                    'status': 'failed',
                    'message': '未获取到热门视频数据'
                })
                
        elif task_type == 'danmu':
            # 爬取指定视频的弹幕
            target = bvid or url
            if not target:
                add_task_log(task_id, '未指定视频BV号或URL', 'danger')
                crawl_tasks[task_id].update({
                    'status': 'failed',
                    'message': '未指定视频BV号或URL'
                })
                return
                
            add_task_log(task_id, f'开始爬取视频 {target} 的弹幕', 'info')
            
            # 获取视频信息
            video_info = crawler.get_video_info(target)
            if video_info:
                crawl_tasks[task_id]['video_title'] = video_info['title']
                crawl_tasks[task_id]['current_item'] = {
                    'title': video_info['title'],
                    'author': video_info['author']
                }
                add_task_log(task_id, f'获取到视频信息: {video_info["title"]}', 'info')
            
            # 爬取弹幕
            danmu_list = crawler.crawl_video_danmu(target, save_to_csv=True, save_to_db=True)
            
            if danmu_list:
                add_task_log(task_id, f'成功爬取 {len(danmu_list)} 条弹幕', 'success')
                crawl_tasks[task_id].update({
                    'status': 'completed',
                    'count': len(danmu_list),
                    'percent': 100
                })
            else:
                add_task_log(task_id, '未获取到弹幕数据', 'danger')
                crawl_tasks[task_id].update({
                    'status': 'failed',
                    'message': '未获取到弹幕数据'
                })
                
        elif task_type == 'batch_danmu':
            # 批量爬取多个视频的弹幕
            add_task_log(task_id, f'开始批量爬取 {limit} 个热门视频的弹幕', 'info')
            
            # 先爬取热门视频
            videos = crawler.crawl_videos(limit=limit)
            
            if not videos:
                add_task_log(task_id, '未获取到热门视频数据', 'danger')
                crawl_tasks[task_id].update({
                    'status': 'failed',
                    'message': '未获取到热门视频数据'
                })
                return
                
            add_task_log(task_id, f'获取到 {len(videos)} 个热门视频，开始爬取弹幕', 'info')
            
            # 批量爬取弹幕
            total_danmu = 0
            for i, video in enumerate(videos):
                bvid = video['bvid']
                title = video['title']
                
                # 更新进度
                progress_callback(i + 1, len(videos), {
                    'title': title,
                    'author': video['author']
                })
                
                # 爬取弹幕
                danmu_list = crawler.crawl_video_danmu(bvid, save_to_csv=True, save_to_db=True)
                
                if danmu_list:
                    total_danmu += len(danmu_list)
                    add_task_log(task_id, f'视频《{title}》爬取到 {len(danmu_list)} 条弹幕', 'info')
                else:
                    add_task_log(task_id, f'视频《{title}》未获取到弹幕', 'warning')
                
                # 防止请求过快
                time.sleep(2)
            
            add_task_log(task_id, f'批量爬取完成，共 {total_danmu} 条弹幕', 'success')
            crawl_tasks[task_id].update({
                'status': 'completed',
                'count': total_danmu,
                'video_count': len(videos),
                'percent': 100
            })
        
    except Exception as e:
        # 更新任务状态为失败
        crawl_tasks[task_id].update({
            'status': 'failed',
            'message': str(e)
        })
        add_task_log(task_id, f'爬虫任务执行失败: {str(e)}', 'danger')

def add_task_log(task_id, message, log_type='info'):
    """添加任务日志"""
    if task_id in crawl_tasks:
        crawl_tasks[task_id]['log'].append({
            'time': datetime.now(),
            'message': message,
            'type': log_type
        }) 