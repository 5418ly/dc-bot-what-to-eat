# database.py (使用 Motor 进行异步操作)

import os
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import pytz
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient # <-- 1. 导入异步客户端
from pymongo.errors import ConnectionFailure, OperationFailure

load_dotenv()

class RestaurantDB:
    def __init__(self):
        """
        初始化客户端。注意：这里的初始化是非阻塞的。
        实际的连接和操作将在第一个 await 调用时发生。
        """
        self.client = AsyncIOMotorClient(os.getenv('MONGODB_URI')) # <-- 2. 使用异步客户端
        self.db = self.client[os.getenv('DATABASE_NAME', 'restaurant_db')]
        self.collection = self.db[os.getenv('COLLECTION_NAME', 'restaurants')]
        print("✅ MongoDB 异步客户端已初始化。")

    async def connect_and_setup(self):
        """一个独立的异步方法来检查连接和设置索引"""
        try:
            await self.client.admin.command('ping') # <-- 3. 所有网络操作都需要 await
            await self._ensure_indexes()
            print("✅ 成功连接到MongoDB并确认索引。")
        except ConnectionFailure as e:
            print(f"❌ MongoDB连接失败: {e}")
            raise
    
    async def _ensure_indexes(self):
        """异步创建索引"""
        try:
            await self.collection.create_index([("location", "2dsphere")])
            await self.collection.create_index([("google_place_id", 1)], unique=True, sparse=True)
            print("   - 数据库索引已确认。")
        except OperationFailure as e:
            print(f"⚠️ 创建索引时发生错误 (可能是已存在): {e}")

    async def add_or_update_restaurant(self, restaurant_data: Dict) -> Dict:
        """异步添加或更新餐厅"""
        if 'google_place_id' not in restaurant_data:
            raise ValueError("餐厅数据必须包含 'google_place_id'")

        place_id = restaurant_data['google_place_id']
        restaurant_data['last_updated'] = datetime.utcnow()

        result = await self.collection.update_one( # <-- 4. await aio 操作
            {'google_place_id': place_id},
            {'$set': restaurant_data},
            upsert=True
        )
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None
        }

    async def delete_restaurant_by_place_id(self, place_id: str) -> int:
        """异步删除餐厅"""
        result = await self.collection.delete_one({'google_place_id': place_id})
        return result.deleted_count

    async def get_restaurant_by_place_id(self, place_id: str) -> Optional[Dict]:
        """异步获取餐厅"""
        return await self.collection.find_one({'google_place_id': place_id})

    async def get_all_tags(self) -> List[str]:
        """异步获取所有标签"""
        return await self.collection.distinct("tags")

    async def get_all_cuisine_types(self) -> List[str]:
        """异步获取所有菜系"""
        return await self.collection.distinct("cuisine_type")

    # is_open_at_time 是纯计算，不需要 async
    def is_open_at_time(self, opening_hours: Dict, target_dt: datetime, timezone_str: str = 'Asia/Shanghai') -> bool:
        # ... (此函数逻辑不变)
        if not opening_hours: return True
        tz = pytz.timezone(timezone_str)
        localized_dt = target_dt.astimezone(tz)
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        current_weekday = weekdays[localized_dt.weekday()]
        hours_str = opening_hours.get(current_weekday)
        if not hours_str or hours_str.lower() in ['closed', '休息']: return False
        if hours_str.lower() in ['open 24 hours', '24小时营业', '00:00-24:00']: return True
        try:
            open_time_str, close_time_str = hours_str.split('-')
            open_hour, open_minute = map(int, open_time_str.strip().split(':'))
            close_hour, close_minute = map(int, close_time_str.strip().split(':'))
            current_minutes = localized_dt.hour * 60 + localized_dt.minute
            open_minutes = open_hour * 60 + open_minute
            close_minutes = close_hour * 60 + close_minute
            if close_minutes < open_minutes:
                return current_minutes >= open_minutes or current_minutes < close_minutes
            else:
                return open_minutes <= current_minutes < close_minutes
        except (ValueError, TypeError):
            return True

    # _build_query_from_llm_filters 是纯计算，不需要 async
    def _build_query_from_llm_filters(self, filters: Dict) -> Dict:
        # ... (此函数逻辑不变)
        query = {}
        and_conditions = []
        if 'cuisine_type' in filters and filters['cuisine_type']:
            and_conditions.append({'cuisine_type': {'$in': filters['cuisine_type']}})
        if 'price_range' in filters and filters['price_range']:
            and_conditions.append({'price_range': {'$in': filters['price_range']}})
        if 'min_rating' in filters:
            try:
                and_conditions.append({'rating': {'$gte': float(filters['min_rating'])}})
            except (ValueError, TypeError): pass
        if 'keywords' in filters and filters['keywords']:
            keyword_regex = "|".join(filters['keywords'])
            and_conditions.append({
                '$or': [
                    {'name': {'$regex': keyword_regex, '$options': 'i'}},
                    {'tags': {'$in': filters['keywords']}},
                    {'cuisine_type': {'$in': filters['keywords']}}
                ]
            })
        if and_conditions:
            query['$and'] = and_conditions
        return query

    async def find_restaurants(self, filters: Optional[Dict] = None, query_time: Optional[datetime] = None, count: int = 3) -> List[Dict]:
        query = self._build_query_from_llm_filters(filters or {})
        
        cursor = self.collection.find(query)
        # <-- 5. 异步迭代 cursor
        potential_restaurants = [doc async for doc in cursor]

        target_time = query_time if query_time is not None else datetime.now()
        open_restaurants = [
            r for r in potential_restaurants 
            if self.is_open_at_time(r.get('opening_hours', {}), target_time)
        ]

        if len(open_restaurants) > count:
            selected_restaurants = random.sample(open_restaurants, count)
        else:
            selected_restaurants = open_restaurants
        
        for r in selected_restaurants:
            r['_id'] = str(r['_id'])
        
        return selected_restaurants

    async def close(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")