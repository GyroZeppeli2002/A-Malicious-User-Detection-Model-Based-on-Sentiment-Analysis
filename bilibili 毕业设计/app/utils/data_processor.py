import pandas as pd
import numpy as np
from datetime import datetime

class DataProcessor:
    def __init__(self):
        pass
        
    def handle_missing_values(self, data):
        """处理缺失值"""
        # 将数值型特征的缺失值填充为0
        numeric_columns = ['play_count', 'danmaku_count', 'like_count', 
                         'coin_count', 'favorite_count', 'share_count', 
                         'comment_count']
        for col in numeric_columns:
            data[col] = data[col].fillna(0)
        
        # 将字符串类型特征的缺失值填充为'未知'
        string_columns = ['title', 'author', 'video_type']
        for col in string_columns:
            data[col] = data[col].fillna('未知')
            
        return data
    
    def handle_outliers(self, data):
        """处理异常值"""
        numeric_columns = ['play_count', 'danmaku_count', 'like_count', 
                         'coin_count', 'favorite_count', 'share_count', 
                         'comment_count']
        
        for col in numeric_columns:
            # 使用IQR方法处理异常值
            Q1 = data[col].quantile(0.25)
            Q3 = data[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # 将异常值替换为边界值
            data[col] = data[col].clip(lower=lower_bound, upper=upper_bound)
            
        return data
    
    def convert_data_types(self, data):
        """转换数据类型"""
        # 确保数值型列为整数类型
        numeric_columns = ['play_count', 'danmaku_count', 'like_count', 
                         'coin_count', 'favorite_count', 'share_count', 
                         'comment_count']
        for col in numeric_columns:
            data[col] = data[col].astype(int)
            
        return data
    
    def process_data(self, raw_data):
        """处理原始数据"""
        if not raw_data:
            return []
            
        # 转换为DataFrame
        df = pd.DataFrame(raw_data)
        
        # 处理缺失值
        df = self.handle_missing_values(df)
        
        # 处理异常值
        df = self.handle_outliers(df)
        
        # 转换数据类型
        df = self.convert_data_types(df)
        
        # 添加爬取时间
        df['crawled_time'] = datetime.utcnow()
        
        # 转换回字典列表
        return df.to_dict('records')