import os
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pytz
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

class RestaurantDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.connect()
    
    def connect(self):
        """连接到MongoDB数据库"""
        try:
            self.client = MongoClient(os.getenv('MONGODB_URI'))
            # 测试连接
            self.client.admin.command('ping')
            print("✅ 成功连接到MongoDB")
            
            self.db = self.client[os.getenv('DATABASE_NAME', 'restaurant_db')]
            self.collection = self.db[os.getenv('COLLECTION_NAME', 'restaurants')]
            
        except ConnectionFailure as e:
            print(f"❌ MongoDB连接失败: {e}")
            raise
    
    def is_open_now(self, opening_hours: Dict, timezone: str = 'Asia/Shanghai') -> bool:
        """检查餐厅是否正在营业"""
        if not opening_hours:
            return True  # 如果没有营业时间信息，默认为营业中
        
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        
        # 获取当前是星期几
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        current_weekday = weekdays[now.weekday()]
        
        if current_weekday not in opening_hours:
            return True  # 如果没有当天的营业时间，默认为营业中
        
        hours_str = opening_hours[current_weekday]
        if not hours_str or hours_str.lower() == 'closed':
            return False
        
        try:
            # 解析营业时间 (格式: "10:00-22:00")
            open_time_str, close_time_str = hours_str.split('-')
            open_hour, open_minute = map(int, open_time_str.strip().split(':'))
            close_hour, close_minute = map(int, close_time_str.strip().split(':'))
            
            current_minutes = now.hour * 60 + now.minute
            open_minutes = open_hour * 60 + open_minute
            close_minutes = close_hour * 60 + close_minute
            
            # 处理跨夜营业的情况
            if close_minutes < open_minutes:  # 跨夜营业
                return current_minutes >= open_minutes or current_minutes <= close_minutes
            else:
                return open_minutes <= current_minutes <= close_minutes
                
        except:
            return True  # 如果解析失败，默认为营业中
    
    def build_query(self, filters: Dict) -> Dict:
        """构建MongoDB查询条件"""
        query = {}
        
        # 菜系筛选
        if filters.get('cuisine_type'):
            cuisines = [c.strip() for c in filters['cuisine_type'].split(',')]
            query['cuisine_type'] = {'$in': cuisines}
        
        # 价格范围筛选
        if filters.get('price_range'):
            price = filters['price_range'].strip()
            # 支持单个价格或价格范围
            if '-' in price:  # 例如: "$$-$$$"
                min_price, max_price = price.split('-')
                query['$and'] = [
                    {'price_range': {'$gte': min_price.strip()}},
                    {'price_range': {'$lte': max_price.strip()}}
                ]
            else:
                query['price_range'] = price
        
        # 评分筛选
        if filters.get('min_rating'):
            try:
                min_rating = float(filters['min_rating'])
                query['rating'] = {'$gte': min_rating}
            except ValueError:
                pass
        
        # 标签筛选
        if filters.get('tags'):
            tags = [t.strip() for t in filters['tags'].split(',')]
            query['tags'] = {'$in': tags}
        
        # 关键词搜索（在名称或标签中搜索）
        if filters.get('keyword'):
            keyword = filters['keyword']
            query['$or'] = [
                {'name': {'$regex': keyword, '$options': 'i'}},
                {'tags': {'$regex': keyword, '$options': 'i'}}
            ]
        
        return query
    
    def get_random_restaurants(
        self, 
        count: int = 3, 
        filters: Optional[Dict] = None,
        check_open: bool = True,
        user_location: Optional[Tuple[float, float]] = None,
        max_distance: Optional[float] = None
    ) -> List[Dict]:
        """
        获取随机餐厅
        
        Args:
            count: 返回餐厅数量
            filters: 筛选条件
            check_open: 是否只返回营业中的餐厅
            user_location: 用户位置 (经度, 纬度)
            max_distance: 最大距离（米）
        """
        query = self.build_query(filters or {})
        
        # 地理位置筛选
        if user_location and max_distance:
            query['location'] = {
                '$near': {
                    '$geometry': {
                        'type': 'Point',
                        'coordinates': list(user_location)
                    },
                    '$maxDistance': max_distance
                }
            }
        
        # 获取符合条件的所有餐厅
        restaurants = list(self.collection.find(query))
        
        # 筛选营业中的餐厅
        if check_open:
            open_restaurants = []
            for restaurant in restaurants:
                if self.is_open_now(restaurant.get('opening_hours', {})):
                    open_restaurants.append(restaurant)
            restaurants = open_restaurants
        
        # 随机选择
        if len(restaurants) <= count:
            selected = restaurants
        else:
            selected = random.sample(restaurants, count)
        
        # 转换ObjectId为字符串
        for restaurant in selected:
            restaurant['_id'] = str(restaurant['_id'])
        
        return selected
    
    def close(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()