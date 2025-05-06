from flask import (
    Blueprint, 
    render_template, 
    jsonify, 
    request, 
    current_app, 
    flash,  # 添加 flash
    url_for
)
from flask_login import login_required, current_user
from app.models import Video, Danmu, Author
from app import db, socketio, create_app
from sqlalchemy import func, desc
import pandas as pd
import numpy as np
from pyecharts.charts import Bar, Line, Pie, WordCloud, HeatMap, Radar, Funnel
from pyecharts import options as opts
from pyecharts.globals import ThemeType
from app.utils.crawler import BilibiliCrawler
from app.utils.data_processor import DataProcessor
from flask_socketio import emit
import threading
import sys
import jieba
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy import text
from app.services.danmu_analysis import DanmuAnalysisService
import os
import json
import random
from snownlp import SnowNLP

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """首页"""
    try:
        # 获取最近的视频
        recent_videos = Video.query.order_by(Video.created_time.desc()).limit(10).all()
        # 添加当前时间变量和datetime模块
        now = datetime.now()
        return render_template('index.html', 
                             recent_videos=recent_videos, 
                             now=now,
                             datetime=datetime)  # 传入datetime模块
    except Exception as e:
        current_app.logger.error(f"Error in index route: {str(e)}")
        return render_template('index.html', 
                             recent_videos=[], 
                             now=datetime.now(),
                             datetime=datetime,  # 传入datetime模块
                             error=str(e))

