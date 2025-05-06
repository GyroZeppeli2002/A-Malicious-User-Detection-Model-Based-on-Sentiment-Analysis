from flask import Blueprint, render_template, jsonify, request, current_app, flash, redirect, url_for
from app.services.user_detection import MaliciousUserDetectionService
from app.models.danmu import Danmu
from app.models.video import Video
from app import db
from flask_login import login_required
import json
from sqlalchemy.sql import func, distinct

detection_bp = Blueprint('detection', __name__, url_prefix='/detection')

@detection_bp.route('/')
@login_required
def index():
    """恶意用户检测页面"""
    # 获取所有有弹幕的视频
    videos_with_danmu = db.session.query(Video, db.func.count(Danmu.id).label('danmu_count'))\
        .join(Danmu, Video.id == Danmu.video_id)\
        .group_by(Video.id)\
        .order_by(db.desc('danmu_count'))\
        .all()
    
    return render_template('detection/index.html', videos=videos_with_danmu)

@detection_bp.route('/api/detect', methods=['POST'])
@login_required
def detect_malicious_users():
    """检测恶意用户API"""
    data = request.json
    video_id = data.get('video_id')
    threshold = data.get('threshold', 0.7)
    
    try:
        # 检测恶意用户
        malicious_users = MaliciousUserDetectionService.detect_malicious_users(
            video_id=video_id, 
            threshold=float(threshold)
        )
        
        # 计算统计数据
        stats = {
            'total_users': 0,
            'malicious_count': len(malicious_users),
            'by_type': {
                'negative_emotion': 0,
                'unsupport': 0,
                'sensitive': 0,
                'spam': 0,
                'other': 0
            },
            'score_distribution': {
                '0.9-1.0': 0,
                '0.8-0.9': 0,
                '0.7-0.8': 0,
                '0.6-0.7': 0,
                '0.5-0.6': 0,
                '0.4-0.5': 0,
                '0.3-0.4': 0,
                '0.2-0.3': 0,
                '0.1-0.2': 0,
                '0.0-0.1': 0
            }
        }
        
        # 获取总用户数
        if video_id:
            stats['total_users'] = db.session.query(func.count(distinct(Danmu.user_hash))).filter(Danmu.video_id == video_id).scalar()
        else:
            stats['total_users'] = db.session.query(func.count(distinct(Danmu.user_hash))).scalar()
        
        # 分析恶意用户类型
        for user in malicious_users:
            # 分析主要恶意类型
            scores = user['details']['scores']
            max_score_type = max(
                ('negative_emotion', scores.get('negative_emotion_score', 0)),
                ('unsupport', scores.get('unsupport_score', 0)),
                ('sensitive', scores.get('sensitive_score', 0)),
                ('spam', scores.get('spam_score', 0)),
                ('other', scores.get('burst_score', 0) + scores.get('duplicate_score', 0) + scores.get('cross_spam_score', 0))
            , key=lambda x: x[1])[0]
            
            stats['by_type'][max_score_type] += 1
            
            # 分析分数分布
            score = user['score']
            if score >= 0.9:
                stats['score_distribution']['0.9-1.0'] += 1
            elif score >= 0.8:
                stats['score_distribution']['0.8-0.9'] += 1
            elif score >= 0.7:
                stats['score_distribution']['0.7-0.8'] += 1
            elif score >= 0.6:
                stats['score_distribution']['0.6-0.7'] += 1
            elif score >= 0.5:
                stats['score_distribution']['0.5-0.6'] += 1
            elif score >= 0.4:
                stats['score_distribution']['0.4-0.5'] += 1
            elif score >= 0.3:
                stats['score_distribution']['0.3-0.4'] += 1
            elif score >= 0.2:
                stats['score_distribution']['0.2-0.3'] += 1
            elif score >= 0.1:
                stats['score_distribution']['0.1-0.2'] += 1
            else:
                stats['score_distribution']['0.0-0.1'] += 1
        
        return jsonify({
            'status': 'success',
            'count': len(malicious_users),
            'users': malicious_users,
            'stats': stats
        })
    except Exception as e:
        current_app.logger.error(f"恶意用户检测失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"检测失败: {str(e)}"
        }), 500

@detection_bp.route('/api/user/<user_hash>')
@login_required
def get_user_activity(user_hash):
    """获取用户活动记录API"""
    try:
        activity = MaliciousUserDetectionService.get_user_activity(user_hash)
        return jsonify({
            'status': 'success',
            'data': activity
        })
    except Exception as e:
        current_app.logger.error(f"获取用户活动记录失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f"获取失败: {str(e)}"
        }), 500

@detection_bp.route('/user/<user_hash>')
@login_required
def user_detail(user_hash):
    """用户详情页面"""
    try:
        # 获取用户活动记录（包含情感和行为分析）
        activity = MaliciousUserDetectionService.get_user_activity(user_hash)
        
        # 获取用户行为模式分析
        behavior_patterns = MaliciousUserDetectionService.analyze_user_behavior_patterns(user_hash)
        
        return render_template('detection/user_detail.html', 
                              user_hash=user_hash, 
                              activity=activity,
                              behavior_patterns=behavior_patterns)
    except Exception as e:
        current_app.logger.error(f"获取用户详情失败: {str(e)}")
        flash(f"获取用户详情失败: {str(e)}", "danger")
        return redirect(url_for('detection.index')) 