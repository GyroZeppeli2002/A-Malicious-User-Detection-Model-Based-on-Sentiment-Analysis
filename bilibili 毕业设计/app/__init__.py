import sys
import platform
from threading import Thread

if platform.system() != 'Windows':
    import eventlet
    eventlet.monkey_patch()
else:
    # Windows 系统使用替代方案
    from gevent import monkey
    monkey.patch_all()

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_login import LoginManager
from config import Config
import os

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'info'

# 检查是否禁用 Socket.IO 服务器
disable_socketio_server = os.environ.get('DISABLE_SOCKETIO_SERVER', 'false').lower() == 'true'

# 确保 socketio 在这里初始化，并设置 async_mode
socketio = SocketIO(
    async_mode='eventlet',
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    message_queue='memory://' if disable_socketio_server else None,
    ping_timeout=60,  # 增加超时时间
    ping_interval=25  # 增加心跳间隔
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    
    # 初始化 socketio 并传入 app
    socketio.init_app(app)
    login_manager.init_app(app)

    # 注册蓝图
    from app.controllers.main import main_bp
    from app.controllers.auth import auth_bp
    from app.controllers.user_detection import detection_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(detection_bp)
    
    # 添加自定义过滤器
    @app.template_filter('format_number')
    def format_number(value):
        """格式化数字，添加千位分隔符"""
        return "{:,}".format(int(value))
    
    # 添加命令行命令
    @app.cli.command('crawl')
    def crawl_command():
        """爬取B站数据"""
        from app.utils.crawler import BilibiliCrawler
        crawler = BilibiliCrawler(app=app)
        with app.app_context():
            videos = crawler.crawl_videos(limit=10)
            if videos:
                print(f"成功爬取 {len(videos)} 个视频")
            else:
                print("未获取到视频数据")
    
    # 添加弹幕爬取命令
    @app.cli.command('crawl-danmu')
    def crawl_danmu_command():
        """爬取B站视频弹幕"""
        import click
        from app.utils.crawler import BilibiliCrawler
        
        bvid = click.prompt('请输入视频BV号', type=str)
        crawler = BilibiliCrawler(app=app)
        
        with app.app_context():
            click.echo(f"开始爬取视频 {bvid} 的弹幕...")
            danmu_list = crawler.crawl_video_danmu(bvid, save_to_csv=True, save_to_db=True)
            
            if danmu_list:
                click.echo(f"成功爬取 {len(danmu_list)} 条弹幕")
            else:
                click.echo("未获取到弹幕数据")
    
    # 清除路由缓存
    with app.app_context():
        app.url_map.update()
    
    @login_manager.user_loader
    def load_user(id):
        from app.models.user import User
        return User.query.get(int(id))
    
    return app

from app import models

# 导入模型以便迁移
from app.models.danmu import Danmu
from app.models.video import Video
from app.models.author import Author

# 替换原来的 eventlet 相关代码
def run_async(func):
    def wrapper(*args, **kwargs):
        thread = Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper