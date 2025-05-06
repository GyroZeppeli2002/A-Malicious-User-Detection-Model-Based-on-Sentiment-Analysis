import os
import sys
import time
import json
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import pandas as pd
import logging
from flask import current_app
from flask_sqlalchemy import SQLAlchemy

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入 db 对象
try:
    from app import db
except ImportError:
    db = SQLAlchemy()

# 定义全局 socketio 变量
socketio = None

# 尝试导入 socketio
try:
    from app import socketio
except ImportError:
    # 如果直接运行此文件，提供一个模拟的 socketio
    class MockSocketIO:
        def emit(self, event, data=None):
            print(f"[MOCK SOCKET.IO] Event: {event}, Data: {str(data)[:100]}...")
    
    socketio = MockSocketIO()

class BilibiliCrawler:
    def __init__(self, app=None):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com',
            'Origin': 'https://www.bilibili.com',
            'Cookie': ''
        }
        
        self.app = app
        
        # 如果提供了应用实例，尝试从配置获取用户代理和Cookie
        if app:
            try:
                with app.app_context():
                    self.headers['User-Agent'] = app.config.get('USER_AGENT', self.headers['User-Agent'])
                    self.headers['Cookie'] = app.config.get('BILIBILI_COOKIE', '')
                    
                    # 确保 db 已初始化
                    if not hasattr(db, 'session'):
                        db.init_app(app)
            except Exception as e:
                logging.warning(f"获取配置时出错: {str(e)}")
        else:
            # 尝试从当前应用上下文获取配置
            try:
                self.headers['User-Agent'] = current_app.config.get('USER_AGENT', self.headers['User-Agent'])
                self.headers['Cookie'] = current_app.config.get('BILIBILI_COOKIE', '')
            except Exception as e:
                logging.warning(f"获取配置时出错: {str(e)}")
    
        # 添加进度回调
        self.progress_callback = None
    
    def log_to_console(self, message, end='\n'):
        """将消息同时输出到控制台"""
        sys.stdout.write(message + end)
        sys.stdout.flush()
        
    def emit_socket_event(self, event_name, data):
        """安全地发送Socket事件 (简化版，只记录日志)"""
        # 不使用Socket.IO，只输出日志
        self.log_to_console(f"[事件] {event_name}: {str(data)[:100]}...")
        # 不再尝试发送实际的Socket.IO事件

    def get_cid_from_bvid(self, bvid):
        """从BV号获取cid"""
        api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
        
        try:
            response = requests.get(api_url, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['code'] == 0 and 'data' in data:
                # 有些视频可能有多个分P，我们获取第一个分P的cid
                if 'pages' in data['data'] and len(data['data']['pages']) > 0:
                    return data['data']['pages'][0]['cid']
                elif 'cid' in data['data']:
                    return data['data']['cid']
                else:
                    error_msg = "无法在API响应中找到CID"
                    self.log_to_console(f"[错误] {error_msg}")
                    return None
            else:
                error_msg = data.get('message', '未知错误')
                self.log_to_console(f"[错误] 获取CID失败: {error_msg}")
                return None
        except Exception as e:
            self.log_to_console(f"[错误] 获取CID异常: {str(e)}")
            return None
            
    def get_video_info(self, bvid):
        """获取视频详细信息"""
        url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['code'] == 0:
                info = data['data']
                cid = self.get_cid_from_bvid(bvid)  # 获取CID用于弹幕获取
                
                # 获取 UP 主信息
                author_uid = info['owner']['mid']
                author_name = info['owner']['name']
                
                # 尝试获取更多 UP 主信息
                author_info = self.get_author_info(author_uid)
                
                video_info = {
                    'bvid': info['bvid'],
                    'cid': cid,
                    'title': info['title'],
                    'author': author_name,
                    'author_uid': author_uid,
                    'video_type': info['tname'] or '未分类',
                    'play_count': info['stat'].get('view', 0),
                    'danmaku_count': info['stat'].get('danmaku', 0),
                    'like_count': info['stat'].get('like', 0),
                    'coin_count': info['stat'].get('coin', 0),
                    'favorite_count': info['stat'].get('favorite', 0),
                    'share_count': info['stat'].get('share', 0),
                    'comment_count': info['stat'].get('reply', 0),
                    'created_time': datetime.fromtimestamp(info.get('ctime', time.time()))
                }
               
                # 添加 UP 主详细信息
                if author_info:
                    video_info.update({
                        'author_follower_count': author_info.get('follower_count', 0),
                        'author_video_count': author_info.get('video_count', 0),
                        'author_play_count': info['stat'].get('view', 0)
                    })
                    
                # 输出到控制台
                console_msg = f"[爬取] {info['title']} - UP主: {author_name} - 播放量: {info['stat'].get('view', 0)}"
                self.log_to_console(console_msg)
                
                # 发送实时消息
                self.emit_socket_event('crawl_progress', {
                    'title': info['title'],
                    'author': author_name,
                    'plays': info['stat'].get('view', 0),
                    'bvid': info['bvid']
                })
                    
                return video_info
        except Exception as e:
            self.log_to_console(f"[错误] 获取视频 {bvid} 信息失败: {str(e)}")
        
        return None

    def get_author_info(self, uid):
        """获取UP主详细信息"""
        try:
            # 复制一份新的headers，添加必要的cookies
            auth_headers = self.headers.copy()
            
            # 添加更多headers模拟浏览器行为
            auth_headers.update({
                #'Cookie': 'buvid3=ABCDEF123456; SESSDATA=random_value; bili_jct=random_token;',
                'Referer': f'https://space.bilibili.com/{uid}',
                'Origin': 'https://space.bilibili.com',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site'
            })
             # 确保数据至少有一个最小值
            min_followers = 100
            min_videos = 1
            min_plays = 1000
            space_url = f'https://api.bilibili.com/x/web-interface/card?mid={uid}&photo=1'
            vedio_url = f'https://api.bilibili.com/x/space/navnum?mid={uid}&web_location=333.1387'

            # 获取UP主基本信息 - 使用增强的headers
            space_resp = requests.get(space_url, headers=auth_headers, timeout=10)
            space_data = space_resp.json()
            nav_resp = requests.get(vedio_url, headers=auth_headers)
            if space_data['code'] == 0:
                space_data = space_data['data']
                name = space_data['card']['name']
                follower_count = space_data['follower']
                time.sleep(0.5)
                video_count = nav_resp.json()['data']['video']
                total_play_count = space_data['like_num']

                return {
                    'uid': uid,
                    'name': name,
                    'follower_count': max(follower_count, min_followers),
                    'video_count': max(video_count, min_videos),
                    'total_play_count': total_play_count
                }
        except Exception as e:
            self.log_to_console(f"[警告] 获取UP主 {uid} 信息失败: {str(e)}")
            return {
                'uid': uid,
                'name': '未知UP主',
                'follower_count': min_followers,
                'video_count': min_videos,
                'total_play_count': min_plays
            }
        
        return None

    def save_video_to_database(self, video_info):
        """保存视频信息到数据库"""
        if not video_info:
            return None
        
        try:
            # 确保在应用上下文中执行数据库操作
            if self.app:
                with self.app.app_context():
                    # 在上下文中导入模型
                    from app.models.video import Video
                    return self._save_video_to_db(video_info, Video)
            else:
                # 如果没有应用上下文，尝试从当前上下文导入
                try:
                    from app.models.video import Video
                    return self._save_video_to_db(video_info, Video)
                except Exception as e:
                    self.log_to_console(f"[错误] 无法在当前上下文中操作数据库: {str(e)}")
                    return None
                
        except Exception as e:
            self.log_to_console(f"[错误] 保存视频信息到数据库失败: {str(e)}")
            return None

    def _save_video_to_db(self, video_info, Video):
        """实际的数据库保存操作"""
        try:
            # 先保存 UP 主信息
            if 'author' in video_info and video_info['author']:
                try:
                    from app.models.author import Author
                    
                    # 查找或创建 UP 主
                    author = None
                    
                    # 如果有 UID，先通过 UID 查找
                    if 'author_uid' in video_info and video_info['author_uid']:
                        author = Author.query.filter_by(uid=video_info['author_uid']).first()
                    
                    # 如果没找到，再通过名称查找
                    if not author:
                        author_uid = video_info.get('author_uid', '')
                        author_name = video_info['author']
                        
                        # 尝试获取UP主详细信息
                        author_data = self.get_author_info(author_uid)
                        print('up主信息123123',author_data)
                        # 如果无法获取或数据不完整，使用视频本身的信息推断
                        
                            
                        author = Author(
                            uid=author_uid,
                            name=author_name,
                            follower_count=author_data.get('follower_count'),  # 估算的粉丝数
                            video_count=author_data.get('video_count'),  # 至少有当前视频
                            total_play_count=author_data.get('total_play_count', 0)  # 至少有当前视频的播放量
                        )
                       
                        db.session.add(author)
                        db.session.flush()  # 获取新插入的 ID
                        self.log_to_console(f"[数据库] 已创建新UP主: {author.name}")
                    else:
                        # 更新现有 UP 主信息
                        if 'author_follower_count' in video_info:
                            author.follower_count = video_info['author_follower_count']
                        if 'author_video_count' in video_info:
                            author.video_count = video_info['author_video_count']
                        if 'author_play_count' in video_info:
                            author.total_play_count = video_info['author_play_count']
                        author.updated_at = datetime.now()
                        self.log_to_console(f"[数据库] 已更新UP主: {author.name}")
                        
                    # 记录 author_id 用于视频
                    author_id = author.id
                except Exception as e:
                    self.log_to_console(f"[警告] 保存 UP 主信息失败: {str(e)}")
                    author_id = None
            else:
                author_id = None
            
            # 检查是否已存在相同BV号的视频
            existing_video = Video.query.filter_by(bvid=video_info['bvid']).first()
            if existing_video:
                # 更新现有记录
                for key, value in video_info.items():
                    if hasattr(existing_video, key) and key != 'author_id':
                        setattr(existing_video, key, value)
                
                # 更新 UP 主关联
                if author_id:
                    existing_video.author_id = author_id
                
                existing_video.updated_at = datetime.now()
                video = existing_video
                self.log_to_console(f"[数据库] 已更新视频: {video.title}")
            else:
                # 创建新记录
                video_data = {
                    'bvid': video_info['bvid'],
                    'title': video_info.get('title', '未知标题'),
                    'author': video_info.get('author', '未知作者'),
                    'video_type': video_info.get('video_type', '未分类'),
                    'play_count': video_info.get('play_count', 0),
                    'danmaku_count': video_info.get('danmaku_count', 0),
                    'like_count': video_info.get('like_count', 0),
                    'coin_count': video_info.get('coin_count', 0),
                    'favorite_count': video_info.get('favorite_count', 0),
                    'share_count': video_info.get('share_count', 0),
                    'comment_count': video_info.get('comment_count', 0),
                    'created_time': video_info.get('created_time', datetime.now())
                }
                
                # 添加 UP 主关联
                if author_id:
                    video_data['author_id'] = author_id
                
                video = Video(**video_data)
                db.session.add(video)
                self.log_to_console(f"[数据库] 已创建新视频: {video.title}")
            
            db.session.commit()
            return video
        
        except Exception as e:
            db.session.rollback()
            self.log_to_console(f"[错误] 保存视频信息失败: {str(e)}")
            return None

    def get_popular_videos(self, ps=20):
        """获取热门视频列表"""
        url = f'https://api.bilibili.com/x/web-interface/popular?ps={ps}&pn=1'
        videos = []
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['code'] == 0:
                videos_list = data['data'].get('list', [])
                
                for item in videos_list:
                    video_info = {
                        'bvid': item['bvid'],
                        'cid': item.get('cid'),
                        'title': item['title'],
                        'author': item['owner']['name'],
                        'video_type': item.get('tname', '未分类'),
                        'play_count': item['stat'].get('view', 0),
                        'danmaku_count': item['stat'].get('danmaku', 0),
                        'like_count': item['stat'].get('like', 0),
                        'coin_count': item['stat'].get('coin', 0),
                        'favorite_count': item['stat'].get('favorite', 0),
                        'share_count': item['stat'].get('share', 0),
                        'comment_count': item['stat'].get('reply', 0),
                        'created_time': datetime.fromtimestamp(item.get('ctime', time.time()))
                    }
                    
                    # 输出到控制台
                    # console_msg = f"[爬取] {item['title']} - UP主: {item['owner']['name']} - 播放量: {item['stat'].get('view', 0)}"
                    self.log_to_console(console_msg)
                    
                    # 发送实时消息
                    self.emit_socket_event('crawl_status', {
                        'title': item['title'],
                        'author': item['owner']['name'],
                        'plays': item['stat'].get('view', 0),
                        'bvid': item['bvid']
                    })
                    
                    videos.append(video_info)
                
                return videos
            else:
                error_msg = data.get('message', '未知错误')
                self.log_to_console(f"[错误] 获取热门视频失败: {error_msg}")
                return []
        except Exception as e:
            self.log_to_console(f"[错误] 获取热门视频异常: {str(e)}")
            return []

    def crawl_videos(self, limit=10, with_danmu=True):
        """爬取热门视频并提供进度更新"""
        self.log_to_console("开始爬取热门视频...")
        
        # 获取排行榜数据
        url = 'https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all'
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['code'] == 0 and 'data' in data and 'list' in data['data']:
                ranking_items = data['data']['list']
                
                if not ranking_items:
                    self.log_to_console("[警告] 排行榜数据为空")
                    return []
                
                videos_data = []
                # 限制爬取数量
                total_videos = min(limit, len(ranking_items))
                
                # 发送开始爬取信号
                self.emit_progress('popular_videos', 0, total_videos, '开始爬取热门视频')
                
                for i, item in enumerate(ranking_items[:total_videos]):
                    try:
                        # 提取视频信息
                        video_info = {
                            'bvid': item['bvid'],
                            'title': item['title'],
                            'author': item['owner']['name'],
                            'author_uid': str(item['owner']['mid']),
                            'play_count': item['stat']['view'],
                            'danmaku_count': item['stat']['danmaku'],
                            'like_count': item['stat']['like'],
                            'coin_count': item['stat']['coin'],
                            'favorite_count': item['stat']['favorite'],
                            'share_count': item['stat']['share'],
                            'comment_count': item['stat']['reply'],
                            'duration': item['duration'],
                            'publish_time': item['pubdate'],
                            'video_type': item.get('tname', '未分类'),
                            'description': item.get('desc', '')
                        }
                        
                        # 获取UP主信息
                        author_info = self.get_author_info(video_info['author_uid'])
                        if author_info:
                            video_info['author_follower_count'] = author_info.get('follower_count', 0)
                            video_info['author_video_count'] = author_info.get('video_count', 0)
                            video_info['author_play_count'] = author_info.get('total_play_count', 0)
                        
                        # 保存信息到数据库
                        self.save_video_to_database(video_info)
                        
                        videos_data.append(video_info)
                        
                        # 如果需要，爬取弹幕
                        if with_danmu:
                            danmu_count = self.crawl_video_danmu(video_info['bvid'], save_to_csv=True, save_to_db=True)
                            self.log_to_console(f"已爬取 {video_info['title']} 的 {danmu_count} 条弹幕")
                        
                        # 更新进度
                        self.emit_progress('popular_videos', i+1, total_videos, 
                                          f'已爬取: {video_info["title"][:20]}...',
                                          {'video_info': {
                                              'title': video_info['title'],
                                              'bvid': video_info['bvid'],
                                              'author': video_info['author'],
                                              'play_count': video_info['play_count']
                                          }})
                        
                        # 适当延迟，避免请求过快
                        time.sleep(1)
                        
                    except Exception as e:
                        self.log_to_console(f"[错误] 处理视频 {item.get('title', '未知')} 时失败: {str(e)}")
                        # 即使失败也更新进度
                        self.emit_progress('popular_videos', i+1, total_videos, 
                                          f'处理失败: {item.get("title", "未知")[:20]}...',
                                          {'error': str(e)})
                
                self.emit_progress('popular_videos', total_videos, total_videos, 
                                  f'爬取完成，共 {len(videos_data)} 个视频',
                                  {'success_count': len(videos_data)})
                
                return videos_data
            else:
                error_msg = data.get('message', '未知错误')
                self.log_to_console(f"[错误] 获取排行榜失败: {error_msg}")
                self.emit_progress('popular_videos', 0, 0, f'获取排行榜失败: {error_msg}', {'error': error_msg})
                return []
        except Exception as e:
            self.log_to_console(f"[错误] 爬取排行榜异常: {str(e)}")
            self.emit_progress('popular_videos', 0, 0, f'爬取异常: {str(e)}', {'error': str(e)})
            return []

    def get_danmu(self, cid):
        """获取视频弹幕内容"""
        if not cid:
            self.log_to_console("[错误] 无法获取弹幕: CID为空")
            return []
            
        danmu_url = f'https://comment.bilibili.com/{cid}.xml'
        danmu_list = []
        
        try:
            response = requests.get(danmu_url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                
                # 控制台输出
                total_danmu = len(root.findall('./d'))
                self.log_to_console(f"[弹幕] 获取到 {total_danmu} 条弹幕")
                
                for d in root.findall('./d'):
                    attr_str = d.attrib.get('p', '')
                    attrs = attr_str.split(',')
                    
                    if len(attrs) >= 8:
                        appear_time = float(attrs[0])  # 弹幕出现时间(秒)
                        mode = int(attrs[1])  # 弹幕类型
                        font_size = int(attrs[2])  # 字体大小
                        color = int(attrs[3])  # 颜色
                        timestamp = int(attrs[4])  # 发送时间戳
                        pool = int(attrs[5])  # 弹幕池
                        user_hash = attrs[6]  # 用户hash
                        row_id = int(attrs[7])  # 行ID
                        
                        # 把时间戳转换成可读的日期格式
                        send_time = datetime.fromtimestamp(timestamp)
                        
                        # 弹幕内容
                        content = d.text if d.text else ""
                        
                        danmu_list.append({
                            'content': content,
                            'appear_time': appear_time,
                            'mode': mode, 
                            'font_size': font_size,
                            'color': color,
                            'created_time': send_time,
                            'user_hash': user_hash,
                            'row_id': row_id
                        })
                
                # 发送弹幕爬取状态
                self.emit_socket_event('danmu_status', {
                    'count': len(danmu_list),
                    'cid': cid
                })
                
                return danmu_list
            else:
                self.log_to_console(f"[错误] 获取弹幕失败，状态码: {response.status_code}")
        except Exception as e:
            self.log_to_console(f"[错误] 获取弹幕异常: {str(e)}")
        
        return []
        
    def save_danmu_to_csv(self, danmu_list, output_file):
        """保存弹幕数据到CSV文件"""
        try:
            if not danmu_list:
                self.log_to_console("[警告] 没有弹幕数据可保存")
                return False
            
            df = pd.DataFrame(danmu_list)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            
            self.log_to_console(f"[成功] 已保存{len(danmu_list)}条弹幕到{output_file}")
            return True
        except Exception as e:
            self.log_to_console(f"[错误] 保存弹幕数据失败: {str(e)}")
            return False
    
    def get_danmu_from_url(self, url):
        """通过视频URL获取弹幕"""
        bvid = None
        
        # 尝试从URL中提取BV号
        bvid_pattern = r'BV\w+' 
        match = re.search(bvid_pattern, url)
        
        if match:
            bvid = match.group()
        else:
            # 如果找不到BV号，尝试从页面中提取
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                html_bvid = re.search(r'"bvid":"(BV\w+)"', response.text)
                if html_bvid:
                    bvid = html_bvid.group(1)
            except Exception as e:
                self.log_to_console(f"[错误] 解析视频URL失败: {str(e)}")
                return None, []
            
        if not bvid:
            self.log_to_console("[错误] 无法从URL中提取BV号")
            return None, []
        
        # 获取视频信息和CID
        video_info = self.get_video_info(bvid)
        if not video_info or 'cid' not in video_info:
            self.log_to_console(f"[错误] 无法获取视频 {bvid} 的信息或CID")
            return None, []
            
        # 获取弹幕
        danmu_list = self.get_danmu(video_info['cid'])
        
        return video_info, danmu_list
            
    def save_danmu_to_database(self, video_info, danmu_list):
        """保存弹幕数据到数据库"""
        if not danmu_list or not video_info:
            return 0
        
        try:
            # 确保在应用上下文中执行
            if self.app:
                with self.app.app_context():
                    from app.models.danmu import Danmu
                    from app.models.video import Video
                    return self._save_danmu_to_db(video_info, danmu_list, Video, Danmu)
            else:
                try:
                    from app.models.danmu import Danmu
                    from app.models.video import Video
                    return self._save_danmu_to_db(video_info, danmu_list, Video, Danmu)
                except Exception as e:
                    self.log_to_console(f"[错误] 无法在当前上下文中操作数据库: {str(e)}")
                    return 0
                
        except Exception as e:
            self.log_to_console(f"[错误] 保存弹幕数据到数据库失败: {str(e)}")
            return 0

    def _save_danmu_to_db(self, video_info, danmu_list, Video, Danmu):
        """实际的弹幕保存操作"""
        try:
            # 先保存视频信息并获取视频ID
            video = None
            video_id = None
            video_bvid = None
            video_title = None
            
            # 检查视频是否已存在
            existing_video = Video.query.filter_by(bvid=video_info['bvid']).first()
            if existing_video:
                video_id = existing_video.id
                video_bvid = existing_video.bvid
                video_title = existing_video.title
            else:
                # 创建新视频记录
                video = Video(
                    bvid=video_info['bvid'],
                    title=video_info.get('title', '未知标题'),
                    author=video_info.get('author', '未知作者'),
                    video_type=video_info.get('video_type', '未分类'),
                    play_count=video_info.get('play_count', 0),
                    danmaku_count=video_info.get('danmaku_count', 0),
                    like_count=video_info.get('like_count', 0),
                    coin_count=video_info.get('coin_count', 0),
                    favorite_count=video_info.get('favorite_count', 0),
                    share_count=video_info.get('share_count', 0),
                    comment_count=video_info.get('comment_count', 0),
                    created_time=video_info.get('created_time', datetime.now())
                )
                db.session.add(video)
                db.session.flush()  # 获取新插入记录的ID
                video_id = video.id
                video_bvid = video.bvid
                video_title = video.title
            
            saved_count = 0
            # 批量处理弹幕
            batch_size = 100
            danmu_batch = []
            
            for danmu in danmu_list:
                try:
                    # 检查是否已存在相同的弹幕
                    existing_danmu = Danmu.query.filter_by(
                        video_id=video_id,
                        content=danmu['content'],
                        appear_time=danmu['appear_time']
                    ).first()
                    
                    if not existing_danmu:
                        # 创建新弹幕记录
                        new_danmu = Danmu(
                            video_id=video_id,
                            video_bvid=video_bvid,
                            video_title=video_title,
                            content=danmu['content'],
                            appear_time=danmu['appear_time'],
                            mode=danmu['mode'],
                            font_size=danmu['font_size'],
                            color=danmu['color'],
                            created_time=danmu['created_time'],
                            user_hash=danmu['user_hash']
                        )
                        danmu_batch.append(new_danmu)
                        saved_count += 1
                        
                        # 当批次达到指定大小时提交
                        if len(danmu_batch) >= batch_size:
                            db.session.bulk_save_objects(danmu_batch)
                            db.session.commit()
                            self.log_to_console(f"[数据库] 已保存 {saved_count} 条弹幕")
                            danmu_batch = []
                            
                except Exception as e:
                    self.log_to_console(f"[警告] 处理单条弹幕失败: {str(e)}")
                    continue
            
            # 保存剩余的弹幕
            if danmu_batch:
                try:
                    db.session.bulk_save_objects(danmu_batch)
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    self.log_to_console(f"[错误] 保存最后一批弹幕失败: {str(e)}")
                    return saved_count - len(danmu_batch)
            
            self.log_to_console(f"[数据库] 成功保存 {saved_count} 条弹幕")
            return saved_count
            
        except Exception as e:
            db.session.rollback()
            self.log_to_console(f"[错误] 保存弹幕数据失败: {str(e)}")
            return 0
            
    def crawl_video_danmu(self, bvid_or_url, save_to_csv=True, save_to_db=True):
        """爬取视频弹幕"""
        self.log_to_console(f"\n{'=' * 50}")
        self.log_to_console(f"开始爬取弹幕 - {bvid_or_url}")
        self.log_to_console(f"{'=' * 50}\n")
        
        video_info = None
        danmu_list = []
        
        try:
            # 发送爬取开始的消息
            self.emit_socket_event('danmu_start', {
                'bvid': bvid_or_url if not bvid_or_url.startswith('http') else '从URL爬取'
            })
            
            # 判断输入是URL还是BV号
            if bvid_or_url.startswith('http'):
                video_info, danmu_list = self.get_danmu_from_url(bvid_or_url)
            else:
                # 作为BV号处理
                bvid = bvid_or_url
                video_info = self.get_video_info(bvid)
                if video_info and 'cid' in video_info:
                    danmu_list = self.get_danmu(video_info['cid'])
            
            # 如果成功获取到弹幕
            if danmu_list and video_info:
                # 发送进度更新
                self.emit_socket_event('danmu_progress', {
                    'current': len(danmu_list),
                    'total': len(danmu_list),
                    'percent': 100,
                    'bvid': video_info['bvid']
                })
                
                # 保存到数据库
                if save_to_db:
                    with self.app.app_context():
                        saved_count = self.save_danmu_to_database(video_info, danmu_list)
                        
                        # 发送数据库保存状态
                        self.emit_socket_event('danmu_db_saved', {
                            'bvid': video_info['bvid'],
                            'count': saved_count
                        })
                
                # 保存到CSV
                if save_to_csv:
                    filename = f"danmu_{video_info['bvid']}.csv"
                    self.save_danmu_to_csv(danmu_list, filename)
                
                # 发送完成事件
                self.emit_socket_event('danmu_complete', {
                    'bvid': video_info['bvid'] if video_info else bvid_or_url,
                    'title': video_info['title'] if video_info else '未知视频',
                    'count': len(danmu_list),
                    'file': filename if save_to_csv else None
                })
            
            self.log_to_console(f"\n{'=' * 50}")
            self.log_to_console(f"弹幕爬取完成 - 共 {len(danmu_list)} 条弹幕")
            self.log_to_console(f"{'=' * 50}\n")
            
            return danmu_list
                
        except Exception as e:
            error_msg = f'爬取弹幕失败: {str(e)}'
            self.log_to_console(f"\n[错误] {error_msg}")
            
            self.emit_socket_event('danmu_error', {
                'message': str(e)
            })
            
            return []
            
    def crawl_multiple_video_danmu(self, video_list, save_to_csv=True, save_to_db=True):
        """批量爬取多个视频的弹幕"""
        results = []
        total = len(video_list)
        
        self.log_to_console(f"\n{'=' * 50}")
        self.log_to_console(f"开始批量爬取弹幕 - 总计 {total} 个视频")
        self.log_to_console(f"{'=' * 50}\n")
        
        # 发送开始爬取的消息
        self.emit_socket_event('danmu_batch_start', {
            'total': total
        })
        
        for i, video in enumerate(video_list):
            # 更新进度
            self.log_to_console(f"正在爬取第 {i+1}/{total} 个视频的弹幕")
            
            # 发送爬取进度
            self.emit_socket_event('danmu_batch_status', {
                'current': i + 1,
                'total': total,
                'percent': round((i + 1) / total * 100, 1)
            })
            
            # 爬取弹幕
            danmu_list = self.crawl_video_danmu(video, save_to_csv, save_to_db)
            
            if danmu_list:
                results.append({
                    'video': video,
                    'danmu_count': len(danmu_list)
                })
                
            # 防止请求过快
            time.sleep(2)
        
        # 发送批量爬取完成的消息
        self.emit_socket_event('danmu_batch_complete', {
            'success_count': len(results),
            'total': total
        })
        
        self.log_to_console(f"\n{'=' * 50}")
        self.log_to_console(f"批量爬取完成 - 成功获取 {len(results)}/{total} 个视频的弹幕")
        self.log_to_console(f"{'=' * 50}\n")
        
        return results

    def start_crawl_task(self, task_type='popular', limit=10, bvid=None, url=None):
        """启动爬虫任务并显示进度"""
        self.log_to_console(f"\n{'=' * 50}")
        self.log_to_console(f"正在启动爬虫任务... - 类型: {task_type}")
        self.log_to_console(f"{'=' * 50}\n")
        
        # 发送任务开始事件
        self.emit_socket_event('crawl_task_start', {
            'type': task_type,
            'limit': limit,
            'bvid': bvid,
            'url': url
        })
        
        results = []
        
        try:
            if task_type == 'popular':
                # 爬取热门视频
                self.log_to_console("开始爬取热门视频...")
                videos = self.crawl_videos(limit=limit, with_danmu=True)  # 默认同时爬取弹幕
                
                if videos:
                    self.log_to_console(f"成功爬取 {len(videos)} 个热门视频")
                    results = videos
                    
                    # 发送任务完成事件
                    self.emit_socket_event('crawl_task_complete', {
                        'type': 'popular',
                        'count': len(videos),
                        'message': f"成功爬取 {len(videos)} 个热门视频"
                    })
                else:
                    self.log_to_console("未获取到热门视频数据")
                    # 发送任务失败事件
                    self.emit_socket_event('crawl_task_error', {
                        'type': 'popular',
                        'message': "未获取到热门视频数据"
                    })
                    
            elif task_type == 'danmu':
                # 爬取指定视频的弹幕
                target = bvid or url
                if not target:
                    self.log_to_console("[错误] 未指定视频BV号或URL")
                    self.emit_socket_event('crawl_task_error', {
                        'type': 'danmu',
                        'message': "未指定视频BV号或URL"
                    })
                    return []
                    
                self.log_to_console(f"开始爬取视频 {target} 的弹幕...")
                danmu_list = self.crawl_video_danmu(target, save_to_csv=True, save_to_db=True)
                
                if danmu_list:
                    self.log_to_console(f"成功爬取 {len(danmu_list)} 条弹幕")
                    results = danmu_list
                    
                    # 发送任务完成事件
                    self.emit_socket_event('crawl_task_complete', {
                        'type': 'danmu',
                        'count': len(danmu_list),
                        'message': f"成功爬取 {len(danmu_list)} 条弹幕"
                    })
                else:
                    self.log_to_console("未获取到弹幕数据")
                    # 发送任务失败事件
                    self.emit_socket_event('crawl_task_error', {
                        'type': 'danmu',
                        'message': "未获取到弹幕数据"
                    })
                    
            elif task_type == 'batch_danmu':
                # 批量爬取多个视频的弹幕
                if not limit or limit <= 0:
                    limit = 5
                    
                self.log_to_console(f"开始批量爬取 {limit} 个热门视频的弹幕...")
                results = self.crawl_batch_danmu(limit=limit)
                
                if results:
                    self.log_to_console(f"成功批量爬取 {len(results)} 个视频的弹幕")
                    # 发送任务完成事件
                    self.emit_socket_event('crawl_task_complete', {
                        'type': 'batch_danmu',
                        'count': len(results),
                        'message': f"成功批量爬取 {len(results)} 个视频的弹幕"
                    })
                else:
                    self.log_to_console("批量爬取弹幕失败")
                    # 发送任务失败事件
                    self.emit_socket_event('crawl_task_error', {
                        'type': 'batch_danmu',
                        'message': "批量爬取弹幕失败"
                    })
            
            return results
            
        except Exception as e:
            self.log_to_console(f"[错误] 爬虫任务执行失败: {str(e)}")
            # 发送任务失败事件
            self.emit_socket_event('crawl_task_error', {
                'type': task_type,
                'message': f"爬虫任务执行失败: {str(e)}"
            })
            return []

    def set_progress_callback(self, callback):
        """设置进度回调函数"""
        self.progress_callback = callback

    def update_progress(self, current, total, item=None):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(current, total, item)

    def emit_progress(self, task_type, current, total, message=None, extra_data=None):
        """发送爬取进度更新"""
        from app import socketio
        from datetime import datetime
        
        progress = {
            'task_type': task_type,
            'current': current,
            'total': total,
            'percentage': round(current / total * 100, 2) if total > 0 else 0,
            'message': message,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        
        if extra_data:
            progress.update(extra_data)
        
        try:
            # 通过Socket.IO发送进度更新
            socketio.emit('crawl_progress', progress)
            # 也输出到控制台
            self.log_to_console(f"[进度] {progress['task_type']}: {progress['current']}/{progress['total']} ({progress['percentage']}%) - {progress['message'] or ''}")
        except Exception as e:
            self.log_to_console(f"[警告] 发送进度更新失败: {str(e)}")


# 使用示例
if __name__ == "__main__":
    print("=== B站爬虫模块直接运行 ===")
    crawler = BilibiliCrawler()
    
    # 爬取热门视频
    print("\n爬取热门视频...")
    videos = crawler.crawl_videos(limit=5)
    
    if videos:
        print(f"\n成功爬取 {len(videos)} 个视频")
    else:
        print("未获取到视频数据")