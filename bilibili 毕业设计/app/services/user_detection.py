from app import db
from app.models.danmu import Danmu
from collections import Counter
import re
import jieba.analyse
from sqlalchemy import func, text
import numpy as np
from datetime import datetime, timedelta
from snownlp import SnowNLP  # 添加SnowNLP用于情感分析

class MaliciousUserDetectionService:
    """恶意用户检测服务"""
    
    # 敏感词列表
    SENSITIVE_WORDS = [
        '傻逼', '垃圾', '废物', '脑残', '白痴', '智障', '滚', '操', '草', '艹', 
        '妈的', '煞笔', '贱', '死', '滚蛋', '混蛋', '骗子', '骗', '垃圾', '辣鸡',
        '举报', '封号', '封', '黑粉', '黑', '水军', '网军', '带节奏', '引战'
    ]
    
    # 垃圾信息模式
    SPAM_PATTERNS = [
        r'(关注|点赞|投币|三连|一键三连).*(送|抽|赠|中奖)',
        r'(抽|送|赠).*(关注|点赞)',
        r'私信.*(送|赠)',
        r'加V|加微信|QQ群|私聊',
        r'免费|特价|优惠|打折|促销',
        r'(代|帮).*(刷|赚|做)',
        r'兼职|招聘|招募|招人|找人',
        r'(涨|刷|买).*(粉|赞|播放|投币)',
        r'(教|分享).*(赚钱|日入|月入)'
    ]
    
    # 负面情绪词汇
    NEGATIVE_EMOTION_WORDS = [
        '失望', '难过', '伤心', '痛苦', '悲伤', '愤怒', '生气', '烦躁', '厌恶', '讨厌',
        '恨', '恼火', '不满', '不爽', '郁闷', '烦', '烦人', '无聊', '无趣', '无语',
        '吐了', '呕', '恶心', '难受', '差劲', '糟糕', '可怕', '惨', '惨不忍睹', '崩溃',
        '绝望', '哭', '哭了', '泪', '泪目', '心碎', '心痛', '心疼', '心寒', '心凉'
    ]
    
    # 不支持行为模式
    UNSUPPORT_PATTERNS = [
        r'不(会|想|愿意|可能|打算|准备)?(点赞|投币|收藏|三连)',
        r'(取消|撤销)(点赞|投币|收藏|关注)',
        r'(不值得|不配|不该|不应该)(点赞|投币|收藏|三连)',
        r'白嫖',
        r'(看完就走|看完就跑)',
        r'(不关注|取关)',
        r'(差评|踩|倒赞)'
    ]
    
    @staticmethod
    def detect_malicious_users(video_id=None, threshold=0.7):
        """
        检测恶意用户
        
        参数:
            video_id: 视频ID，如果为None则检测所有视频
            threshold: 恶意分数阈值，超过此值被判定为恶意用户
            
        返回:
            恶意用户列表，每个元素包含用户hash、恶意分数和详细信息
        """
        # 基础查询
        query = db.session.query(Danmu.user_hash, Danmu.content, Danmu.appear_time, 
                                Danmu.created_time, Danmu.video_id, Danmu.video_title)
        
        # 如果指定了视频ID，则只检测该视频的弹幕
        if video_id:
            query = query.filter(Danmu.video_id == video_id)
        
        # 获取所有弹幕
        danmus = query.all()
        
        # 打印弹幕数量
        print(f"获取到 {len(danmus)} 条弹幕")
        
        # 按用户分组
        user_danmus = {}
        for danmu in danmus:
            if danmu.user_hash not in user_danmus:
                user_danmus[danmu.user_hash] = []
            user_danmus[danmu.user_hash].append(danmu)
        
        # 分析每个用户
        malicious_users = []
        for user_hash, user_danmu_list in user_danmus.items():
            # 如果用户弹幕数量太少，跳过 (恢复过滤条件，但降低阈值)
            if len(user_danmu_list) < 2:
                continue
            
            # 计算恶意分数
            malicious_score, details = MaliciousUserDetectionService._calculate_malicious_score(user_hash, user_danmu_list)
            
            # 如果超过阈值，加入恶意用户列表
            if malicious_score >= threshold:
                malicious_users.append({
                    'user_hash': user_hash,
                    'score': malicious_score,
                    'details': details,
                    'danmu_count': len(user_danmu_list),
                    'videos': list(set([d.video_title for d in user_danmu_list])),
                    'latest_activity': max([d.created_time for d in user_danmu_list])
                })
        
        # 按恶意分数排序
        malicious_users.sort(key=lambda x: x['score'], reverse=True)
        
        return malicious_users
    
    @staticmethod
    def _calculate_malicious_score(user_hash, danmu_list):
        """
        计算用户的恶意分数
        
        参数:
            user_hash: 用户hash
            danmu_list: 用户的弹幕列表
            
        返回:
            恶意分数(0-1之间的浮点数)和详细信息
        """
        details = {
            'sensitive_word_count': 0,
            'spam_count': 0,
            'duplicate_count': 0,
            'burst_count': 0,
            'cross_video_spam': 0,
            'negative_emotion_count': 0,  # 负面情绪计数
            'unsupport_count': 0,         # 不支持行为计数
            'sentiment_score': 0,         # 情感分析分数
            'sensitive_words': [],
            'spam_messages': [],
            'negative_emotions': [],      # 负面情绪词汇
            'unsupport_messages': []      # 不支持行为消息
        }
        
        # 检测敏感词
        for danmu in danmu_list:
            # 检查敏感词
            for word in MaliciousUserDetectionService.SENSITIVE_WORDS:
                if word in danmu.content:
                    details['sensitive_word_count'] += 1
                    if word not in details['sensitive_words']:
                        details['sensitive_words'].append(word)
        
        # 检测垃圾信息
        for danmu in danmu_list:
            # 检查垃圾信息模式
            for pattern in MaliciousUserDetectionService.SPAM_PATTERNS:
                if re.search(pattern, danmu.content):
                    details['spam_count'] += 1
                    if danmu.content not in details['spam_messages'] and len(details['spam_messages']) < 5:
                        details['spam_messages'].append(danmu.content)
                    break
        
        # 检测重复内容
        content_counter = Counter([d.content for d in danmu_list])
        for content, count in content_counter.items():
            if count > 1:
                details['duplicate_count'] += count - 1
        
        # 检测爆发式发送
        # 按时间排序
        sorted_danmus = sorted(danmu_list, key=lambda x: x.created_time if x.created_time else datetime.min)
        
        # 检查短时间内发送多条弹幕
        for i in range(len(sorted_danmus) - 1):
            if sorted_danmus[i].created_time and sorted_danmus[i+1].created_time:
                time_diff = (sorted_danmus[i+1].created_time - sorted_danmus[i].created_time).total_seconds()
                if time_diff < 2:  # 2秒内连续发送
                    details['burst_count'] += 1
        
        # 检测跨视频发送相同内容
        video_contents = {}
        for danmu in danmu_list:
            if danmu.video_id not in video_contents:
                video_contents[danmu.video_id] = []
            video_contents[danmu.video_id].append(danmu.content)
        
        # 检查不同视频中的相同内容
        if len(video_contents) > 1:
            all_contents = []
            for video_id, contents in video_contents.items():
                all_contents.extend(contents)
            
            content_counter = Counter(all_contents)
            for content, count in content_counter.items():
                video_count = sum(1 for video_id, contents in video_contents.items() if content in contents)
                if video_count > 1:
                    details['cross_video_spam'] += video_count - 1
        
        # 检测负面情绪 (增强这部分的检测)
        for danmu in danmu_list:
            # 检查负面情绪词汇
            for word in MaliciousUserDetectionService.NEGATIVE_EMOTION_WORDS:
                if word in danmu.content:
                    # 增加负面情绪的权重
                    details['negative_emotion_count'] += 1.5
                    if word not in details['negative_emotions']:
                        details['negative_emotions'].append(word)
                    break
            
            # 使用SnowNLP进行情感分析
            try:
                s = SnowNLP(danmu.content)
                # SnowNLP情感分数范围为0-1，0为消极，1为积极
                sentiment = s.sentiments
                # 如果情感分数低于0.3，认为是负面情绪，并增加权重
                if sentiment < 0.3:
                    details['sentiment_score'] += (0.3 - sentiment) * 2
                # 如果情感分数非常低（极度负面），额外增加权重
                if sentiment < 0.1:
                    details['sentiment_score'] += 1
            except:
                # 忽略情感分析错误
                pass
        
        # 检测不支持行为 (增强这部分的检测)
        for danmu in danmu_list:
            # 检查不支持行为模式
            for pattern in MaliciousUserDetectionService.UNSUPPORT_PATTERNS:
                if re.search(pattern, danmu.content):
                    # 增加不支持行为的权重
                    details['unsupport_count'] += 1.5
                    if danmu.content not in details['unsupport_messages'] and len(details['unsupport_messages']) < 5:
                        details['unsupport_messages'].append(danmu.content)
                    break
        
        # 计算总分 - 突出负面情绪和不支持行为
        # 敏感词权重
        sensitive_weight = 0.10
        sensitive_score = min(1.0, details['sensitive_word_count'] / max(5, len(danmu_list)))
        
        # 垃圾信息权重 
        spam_weight = 0.10
        spam_score = min(1.0, details['spam_count'] / max(3, len(danmu_list)))
        
        # 重复内容权重 
        duplicate_weight = 0.05
        duplicate_score = min(1.0, details['duplicate_count'] / max(5, len(danmu_list)))
        
        # 爆发式发送权重
        burst_weight = 0.05
        burst_score = min(1.0, details['burst_count'] / max(5, len(danmu_list) - 1))
        
        # 跨视频垃圾信息权重
        cross_spam_weight = 0.05
        cross_spam_score = min(1.0, details['cross_video_spam'] / max(3, len(video_contents)))
        
        # 负面情绪权重 
        negative_emotion_weight = 0.35
        negative_emotion_score = min(1.0, (details['negative_emotion_count'] + details['sentiment_score']) / max(5, len(danmu_list)))
        
        # 不支持行为权重 
        unsupport_weight = 0.30
        unsupport_score = min(1.0, details['unsupport_count'] / max(3, len(danmu_list)))
        
        # 计算加权总分
        total_score = (sensitive_weight * sensitive_score + 
                      spam_weight * spam_score + 
                      duplicate_weight * duplicate_score + 
                      burst_weight * burst_score + 
                      cross_spam_weight * cross_spam_score +
                      negative_emotion_weight * negative_emotion_score +
                      unsupport_weight * unsupport_score)
        
        # 添加分数明细
        details['scores'] = {
            'sensitive_score': round(sensitive_score * sensitive_weight, 2),
            'spam_score': round(spam_score * spam_weight, 2),
            'duplicate_score': round(duplicate_score * duplicate_weight, 2),
            'burst_score': round(burst_score * burst_weight, 2),
            'cross_spam_score': round(cross_spam_score * cross_spam_weight, 2),
            'negative_emotion_score': round(negative_emotion_score * negative_emotion_weight, 2),
            'unsupport_score': round(unsupport_score * unsupport_weight, 2),
            'total_score': round(total_score, 2)
        }
        
        return total_score, details
    
    @staticmethod
    def get_user_activity(user_hash):
        """获取用户活动记录"""
        danmus = Danmu.query.filter_by(user_hash=user_hash).order_by(Danmu.created_time).all()
        
        activity = {
            'user_hash': user_hash,
            'danmu_count': len(danmus),
            'videos': [],
            'timeline': [],
            'sentiment_analysis': {  # 新增：情感分析统计
                'positive': 0,
                'neutral': 0,
                'negative': 0
            },
            'behavior_analysis': {   # 新增：行为分析统计
                'support': 0,        # 支持行为（点赞、投币等）
                'unsupport': 0,      # 不支持行为
                'spam': 0,           # 垃圾信息
                'normal': 0          # 普通评论
            }
        }
        
        # 获取用户发送弹幕的视频
        video_ids = set()
        for danmu in danmus:
            if danmu.video_id not in video_ids:
                video_ids.add(danmu.video_id)
                activity['videos'].append({
                    'video_id': danmu.video_id,
                    'video_title': danmu.video_title,
                    'video_bvid': danmu.video_bvid
                })
        
        # 获取用户活动时间线并进行情感和行为分析
        for danmu in danmus:
            # 情感分析
            try:
                s = SnowNLP(danmu.content)
                sentiment = s.sentiments
                if sentiment > 0.6:
                    sentiment_type = 'positive'
                    activity['sentiment_analysis']['positive'] += 1
                elif sentiment < 0.4:
                    sentiment_type = 'negative'
                    activity['sentiment_analysis']['negative'] += 1
                else:
                    sentiment_type = 'neutral'
                    activity['sentiment_analysis']['neutral'] += 1
            except:
                sentiment_type = 'neutral'
                activity['sentiment_analysis']['neutral'] += 1
                sentiment = 0.5
            
            # 行为分析
            behavior_type = 'normal'
            
            # 检查是否是支持行为
            if re.search(r'(点赞|投币|收藏|三连|关注)', danmu.content) and not re.search(r'不(会|想|愿意)?(点赞|投币|收藏|三连|关注)', danmu.content):
                behavior_type = 'support'
                activity['behavior_analysis']['support'] += 1
            
            # 检查是否是不支持行为
            elif any(re.search(pattern, danmu.content) for pattern in MaliciousUserDetectionService.UNSUPPORT_PATTERNS):
                behavior_type = 'unsupport'
                activity['behavior_analysis']['unsupport'] += 1
            
            # 检查是否是垃圾信息
            elif any(re.search(pattern, danmu.content) for pattern in MaliciousUserDetectionService.SPAM_PATTERNS):
                behavior_type = 'spam'
                activity['behavior_analysis']['spam'] += 1
            
            else:
                activity['behavior_analysis']['normal'] += 1
            
            # 添加到时间线
            activity['timeline'].append({
                'content': danmu.content,
                'video_title': danmu.video_title,
                'video_bvid': danmu.video_bvid,
                'appear_time': danmu.appear_time,
                'created_time': danmu.created_time.strftime('%Y-%m-%d %H:%M:%S') if danmu.created_time else None,
                'sentiment': {
                    'type': sentiment_type,
                    'score': round(sentiment, 2)
                },
                'behavior': behavior_type
            })
        
        return activity
    
    @staticmethod
    def analyze_user_behavior_patterns(user_hash):
        """分析用户行为模式"""
        activity = MaliciousUserDetectionService.get_user_activity(user_hash)
        
        # 计算行为模式
        behavior_patterns = {
            'sentiment_trend': [],  # 情感趋势
            'behavior_trend': [],   # 行为趋势
            'video_preference': [], # 视频偏好
            'active_hours': [],     # 活跃时间
            'interaction_patterns': {  # 互动模式
                'early_comments': 0,    # 视频前半段评论数
                'late_comments': 0,     # 视频后半段评论数
                'reply_rate': 0,        # 回复率（估计）
                'emoji_usage': 0        # 表情使用率
            }
        }
        
        # 分析情感趋势
        if len(activity['timeline']) >= 5:
            # 按时间排序
            sorted_timeline = sorted(activity['timeline'], key=lambda x: x['created_time'] if x['created_time'] else '')
            
            # 计算移动平均情感分数
            window_size = min(5, len(sorted_timeline))
            for i in range(len(sorted_timeline) - window_size + 1):
                window = sorted_timeline[i:i+window_size]
                avg_sentiment = sum(item['sentiment']['score'] for item in window) / window_size
                behavior_patterns['sentiment_trend'].append({
                    'time': window[-1]['created_time'],
                    'score': round(avg_sentiment, 2)
                })
        
        # 分析视频偏好
        video_counts = Counter([item['video_bvid'] for item in activity['timeline']])
        for video in activity['videos']:
            count = video_counts[video['video_bvid']]
            behavior_patterns['video_preference'].append({
                'video_title': video['video_title'],
                'video_bvid': video['video_bvid'],
                'comment_count': count,
                'percentage': round(count / len(activity['timeline']) * 100, 1)
            })
        
        # 分析活跃时间
        hour_counts = Counter()
        for item in activity['timeline']:
            if item['created_time']:
                try:
                    hour = datetime.strptime(item['created_time'], '%Y-%m-%d %H:%M:%S').hour
                    hour_counts[hour] += 1
                except:
                    pass
        
        for hour in range(24):
            behavior_patterns['active_hours'].append({
                'hour': hour,
                'count': hour_counts[hour]
            })
        
        # 分析互动模式
        for item in activity['timeline']:
            # 判断是前半段还是后半段评论
            if item['appear_time'] is not None:
                if item['appear_time'] < 300:  # 假设视频平均时长10分钟，前5分钟为前半段
                    behavior_patterns['interaction_patterns']['early_comments'] += 1
                else:
                    behavior_patterns['interaction_patterns']['late_comments'] += 1
            
            # 检查是否包含表情符号
            if re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', item['content']):
                behavior_patterns['interaction_patterns']['emoji_usage'] += 1
            
            # 检查是否是回复其他用户
            if re.search(r'回复|@|回答|回应', item['content']):
                behavior_patterns['interaction_patterns']['reply_rate'] += 1
        
        # 计算百分比
        total_comments = len(activity['timeline'])
        if total_comments > 0:
            behavior_patterns['interaction_patterns']['early_comments_percent'] = round(behavior_patterns['interaction_patterns']['early_comments'] / total_comments * 100, 1)
            behavior_patterns['interaction_patterns']['late_comments_percent'] = round(behavior_patterns['interaction_patterns']['late_comments'] / total_comments * 100, 1)
            behavior_patterns['interaction_patterns']['emoji_usage_percent'] = round(behavior_patterns['interaction_patterns']['emoji_usage'] / total_comments * 100, 1)
            behavior_patterns['interaction_patterns']['reply_rate_percent'] = round(behavior_patterns['interaction_patterns']['reply_rate'] / total_comments * 100, 1)
        
        return behavior_patterns 