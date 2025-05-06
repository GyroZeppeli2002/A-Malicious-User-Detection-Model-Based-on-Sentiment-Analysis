from app import db
from datetime import datetime

class Danmu(db.Model):
    """弹幕数据模型"""
    __tablename__ = 'danmu'
    
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('videos.id', name='fk_danmu_video'), index=True)
    video_bvid = db.Column(db.String(20), index=True, nullable=False, comment='视频BV号')
    video_title = db.Column(db.String(255), comment='视频标题')
    
    content = db.Column(db.Text, nullable=False, comment='弹幕内容')
    appear_time = db.Column(db.Float, comment='弹幕出现时间(秒)')
    mode = db.Column(db.Integer, comment='弹幕类型')
    font_size = db.Column(db.Integer, comment='字体大小')
    color = db.Column(db.Integer, comment='颜色')
    user_hash = db.Column(db.String(50), comment='用户hash')
    created_time = db.Column(db.DateTime, comment='弹幕发送时间')
    
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Danmu {self.id}: {self.content[:20]}>'
    
    @staticmethod
    def save_danmu_list(video_info, danmu_list):
        """批量保存弹幕列表到数据库"""
        if not danmu_list or not video_info:
            return 0
        
        # 先保存视频信息，获取视频ID
        from app.models.video import Video
        video = Video.save_video_info(video_info)
        
        if not video:
            return 0
            
        danmu_objects = []
        for danmu in danmu_list:
            danmu_obj = Danmu(
                video_id=video.id,
                video_bvid=video_info['bvid'],
                video_title=video_info['title'],
                content=danmu['content'],
                appear_time=danmu['appear_time'],
                mode=danmu['mode'],
                font_size=danmu['font_size'],
                color=danmu['color'],
                user_hash=danmu['user_hash'],
                created_time=danmu['send_time']
            )
            danmu_objects.append(danmu_obj)
            
        try:
            db.session.bulk_save_objects(danmu_objects)
            db.session.commit()
            return len(danmu_objects)
        except Exception as e:
            db.session.rollback()
            raise e 