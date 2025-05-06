from app import db
from datetime import datetime

class Author(db.Model):
    """UP主信息模型"""
    __tablename__ = 'authors'
    
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(20), unique=True, index=True, nullable=False, comment='UP主UID')
    name = db.Column(db.String(100), nullable=False, comment='UP主名称')
    follower_count = db.Column(db.Integer, default=0, comment='粉丝数')
    video_count = db.Column(db.Integer, default=0, comment='视频数')
    total_play_count = db.Column(db.BigInteger, default=0, comment='总播放量')
    
    # 关联视频
    videos = db.relationship('Video', backref='author_info', lazy='dynamic')
    
    # 时间信息
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    def __repr__(self):
        return f'<Author {self.uid}: {self.name}>'
    
    @staticmethod
    def save_author_info(author_info):
        """保存UP主信息到数据库"""
        if not author_info:
            return None
            
        # 检查UP主是否已存在
        existing_author = Author.query.filter_by(uid=author_info['uid']).first()
        if existing_author:
            # 更新现有记录
            existing_author.name = author_info.get('name', existing_author.name)
            existing_author.follower_count = author_info.get('follower_count', existing_author.follower_count)
            existing_author.video_count = author_info.get('video_count', existing_author.video_count)
            existing_author.total_play_count = author_info.get('total_play_count', existing_author.total_play_count)
            existing_author.updated_at = datetime.now()
            
            author = existing_author
        else:
            # 创建新记录
            author = Author(
                uid=author_info['uid'],
                name=author_info.get('name', '未知UP主'),
                follower_count=author_info.get('follower_count', 0),
                video_count=author_info.get('video_count', 0),
                total_play_count=author_info.get('total_play_count', 0)
            )
            db.session.add(author)
            
        try:
            db.session.commit()
            return author
        except Exception as e:
            db.session.rollback()
            raise e 