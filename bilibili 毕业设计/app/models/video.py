from app import db
from datetime import datetime

class Video(db.Model):
    """视频信息模型"""
    __tablename__ = 'videos'
    
    id = db.Column(db.Integer, primary_key=True)
    bvid = db.Column(db.String(20), unique=True, index=True, nullable=False, comment='视频BV号')
    cid = db.Column(db.BigInteger, index=True, comment='视频CID')
    title = db.Column(db.String(255), nullable=False, comment='视频标题')
    author = db.Column(db.String(100), comment='UP主名称')
    author_uid = db.Column(db.String(20))
    video_type = db.Column(db.String(50), comment='视频分类')
    
    # 统计数据
    play_count = db.Column(db.Integer, default=0, comment='播放量')
    danmaku_count = db.Column(db.Integer, default=0, comment='弹幕数')
    like_count = db.Column(db.Integer, default=0, comment='点赞数')
    coin_count = db.Column(db.Integer, default=0, comment='投币数')
    favorite_count = db.Column(db.Integer, default=0, comment='收藏数')
    share_count = db.Column(db.Integer, default=0, comment='分享数')
    comment_count = db.Column(db.Integer, default=0, comment='评论数')
    
    # 时间信息
    created_time = db.Column(db.DateTime, comment='视频创建时间')
    crawled_at = db.Column(db.DateTime, default=datetime.now, comment='爬取时间')
    
    # 关联弹幕
    danmus = db.relationship('Danmu', backref='video_info', lazy='dynamic', 
                             foreign_keys='Danmu.video_id')
    
    # 在 Video 模型中添加 author_id 字段，并为外键约束指定名称
    author_id = db.Column(db.Integer, db.ForeignKey('authors.id', name='fk_video_author'), index=True)
    
    def __repr__(self):
        return f'<Video {self.bvid}: {self.title}>'
    
    @staticmethod
    def save_video_info(video_info):
        """保存视频信息到数据库"""
        if not video_info:
            return None
            
        # 检查视频是否已存在
        existing_video = Video.query.filter_by(bvid=video_info['bvid']).first()
        if existing_video:
            # 更新现有记录
            existing_video.cid = video_info.get('cid', existing_video.cid)
            existing_video.title = video_info.get('title', existing_video.title)
            existing_video.author = video_info.get('author', existing_video.author)
            existing_video.video_type = video_info.get('video_type', existing_video.video_type)
            existing_video.play_count = video_info.get('play_count', existing_video.play_count)
            existing_video.danmaku_count = video_info.get('danmaku_count', existing_video.danmaku_count)
            existing_video.like_count = video_info.get('like_count', existing_video.like_count)
            existing_video.coin_count = video_info.get('coin_count', existing_video.coin_count)
            existing_video.favorite_count = video_info.get('favorite_count', existing_video.favorite_count)
            existing_video.share_count = video_info.get('share_count', existing_video.share_count)
            existing_video.comment_count = video_info.get('comment_count', existing_video.comment_count)
            existing_video.created_time = video_info.get('created_time', existing_video.created_time)
            existing_video.crawled_at = datetime.now()
            
            video = existing_video
        else:
            # 创建新记录
            video = Video(
                bvid=video_info['bvid'],
                cid=video_info.get('cid'),
                title=video_info.get('title', '未知标题'),
                author=video_info.get('author'),
                video_type=video_info.get('video_type'),
                play_count=video_info.get('play_count', 0),
                danmaku_count=video_info.get('danmaku_count', 0),
                like_count=video_info.get('like_count', 0),
                coin_count=video_info.get('coin_count', 0),
                favorite_count=video_info.get('favorite_count', 0),
                share_count=video_info.get('share_count', 0),
                comment_count=video_info.get('comment_count', 0),
                created_time=video_info.get('created_time')
            )
            db.session.add(video)
            
        try:
            db.session.commit()
            return video
        except Exception as e:
            db.session.rollback()
            raise e 