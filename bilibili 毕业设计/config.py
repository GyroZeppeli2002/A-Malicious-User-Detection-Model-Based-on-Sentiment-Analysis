import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'bilibili-data-analysis'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'bilibili.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 爬虫配置
    BILIBILI_COOKIE = os.environ.get('BILIBILI_COOKIE', '')
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    
    # 分页配置
    POSTS_PER_PAGE = 10