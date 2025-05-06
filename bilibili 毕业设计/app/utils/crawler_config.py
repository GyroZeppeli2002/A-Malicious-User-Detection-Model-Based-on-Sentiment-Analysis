"""爬虫配置"""

# 爬虫默认配置
DEFAULT_CONFIG = {
    # 用户代理
    'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    
    # 请求间隔（秒）
    'REQUEST_DELAY': 0.5,
    
    # 最大重试次数
    'MAX_RETRIES': 3,
    
    # 超时时间（秒）
    'TIMEOUT': 10,
    
    # 是否保存到CSV
    'SAVE_TO_CSV': True,
    
    # 是否保存到数据库
    'SAVE_TO_DB': True,
    
    # CSV文件保存路径
    'CSV_PATH': 'data/danmu',
    
    # 日志级别
    'LOG_LEVEL': 'INFO'
}

def get_config():
    """获取爬虫配置"""
    # 这里可以从环境变量、配置文件等获取配置
    # 暂时直接返回默认配置
    return DEFAULT_CONFIG 