@main_bp.route('/crawl', methods=['GET', 'POST'])
def crawl():
    """爬取页面"""
    if request.method == 'POST':
        # 处理爬取请求
        data = request.get_json()
        # 创建爬虫实例
        crawler = BilibiliCrawler(app=current_app._get_current_object())
        
        if data.get('type') == 'popular':
            # 爬取热门视频
            limit = int(data.get('limit', 20))
            
            # 发送任务开始事件
            socketio.emit('crawl_task_start', {
                'type': 'popular',
                'limit': limit,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            # 在后台线程中爬取
            def run_crawler():
                with current_app.app_context():
                    videos = crawler.crawl_videos(limit=limit)
                    # 任务完成事件会由crawler中的emit_progress发送
            
            thread = threading.Thread(target=run_crawler)
            thread.daemon = True
            thread.start()
            
            return jsonify({'success': True, 'message': '爬取任务已启动'})
        
        elif data.get('type') == 'danmu':
            # 爬取单个视频弹幕
            bvid_or_url = data.get('bvid_or_url', '')
            save_to_csv = data.get('save_to_csv', True)
            save_to_db = data.get('save_to_db', True)
            
            if not bvid_or_url:
                return jsonify({'success': False, 'message': '请提供视频BV号或URL'})
                
            danmu_list = crawler.crawl_video_danmu(bvid_or_url, save_to_csv, save_to_db)
            return jsonify({'success': True, 'count': len(danmu_list)})
            
        elif data.get('type') == 'batch_danmu':
            # 批量爬取多个视频弹幕
            video_list = data.get('video_list', [])
            save_to_csv = data.get('save_to_csv', True)
            save_to_db = data.get('save_to_db', True)
            
            if not video_list:
                return jsonify({'success': False, 'message': '请提供视频列表'})
                
            results = crawler.crawl_multiple_video_danmu(video_list, save_to_csv, save_to_db)
            return jsonify({'success': True, 'count': len(results)})
            
        return jsonify({'success': False, 'message': '未知的爬取类型'})
        
    # GET请求返回页面
    return render_template('crawl.html')

@main_bp.route('/analysis')
def analysis():
    """数据分析页面"""
    # 获取所有视频
    videos = Video.query.order_by(Video.crawled_at.desc()).all()
    
    # 计算基本统计数据
    stats = {}
    if videos:
        play_counts = [v.play_count for v in videos]
        danmaku_counts = [v.danmaku_count for v in videos]
        like_counts = [v.like_count for v in videos]
        
        stats = {
            'play_count': {
                'mean': np.mean(play_counts) if play_counts else 0,
                'max': max(play_counts) if play_counts else 0,
                'min': min(play_counts) if play_counts else 0
            },
            'danmaku_count': {
                'mean': np.mean(danmaku_counts) if danmaku_counts else 0,
                'max': max(danmaku_counts) if danmaku_counts else 0,
                'min': min(danmaku_counts) if danmaku_counts else 0
            },
            'like_count': {
                'mean': np.mean(like_counts) if like_counts else 0,
                'max': max(like_counts) if like_counts else 0,
                'min': min(like_counts) if like_counts else 0
            }
        }
    
    return render_template('analysis.html', videos=videos, stats=stats)

@main_bp.route('/api/danmu/stats/<bvid>')
def danmu_stats(bvid):
    """获取视频弹幕统计数据"""
    try:
        # 获取视频信息
        video = Video.query.filter_by(bvid=bvid).first_or_404()
        
        # 弹幕时间分布 - 修复 group_by 语法
        time_segment_expr = db.func.floor(Danmu.appear_time / 10).label('time_segment')
        time_distribution = db.session.query(
            time_segment_expr,
            db.func.count(Danmu.id).label('count')
        ).filter_by(video_id=video.id).group_by(time_segment_expr).order_by(time_segment_expr).all()
        
        time_dist_data = []
        for item in time_distribution:
            # 添加错误处理
            try:
                segment = int(item[0]) if item[0] is not None else 0
                count = item[1]
                time_dist_data.append({'time_segment': segment, 'count': count})
            except (ValueError, TypeError) as e:
                current_app.logger.error(f"时间段数据转换错误: {str(e)}")
        
        # 弹幕模式分布 - 修复 group_by 语法 
        mode_distribution = db.session.query(
            Danmu.mode,
            db.func.count(Danmu.id).label('count')
        ).filter_by(video_id=video.id).group_by(Danmu.mode).order_by(db.desc('count')).all()
        
        mode_dist_data = []
        for item in mode_distribution:
            try:
                mode = int(item[0]) if item[0] is not None else 0
                count = item[1]
                mode_dist_data.append({'mode': mode, 'count': count})
            except (ValueError, TypeError) as e:
                current_app.logger.error(f"模式数据转换错误: {str(e)}")
        
        # 确保返回有效数据，即使是空列表
        return jsonify({
            'time_distribution': time_dist_data,
            'mode_distribution': mode_dist_data
        })
    
    except Exception as e:
        current_app.logger.error(f"弹幕统计API错误: {str(e)}")
        # 返回错误信息和状态码
        return jsonify({
            'error': f"获取弹幕统计数据失败: {str(e)}",
            'time_distribution': [],
            'mode_distribution': []
        }), 500

@main_bp.route('/api/danmu/keywords/<bvid>')
def danmu_keywords(bvid):
    """弹幕关键词提取 - 增强版"""
    # 获取视频弹幕
    video = Video.query.filter_by(bvid=bvid).first_or_404()
    danmus = Danmu.query.filter_by(video_id=video.id).all()
    
    # 如果弹幕数量太少，直接返回
    if len(danmus) < 5:
        return jsonify([])
    
    # 合并所有弹幕内容
    all_content = ' '.join([d.content for d in danmus])
    
    # 扩展停用词列表
    stopwords = {
        '的', '了', '是', '我', '你', '他', '她', '它', '们', '这', '那', '啊', '吧', '呢', 
        '哈', '哦', '呀', '哇', '嗯', '啥', '呵', '哎', '唉', '诶', '额', '哼', '喔', '哟',
        '好', '不', '有', '在', '人', '就', '说', '又', '看', '吗', '呦', '喂', '一个',
        '什么', '还是', '就是', '这个', '那个', '也', '都', '回', '做'
    }
    
    # 使用结巴分词提取关键词
    import jieba.analyse
    
    # 基于TF-IDF提取关键词
    tfidf_keywords = jieba.analyse.extract_tags(
        all_content, 
        topK=15, 
        withWeight=True, 
        allowPOS=('ns', 'n', 'vn', 'v', 'a')  # 只保留名词、动词和形容词
    )
    
    # 基于TextRank提取关键词
    textrank_keywords = jieba.analyse.textrank(
        all_content, 
        topK=15, 
        withWeight=True, 
        allowPOS=('ns', 'n', 'vn', 'v', 'a')
    )
    
    # 合并两种方法的结果
    combined_keywords = {}
    for word, weight in tfidf_keywords:
        if word not in stopwords and len(word) > 1:
            combined_keywords[word] = {'tfidf': weight, 'textrank': 0}
            
    for word, weight in textrank_keywords:
        if word not in stopwords and len(word) > 1:
            if word in combined_keywords:
                combined_keywords[word]['textrank'] = weight
            else:
                combined_keywords[word] = {'tfidf': 0, 'textrank': weight}
    
    # 计算各关键词在弹幕中的出现次数
    word_counts = {}
    for danmu in danmus:
        for word in combined_keywords.keys():
            if word in danmu.content:
                word_counts[word] = word_counts.get(word, 0) + 1
    
    # 整合结果
    result = []
    for word, metrics in combined_keywords.items():
        result.append({
            'word': word,
            'tfidf': round(metrics['tfidf'] * 100, 2),  # 转换为百分比
            'textrank': round(metrics['textrank'] * 100, 2),
            'count': word_counts.get(word, 0),
            'score': (metrics['tfidf'] + metrics['textrank']) * word_counts.get(word, 1)  # 综合评分
        })
    
    # 按综合评分排序
    result = sorted(result, key=lambda x: x['score'], reverse=True)[:30]
    
    return jsonify(result)

@main_bp.route('/api/danmu/sentiment/<bvid>')
def danmu_sentiment_analysis(bvid):
    """弹幕情感分析"""
    # 获取视频弹幕
    video = Video.query.filter_by(bvid=bvid).first_or_404()
    danmus = Danmu.query.filter_by(video_id=video.id).all()
    
    # 统计结果
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    
    # 情感值分布
    sentiment_distribution = {
        'very_negative': 0,  # 0.0-0.2
        'negative': 0,       # 0.2-0.4
        'neutral': 0,        # 0.4-0.6
        'positive': 0,       # 0.6-0.8
        'very_positive': 0   # 0.8-1.0
    }
    
    # 情感随时间变化
    time_sentiment = {}
    
    # 对每条弹幕进行情感分析
    for danmu in danmus:
        try:
            # 使用 SnowNLP 进行情感分析
            s = SnowNLP(danmu.content)
            sentiment = s.sentiments  # 返回 0-1 之间的值，越接近1越积极
            
            # 情感分类
            if sentiment > 0.6:
                positive_count += 1
            elif sentiment < 0.4:
                negative_count += 1
            else:
                neutral_count += 1
            
            # 更细致的情感分布
            if sentiment < 0.2:
                sentiment_distribution['very_negative'] += 1
            elif sentiment < 0.4:
                sentiment_distribution['negative'] += 1
            elif sentiment < 0.6:
                sentiment_distribution['neutral'] += 1
            elif sentiment < 0.8:
                sentiment_distribution['positive'] += 1
            else:
                sentiment_distribution['very_positive'] += 1
            
            # 情感随时间变化
            # 使用整数时间点作为键
            time_segment = int(danmu.appear_time) // 10 * 10
            if time_segment not in time_sentiment:
                time_sentiment[time_segment] = {'count': 0, 'total': 0}
            time_sentiment[time_segment]['count'] += 1
            time_sentiment[time_segment]['total'] += sentiment
            
        except Exception as e:
            # 如果分析失败，归为中性
            neutral_count += 1
            current_app.logger.error(f"情感分析错误: {str(e)}")
    
    # 计算每个时间段的平均情感值
    time_sentiment_avg = []
    for time_seg, data in sorted(time_sentiment.items()):
        if data['count'] > 0:
            avg_sentiment = data['total'] / data['count']
            time_sentiment_avg.append({
                'time': time_seg,
                'sentiment': round(avg_sentiment, 2),
                'count': data['count']
            })
    
    # 如果没有数据，添加默认值
    if positive_count == 0 and negative_count == 0 and neutral_count == 0:
        positive_count = 1
        negative_count = 1
        neutral_count = 1
    
    # 返回分析结果
    return jsonify({
        'positive_count': positive_count,
        'negative_count': negative_count,
        'neutral_count': neutral_count,
        'total': len(danmus),
        'sentiment_distribution': sentiment_distribution,
        'time_sentiment': time_sentiment_avg
    })

@main_bp.route('/api/videos')
def get_videos():
    """获取视频列表API"""
    videos = Video.query.order_by(Video.crawled_at.desc()).all()
    result = [{
        'bvid': v.bvid,
        'title': v.title,
        'author': v.author,
        'play_count': v.play_count,
        'danmaku_count': v.danmaku_count
    } for v in videos]
    return jsonify(result)

@main_bp.route('/api/danmu/<bvid>')
def get_danmu_list(bvid):
    """获取视频弹幕列表API"""
    limit = request.args.get('limit', 100, type=int)
    danmus = Danmu.query.filter_by(video_bvid=bvid).limit(limit).all()
    result = [{
        'content': d.content,
        'appear_time': d.appear_time,
        'color': d.color,
        'send_time': d.send_time.strftime('%Y-%m-%d %H:%M:%S') if d.send_time else None
    } for d in danmus]
    return jsonify(result)

@main_bp.route('/dashboard')
def dashboard():
    """数据看板页面"""
    try:
        # 获取基本统计数据
        video_count = Video.query.count()
        author_count = Author.query.count()
        danmu_count = Danmu.query.count()
        
        # 计算总播放量
        total_plays = db.session.query(db.func.sum(Video.play_count)).scalar() or 0
        
        # 获取其他可能需要的统计信息
        popular_videos = Video.query.order_by(Video.play_count.desc()).limit(5).all()
        recent_videos = Video.query.order_by(Video.created_time.desc()).limit(5).all()
        
        return render_template('dashboard.html',
                              video_count=video_count,
                              author_count=author_count, 
                              danmu_count=danmu_count,
                              total_plays=total_plays,
                              popular_videos=popular_videos,
                              recent_videos=recent_videos)
    except Exception as e:
        current_app.logger.error(f"Error in dashboard route: {str(e)}")
        # 提供默认值避免模板错误
        return render_template('dashboard.html',
                              video_count=0,
                              author_count=0,
                              danmu_count=0,
                              total_plays=0,
                              popular_videos=[],
                              recent_videos=[],
                              error=str(e))

@main_bp.route('/api/video_type_distribution')
def video_type_distribution():
    data = db.session.query(
        Video.video_type,
        db.func.count(Video.id).label('count')
    ).group_by(Video.video_type).all()
    
    # 如果没有数据，添加示例数据
    if not data:
        data = [
            ("游戏", 10),
            ("音乐", 8),
            ("科技", 5),
            ("生活", 4),
            ("动画", 7)
        ]
    
    c = (
        Pie()
        .add("", data)
        .set_global_opts(title_opts=opts.TitleOpts(title="视频类型分布"))
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"))
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/trend_analysis')
def trend_analysis():
    # 获取每日视频数据趋势
    data = db.session.query(
        db.func.date(Video.created_time),
        db.func.avg(Video.play_count),
        db.func.avg(Video.danmaku_count)
    ).group_by(db.func.date(Video.created_time)).all()
    
    # 如果没有数据，添加示例数据
    if not data:
        # 创建过去7天的示例数据
        today = datetime.now().date()
        data = [
            (today - timedelta(days=i), 
             random.randint(5000, 20000), 
             random.randint(100, 500))
            for i in range(7)
        ]
    
    c = (
        Line()
        .add_xaxis([str(d[0]) for d in data])
        .add_yaxis("平均播放量", [float(d[1]) for d in data], is_smooth=True)
        .add_yaxis("平均弹幕数", [float(d[2]) for d in data], is_smooth=True)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="视频数据趋势分析"),
            xaxis_opts=opts.AxisOpts(name="日期"),
            yaxis_opts=opts.AxisOpts(name="数量"),
            tooltip_opts=opts.TooltipOpts(trigger="axis")
        )
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/top_authors')
def top_authors():
    authors = Author.query.order_by(Author.follower_count.desc()).limit(10).all()
    
    # 如果没有数据，添加示例数据
    if not authors:
        authors_data = [
            {"name": f"UP主{i}", "follower_count": random.randint(10000, 1000000)}
            for i in range(1, 11)
        ]
        c = (
            Bar()
            .add_xaxis([a["name"] for a in authors_data])
            .add_yaxis("粉丝数", [a["follower_count"] for a in authors_data])
            .set_global_opts(
                title_opts=opts.TitleOpts(title="Top 10 UP主粉丝数"),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                tooltip_opts=opts.TooltipOpts(trigger="axis")
            )
        )
    else:
        c = (
            Bar()
            .add_xaxis([a.name for a in authors])
            .add_yaxis("粉丝数", [a.follower_count for a in authors])
            .set_global_opts(
                title_opts=opts.TitleOpts(title="Top 10 UP主粉丝数"),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                tooltip_opts=opts.TooltipOpts(trigger="axis")
            )
        )
    return c.dump_options_with_quotes()

@main_bp.route('/api/user_behavior_radar')
def user_behavior_radar():
    """用户行为雷达图"""
    # 获取平均用户行为数据
    data = db.session.query(
        db.func.avg(Video.play_count).label('play'),
        db.func.avg(Video.danmaku_count).label('danmaku'),
        db.func.avg(Video.like_count).label('like'),
        db.func.avg(Video.coin_count).label('coin'),
        db.func.avg(Video.favorite_count).label('favorite'),
        db.func.avg(Video.share_count).label('share'),
        db.func.avg(Video.comment_count).label('comment')
    ).first()
    
    if data is None or data.play is None:
        # 默认值
        radar_data = [{
            'value': [0, 0, 0, 0, 0, 0, 0],
            'name': '用户行为均值'
        }]
        
        c = (
            Radar()
            .add_schema(
                schema=[
                    opts.RadarIndicatorItem(name="播放量(万)", max=10),
                    opts.RadarIndicatorItem(name="弹幕量(千)", max=10),
                    opts.RadarIndicatorItem(name="点赞数(千)", max=10),
                    opts.RadarIndicatorItem(name="投币数(千)", max=10),
                    opts.RadarIndicatorItem(name="收藏数(千)", max=10),
                    opts.RadarIndicatorItem(name="分享数(千)", max=10),
                    opts.RadarIndicatorItem(name="评论数(千)", max=10)
                ]
            )
            .add("", radar_data)
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False))
            .set_global_opts(
                title_opts=opts.TitleOpts(title="用户行为分析"),
                legend_opts=opts.LegendOpts(is_show=False)
            )
        )
    else:
        # 雷达图维度和数据
        radar_data = [
            {
                'value': [
                    round(data.play / 10000, 2),
                    round(data.danmaku / 1000, 2),
                    round(data.like / 1000, 2),
                    round(data.coin / 1000, 2),
                    round(data.favorite / 1000, 2),
                    round(data.share / 1000, 2),
                    round(data.comment / 1000, 2)
                ],
                'name': '用户行为均值'
            }
        ]
        
        c = (
            Radar()
            .add_schema(
                schema=[
                    opts.RadarIndicatorItem(name="播放量(万)", max=max(round(data.play / 5000, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="弹幕量(千)", max=max(round(data.danmaku / 500, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="点赞数(千)", max=max(round(data.like / 500, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="投币数(千)", max=max(round(data.coin / 500, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="收藏数(千)", max=max(round(data.favorite / 500, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="分享数(千)", max=max(round(data.share / 500, 2) * 2, 1)),
                    opts.RadarIndicatorItem(name="评论数(千)", max=max(round(data.comment / 500, 2) * 2, 1))
                ]
            )
            .add("", radar_data)
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False))
            .set_global_opts(
                title_opts=opts.TitleOpts(title="用户行为分析"),
                legend_opts=opts.LegendOpts(is_show=False)
            )
        )
    
    return c.dump_options_with_quotes()

@main_bp.route('/api/user_behavior_funnel')
def user_behavior_funnel():
    """用户行为漏斗图"""
    # 获取用户行为总量
    data = db.session.query(
        db.func.sum(Video.play_count).label('play'),
        db.func.sum(Video.danmaku_count).label('danmaku'),
        db.func.sum(Video.like_count).label('like'),
        db.func.sum(Video.coin_count).label('coin'),
        db.func.sum(Video.favorite_count).label('favorite'),
        db.func.sum(Video.share_count).label('share'),
        db.func.sum(Video.comment_count).label('comment')
    ).first()
    
    if data is None or data.play is None:
        # 默认值
        funnel_data = [
            {"value": 100, "name": "播放"},
            {"value": 80, "name": "弹幕"},
            {"value": 60, "name": "点赞"},
            {"value": 40, "name": "投币"},
            {"value": 30, "name": "收藏"},
            {"value": 20, "name": "评论"},
            {"value": 10, "name": "分享"}
        ]
    else:
        funnel_data = [
            {"value": data.play or 0, "name": "播放"},
            {"value": data.danmaku or 0, "name": "弹幕"},
            {"value": data.like or 0, "name": "点赞"},
            {"value": data.coin or 0, "name": "投币"},
            {"value": data.favorite or 0, "name": "收藏"},
            {"value": data.comment or 0, "name": "评论"},
            {"value": data.share or 0, "name": "分享"}
        ]
    
    c = (
        Funnel()
        .add(
            "用户行为",
            funnel_data,
            sort_="descending",
            label_opts=opts.LabelOpts(position="inside"),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="用户行为转化漏斗"),
            tooltip_opts=opts.TooltipOpts(trigger="item", formatter="{a} <br/>{b} : {c}")
        )
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/video_title_wordcloud')
def video_title_wordcloud():
    """视频标题词云图"""
    # 获取所有视频标题
    videos = Video.query.all()
    titles = [v.title for v in videos]
    
    if not titles:
        # 如果没有数据，返回默认词云
        words_data = [
            {"name": "示例词云", "value": 100},
            {"name": "哔哩哔哩", "value": 80},
            {"name": "视频", "value": 70},
            {"name": "数据分析", "value": 60},
            {"name": "B站", "value": 50}
        ]
    else:
        # 使用jieba分词
        text = ' '.join(titles)
        words = jieba.cut(text)
        
        # 过滤停用词
        stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        filtered_words = [word for word in words if len(word) > 1 and word not in stopwords]
        
        # 统计词频
        word_counts = Counter(filtered_words)
        words_data = [{"name": word, "value": count} for word, count in word_counts.most_common(100)]
    
    c = (
        WordCloud()
        .add(series_name="热门词汇", data_pair=words_data, word_size_range=[12, 60])
        .set_global_opts(
            title_opts=opts.TitleOpts(title="视频标题热词"),
            tooltip_opts=opts.TooltipOpts(is_show=True)
        )
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/video_heatmap')
def video_heatmap():
    """视频热力图 - 按照播放量和类型分布"""
    # 获取视频类型和播放量
    videos = Video.query.all()
    
    if not videos:
        # 如果没有数据，返回默认热力图
        video_types = ["游戏", "音乐", "电影", "动画", "科技"]
        play_ranges = ["0-1万", "1-10万", "10-50万", "50-100万", "100-500万", "500万+"]
        heatmap_data = []
        for i in range(len(video_types)):
            for j in range(len(play_ranges)):
                heatmap_data.append([j, i, np.random.randint(1, 10)])
    else:
        # 按视频类型分组
        video_types = set(v.video_type for v in videos)
        video_types = sorted(list(video_types))
        
        # 按播放量范围分组
        play_ranges = ["0-1万", "1-10万", "10-50万", "50-100万", "100-500万", "500万+"]
        
        # 创建热力图数据
        heatmap_data = []
        for i, vtype in enumerate(video_types):
            for j, prange in enumerate(play_ranges):
                # 统计该类型和播放量范围的视频数量
                if prange == "0-1万":
                    count = sum(1 for v in videos if v.video_type == vtype and v.play_count < 10000)
                elif prange == "1-10万":
                    count = sum(1 for v in videos if v.video_type == vtype and 10000 <= v.play_count < 100000)
                elif prange == "10-50万":
                    count = sum(1 for v in videos if v.video_type == vtype and 100000 <= v.play_count < 500000)
                elif prange == "50-100万":
                    count = sum(1 for v in videos if v.video_type == vtype and 500000 <= v.play_count < 1000000)
                elif prange == "100-500万":
                    count = sum(1 for v in videos if v.video_type == vtype and 1000000 <= v.play_count < 5000000)
                else:  # "500万+"
                    count = sum(1 for v in videos if v.video_type == vtype and v.play_count >= 5000000)
                
                heatmap_data.append([j, i, count])
    
    c = (
        HeatMap()
        .add_xaxis(play_ranges)
        .add_yaxis("", video_types, heatmap_data)
        .set_global_opts(
            title_opts=opts.TitleOpts(title="视频类型与播放量分布热力图"),
            visualmap_opts=opts.VisualMapOpts(),
            tooltip_opts=opts.TooltipOpts(formatter="{a} <br/>{b} : {c}")
        )
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/crawl/danmu', methods=['POST'])
def crawl_danmu():
    """爬取指定视频的弹幕"""
    try:
        data = request.get_json()
        bvid = data.get('bvid')
        
        if not bvid:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: bvid'
            }), 400
        
        # 创建爬虫实例
        crawler = BilibiliCrawler(app=current_app._get_current_object())
        
        # 在后台线程中运行爬虫
        def run_crawler():
            with current_app.app_context():
                crawler.crawl_video_danmu(bvid, save_to_csv=True, save_to_db=True)
        
        thread = threading.Thread(target=run_crawler)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'已开始爬取视频 {bvid} 的弹幕'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

def log_to_console(message, end='\n'):
    """辅助函数：输出到控制台"""
    sys.stdout.write(message + end)
    sys.stdout.flush()

# 爬虫后台任务
def crawl_task():
    # 创建应用上下文
    app = create_app()
    with app.app_context():
        try:
            log_to_console("\n开始爬虫任务...")
            crawler = BilibiliCrawler()
            processor = DataProcessor()
            
            # 开始爬取数据
            data = crawler.crawl_videos()
            
            if data:
                # 输出数据处理开始
                log_to_console("\n开始处理数据...")
                
                # 处理数据
                processed_data = processor.process_data(data)
                
                # 输出数据保存开始
                log_to_console(f"开始保存数据到数据库... (共 {len(processed_data)} 条)")
                
                # 记录已存在的BV号，避免重复
                existing_bvids = [v.bvid for v in Video.query.all()]
                
                # 保存到数据库
                new_count = 0
                for item in processed_data:
                    # 检查视频是否已存在
                    if item['bvid'] not in existing_bvids:
                        video = Video(**item)
                        db.session.add(video)
                        new_count += 1
                        
                db.session.commit()
                
                # 输出保存完成
                log_to_console(f"数据保存完成！新增 {new_count} 条记录。")
                
                socketio.emit('task_complete', {'status': 'success', 'message': f'数据爬取成功，新增 {new_count} 条记录'})
            else:
                log_to_console("未获取到有效数据")
                socketio.emit('task_error', {'status': 'error', 'message': '未获取到有效数据'})
                
        except Exception as e:
            error_msg = f'任务执行错误: {str(e)}'
            log_to_console(f"\n[错误] {error_msg}")
            socketio.emit('task_error', {'status': 'error', 'message': str(e)})

@main_bp.route('/crawl', methods=['POST'])
def start_crawl():
    """启动爬虫任务"""
    try:
        # 创建爬虫实例
        crawler = BilibiliCrawler(app=current_app._get_current_object())
        
        # 在后台线程中运行爬虫
        def run_crawler():
            with current_app.app_context():
                crawler.crawl_videos(limit=10)
        
        thread = threading.Thread(target=run_crawler)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': '爬虫任务已启动'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

# Socket.IO事件
@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': '已连接到服务器'})

@socketio.on('disconnect')
def handle_disconnect():
    pass

@main_bp.route('/video/<bvid>')
def video_detail(bvid):
    """视频详情页面"""
    video = Video.query.filter_by(bvid=bvid).first_or_404()
    
    # 获取该视频的弹幕数据
    danmu_count = Danmu.query.filter_by(video_id=video.id).count()
    
    # 获取弹幕统计数据
    danmu_stats = DanmuAnalysisService.get_video_danmu_stats(bvid)
    
    return render_template('video_detail.html', 
                          video=video, 
                          danmu_count=danmu_count,
                          danmu_stats=danmu_stats)

@main_bp.route('/danmu/list')
def danmu_list_view():
    """显示所有视频的弹幕列表页面"""
    videos_with_danmu = db.session.query(Video, db.func.count(Danmu.id).label('danmu_count'))\
        .join(Danmu, Video.id == Danmu.video_id)\
        .group_by(Video.id)\
        .order_by(db.desc('danmu_count'))\
        .all()
    
    return render_template('danmu_list.html', videos=videos_with_danmu)

@main_bp.route('/danmu/<bvid>')
def danmu_detail(bvid):
    """显示特定视频的弹幕详情"""
    # 获取视频信息
    video = Video.query.filter_by(bvid=bvid).first_or_404()
    
    # 获取弹幕数据
    danmu_list = Danmu.query.filter_by(video_id=video.id).order_by(Danmu.appear_time).all()
    
    # 获取弹幕统计信息
    danmu_count = len(danmu_list)
    
    # 弹幕时间分布
    time_distribution = db.session.query(
        db.func.floor(Danmu.appear_time / 10).label('time_segment'),
        db.func.count(Danmu.id).label('count')
    ).filter_by(video_id=video.id).group_by('time_segment').order_by('time_segment').all()
    
    # 弹幕模式分布
    mode_distribution = db.session.query(
        Danmu.mode,
        db.func.count(Danmu.id).label('count')
    ).filter_by(video_id=video.id).group_by(Danmu.mode).order_by(db.desc('count')).all()
    
    return render_template(
        'danmu_detail.html', 
        video=video, 
        danmu_list=danmu_list,
        danmu_count=danmu_count,
        time_distribution=time_distribution,
        mode_distribution=mode_distribution
    )

# 查找并删除或注释掉弹幕颜色分布的API端点
@main_bp.route('/api/danmu_color_distribution')
def danmu_color_distribution():
    # 颜色映射
    color_map = {
        0xFFFFFF: "白色",
        0x000000: "黑色",
        0xFF0000: "红色",
        0x00FFFF: "青色",
        0xFF7204: "橙色", 
        0xFFFF00: "黄色",
        0x00FF00: "绿色",
        0xFF00FF: "紫色",
        # 其他颜色...
    }
    
    # 获取弹幕颜色统计
    # 可能这段代码需要移除或注释
    data = db.session.query(
        Danmu.color, 
        db.func.count(Danmu.id)
    ).group_by(Danmu.color).all()
    
    formatted_data = []
    for color_code, count in data:
        color_name = color_map.get(color_code, f"未知颜色({color_code})")
        formatted_data.append((color_name, count))
    
    # 生成饼图
    c = (
        Pie()
        .add("", formatted_data)
        .set_global_opts(title_opts=opts.TitleOpts(title="弹幕颜色分布"))
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"))
    )
    return c.dump_options_with_quotes()

@main_bp.route('/api/danmu/behavior/<bvid>')
def danmu_behavior_analysis(bvid):
    """分析弹幕用户行为模式"""
    video = Video.query.filter_by(bvid=bvid).first_or_404()
    danmus = Danmu.query.filter_by(video_id=video.id).all()
    
    # 用户参与度分析
    user_hash_count = {}
    for danmu in danmus:
        user_hash = danmu.user_hash
        if user_hash not in user_hash_count:
            user_hash_count[user_hash] = 0
        user_hash_count[user_hash] += 1
    
    # 计算用户活跃度统计
    user_activity = {
        'single_comment': 0,      # 只发一条弹幕的用户
        'active': 0,              # 发2-5条弹幕的用户
        'very_active': 0,         # 发6-10条弹幕的用户
        'super_active': 0         # 发10+条弹幕的用户
    }
    
    for count in user_hash_count.values():
        if count == 1:
            user_activity['single_comment'] += 1
        elif count <= 5:
            user_activity['active'] += 1
        elif count <= 10:
            user_activity['very_active'] += 1
        else:
            user_activity['super_active'] += 1
    
    # 弹幕长度分析
    length_distribution = {
        'very_short': 0,  # 1-5个字
        'short': 0,       # 6-10个字
        'medium': 0,      # 11-20个字
        'long': 0         # 20+个字
    }
    
    for danmu in danmus:
        content_length = len(danmu.content)
        if content_length <= 5:
            length_distribution['very_short'] += 1
        elif content_length <= 10:
            length_distribution['short'] += 1
        elif content_length <= 20:
            length_distribution['medium'] += 1
        else:
            length_distribution['long'] += 1
    
    # 互动高峰时间 - 使用 created_time 而不是 time_point
    peak_times = {}
    for danmu in danmus:
        # 使用created_time而不是appear_time计算小时
        hour = danmu.created_time.hour if danmu.created_time else 0
        if hour not in peak_times:
            peak_times[hour] = 0
        peak_times[hour] += 1
    
    # 格式化peak_times为列表
    peak_times_list = [{'hour': hour, 'count': count} for hour, count in peak_times.items()]
    peak_times_list = sorted(peak_times_list, key=lambda x: x['hour'])
    
    return jsonify({
        'total_users': len(user_hash_count),
        'user_activity': user_activity,
        'length_distribution': length_distribution,
        'peak_times': peak_times_list
    })

@main_bp.route('/video_analysis')
@login_required
def video_analysis():
    """视频数据分析页面"""
    try:
        # 获取基础统计数据
        stats = db.session.query(
            db.func.count(Video.id).label('total_videos'),
            db.func.sum(Video.play_count).label('total_plays'),
            db.func.sum(Video.danmaku_count).label('total_danmus'),
            db.func.sum(Video.like_count).label('total_likes'),
            db.func.sum(Video.coin_count).label('total_coins'),
            db.func.sum(Video.favorite_count).label('total_favorites'),
            db.func.avg(Video.play_count).label('avg_plays'),
            db.func.avg(Video.danmaku_count).label('avg_danmus'),
            db.func.avg(Video.like_count).label('avg_likes'),
            db.func.avg(Video.coin_count).label('avg_coins'),
            db.func.avg(Video.favorite_count).label('avg_favorites')
        ).first()
        
        # 将查询结果转换为字典
        stats_dict = {
            'total_videos': int(stats[0] or 0),
            'total_plays': int(stats[1] or 0),
            'total_danmus': int(stats[2] or 0),
            'total_likes': int(stats[3] or 0),
            'total_coins': int(stats[4] or 0),
            'total_favorites': int(stats[5] or 0),
            'avg_plays': round(float(stats[6] or 0), 2),
            'avg_danmus': round(float(stats[7] or 0), 2),
            'avg_likes': round(float(stats[8] or 0), 2),
            'avg_coins': round(float(stats[9] or 0), 2),
            'avg_favorites': round(float(stats[10] or 0), 2)
        }
        
        # 获取播放量排名前10的视频
        top_played = Video.query.order_by(Video.play_count.desc()).limit(10).all()
        
        # 获取互动比例最高的视频(互动=点赞+投币+收藏)
        top_interaction = db.session.query(Video).order_by(
            (Video.like_count + Video.coin_count + Video.favorite_count).desc()
        ).limit(10).all()
        
        return render_template('video_analysis.html', 
                             stats=stats_dict,
                             top_played=top_played,
                             top_interaction=top_interaction)
                             
    except Exception as e:
        current_app.logger.error(f"Error in video_analysis: {str(e)}")
        # 使用current_app.flash代替flash
        current_app.logger.error('获取数据时发生错误')
        return render_template('video_analysis.html', 
                             stats={
                                 'total_videos': 0,
                                 'total_plays': 0,
                                 'total_danmus': 0,
                                 'total_likes': 0,
                                 'total_coins': 0,
                                 'total_favorites': 0,
                                 'avg_plays': 0,
                                 'avg_danmus': 0,
                                 'avg_likes': 0,
                                 'avg_coins': 0,
                                 'avg_favorites': 0
                             },
                             top_played=[],
                             top_interaction=[])

@main_bp.route('/api/video/stats')
@login_required
def video_stats_api():
    """获取视频统计数据API"""
    try:
        # 获取播放量前10的视频的完整数据
        top_videos = Video.query.order_by(Video.play_count.desc()).limit(10).all()
        
        # 获取所有视频数据用于关系分析
        all_videos = Video.query.all()
        
        # 准备排行榜数据
        ranking_data = {
            'titles': [video.title[:15] + '...' if len(video.title) > 15 else video.title for video in top_videos],
            'play_count': [int(video.play_count or 0) for video in top_videos],
            'danmaku_count': [int(video.danmaku_count or 0) for video in top_videos],
            'like_count': [int(video.like_count or 0) for video in top_videos],
            'coin_count': [int(video.coin_count or 0) for video in top_videos],
            'favorite_count': [int(video.favorite_count or 0) for video in top_videos]
        }
        
        # 准备关系数据
        correlation_data = {
            'play_like': [[v.play_count, v.like_count] for v in all_videos],
            'play_coin': [[v.play_count, v.coin_count] for v in all_videos],
            'play_favorite': [[v.play_count, v.favorite_count] for v in all_videos],
            'play_danmu': [[v.play_count, v.danmaku_count] for v in all_videos]
        }
        
        return jsonify({
            'status': 'success',
            'ranking_data': ranking_data,
            'correlation_data': correlation_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in video_stats_api: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@main_bp.route('/api/video/interaction_stats', methods=['GET'])
@login_required
def video_interaction_stats():
    """获取视频互动统计数据"""
    try:
        # 获取所有视频的互动数据
        videos = Video.query.all()
        
        # 初始化计数器
        stats = {
            'triple': 0,  # 三连(点赞+投币+收藏)
            'like_favorite': 0,  # 点赞+收藏
            'like_coin': 0,  # 点赞+投币
            'only_like': 0,  # 仅点赞
            'only_favorite': 0,  # 仅收藏
            'only_coin': 0,  # 仅投币
            'no_interaction': 0  # 无互动
        }
        
        for video in videos:
            # 计算每个视频的互动类型
            has_like = bool(video.like_count)
            has_coin = bool(video.coin_count)
            has_favorite = bool(video.favorite_count)
            
            # 获取视频播放量，确保是整数
            play_count = int(video.play_count or 0)
            
            if has_like and has_coin and has_favorite:
                stats['triple'] += play_count
            elif has_like and has_favorite:
                stats['like_favorite'] += play_count
            elif has_like and has_coin:
                stats['like_coin'] += play_count
            elif has_like:
                stats['only_like'] += play_count
            elif has_favorite:
                stats['only_favorite'] += play_count
            elif has_coin:
                stats['only_coin'] += play_count
            else:
                stats['no_interaction'] += play_count
        
        # 确保所有值都是整数
        stats = {k: int(v) for k, v in stats.items()}
        
        return jsonify({
            'status': 'success',
            'data': stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in interaction_stats: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500