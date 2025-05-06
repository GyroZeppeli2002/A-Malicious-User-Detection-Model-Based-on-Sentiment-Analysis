from app.models.danmu import Danmu
from sqlalchemy import func
from collections import Counter
import jieba
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.models.video import Video
from flask import current_app
import os

class DanmuAnalysisService:
    """弹幕分析服务"""
    
    @staticmethod
    def get_video_danmu_stats(bvid):
        """获取视频弹幕统计数据"""
        try:
            # 获取视频信息
            video = Video.query.filter_by(bvid=bvid).first()
            if not video:
                return {'error': '视频不存在'}
            
            # 获取该视频的所有弹幕
            danmus = Danmu.query.filter_by(video_id=video.id).all()
            if not danmus:
                return {'error': '没有弹幕数据'}
            
            # 按时间分布统计
            time_stats = {}
            for danmu in danmus:
                # 弹幕出现时间（秒）
                time_point = int(danmu.time_point)
                if time_point not in time_stats:
                    time_stats[time_point] = 0
                time_stats[time_point] += 1
            
            # 转换为列表格式
            time_distribution = [{'time': t, 'count': c} for t, c in time_stats.items()]
            time_distribution.sort(key=lambda x: x['time'])
            
            # 弹幕长度分布
            length_stats = {}
            for danmu in danmus:
                length = len(danmu.content)
                length_range = f"{(length-1)//5*5+1}-{(length-1)//5*5+5}" if length <= 30 else "30+"
                if length_range not in length_stats:
                    length_stats[length_range] = 0
                length_stats[length_range] += 1
            
            # 转换为列表格式
            length_distribution = [{'range': r, 'count': c} for r, c in length_stats.items()]
            length_distribution.sort(key=lambda x: int(x['range'].split('-')[0]) if '-' in x['range'] else 31)
            
            # 弹幕发送时间分布
            hour_stats = {}
            for danmu in danmus:
                hour = danmu.created_time.hour
                if hour not in hour_stats:
                    hour_stats[hour] = 0
                hour_stats[hour] += 1
            
            # 转换为列表格式
            hour_distribution = [{'hour': h, 'count': c} for h, c in hour_stats.items()]
            hour_distribution.sort(key=lambda x: x['hour'])
            
            # 弹幕关键词
            keywords = DanmuAnalysisService.get_danmu_keywords(bvid, top_n=20)
            keywords_list = [{'word': word, 'count': count} for word, count in keywords]
            
            return {
                'total': len(danmus),
                'time_distribution': time_distribution,
                'length_distribution': length_distribution,
                'hour_distribution': hour_distribution,
                'keywords': keywords_list
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_danmu_keywords(bvid, top_n=20):
        """获取弹幕关键词"""
        try:
            # 获取视频信息
            video = Video.query.filter_by(bvid=bvid).first()
            if not video:
                return []
            
            # 获取该视频的所有弹幕
            danmus = Danmu.query.filter_by(video_id=video.id).all()
            if not danmus:
                return []
            
            # 合并所有弹幕内容
            all_content = ' '.join([d.content for d in danmus])
            
            # 使用结巴分词
            words = jieba.cut(all_content)
            
            # 过滤停用词
            stop_words = set(['的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'])
            filtered_words = [word for word in words if len(word) > 1 and word not in stop_words]
            
            # 统计词频
            word_counts = Counter(filtered_words)
            
            # 返回前N个高频词
            return word_counts.most_common(top_n)
        except Exception as e:
            print(f"获取弹幕关键词出错: {str(e)}")
            return []
    
    @staticmethod
    def get_danmu_sentiment(bvid):
        """获取弹幕情感分析"""
        try:
            # 获取视频信息
            video = Video.query.filter_by(bvid=bvid).first()
            if not video:
                return {'error': '视频不存在'}
            
            # 获取该视频的所有弹幕
            danmus = Danmu.query.filter_by(video_id=video.id).all()
            if not danmus:
                return {'error': '没有弹幕数据'}
            
            # 简单情感分析（基于关键词）
            positive_words = set(['好', '棒', '赞', '喜欢', '爱', '漂亮', '帅', '美', '厉害', '强', '支持', '感动', '哈哈', '笑', '开心', '可爱'])
            negative_words = set(['差', '烂', '丑', '讨厌', '恨', '垃圾', '弱', '难看', '失望', '可惜', '遗憾', '哭', '悲伤', '难过'])
            
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            
            for danmu in danmus:
                content = danmu.content
                has_positive = any(word in content for word in positive_words)
                has_negative = any(word in content for word in negative_words)
                
                if has_positive and not has_negative:
                    positive_count += 1
                elif has_negative and not has_positive:
                    negative_count += 1
                else:
                    neutral_count += 1
            
            total = len(danmus)
            
            return {
                'positive': {
                    'count': positive_count,
                    'percent': round(positive_count / total * 100, 1) if total > 0 else 0
                },
                'negative': {
                    'count': negative_count,
                    'percent': round(negative_count / total * 100, 1) if total > 0 else 0
                },
                'neutral': {
                    'count': neutral_count,
                    'percent': round(neutral_count / total * 100, 1) if total > 0 else 0
                }
            }
        except Exception as e:
            return {'error': str(e)} 