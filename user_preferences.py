# user_preferences.py
import os
from typing import Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure
from dotenv import load_dotenv

load_dotenv()

class UserPreferencesDB:
    def __init__(self):
        """初始化用户偏好数据库客户端"""
        self.client = AsyncIOMotorClient(os.getenv('MONGODB_URI'))
        self.db = self.client[os.getenv('DATABASE_NAME', 'restaurant_db')]
        self.collection = self.db[os.getenv('USER_PREFERENCES_COLLECTION', 'user_preferences')]
        self.location_aliases_collection = self.db[os.getenv('LOCATION_ALIASES_COLLECTION', 'location_aliases')]
        print("✅ 用户偏好数据库异步客户端已初始化。")
    
    async def connect_and_setup(self):
        """检查连接和设置索引"""
        try:
            await self.client.admin.command('ping')
            await self._ensure_indexes()
            print("✅ 成功连接到用户偏好数据库并确认索引。")
        except ConnectionFailure as e:
            print(f"❌ MongoDB连接失败: {e}")
            raise
    
    async def _ensure_indexes(self):
        """创建索引"""
        try:
            # 用户偏好索引
            await self.collection.create_index([("user_id", 1)], unique=True)
            # 位置别名索引
            await self.location_aliases_collection.create_index([("alias", 1)], unique=True)
            await self.location_aliases_collection.create_index([("created_by", 1)])
            print("   - 用户偏好数据库索引已确认。")
        except OperationFailure as e:
            print(f"⚠️ 创建索引时发生错误 (可能是已存在): {e}")
    
    # ===== 用户偏好管理 =====
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """获取用户偏好"""
        return await self.collection.find_one({'user_id': user_id})
    
    async def set_default_location(
        self, 
        user_id: str, 
        latitude: float, 
        longitude: float, 
        address: str = None,
        radius: int = 2000
    ) -> Dict:
        """设置用户的默认查询位置"""
        location_data = {
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude
            },
            "address": address,
            "radius": radius
        }
        
        result = await self.collection.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'user_id': user_id,
                    'default_location': location_data
                }
            },
            upsert=True
        )
        
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None
        }
    
    async def get_default_location(self, user_id: str) -> Optional[Dict]:
        """获取用户的默认位置"""
        prefs = await self.get_user_preferences(user_id)
        if prefs and 'default_location' in prefs:
            return prefs['default_location']
        return None
    
    async def clear_default_location(self, user_id: str) -> int:
        """清除用户的默认位置"""
        result = await self.collection.update_one(
            {'user_id': user_id},
            {'$unset': {'default_location': ""}}
        )
        return result.modified_count
    
    # ===== 位置别名管理（黑话） =====
    
    async def add_location_alias(
        self, 
        alias: str, 
        latitude: float, 
        longitude: float,
        address: str = None,
        description: str = None,
        created_by: str = None,
        guild_id: str = None
    ) -> Dict:
        """
        添加位置别名（黑话）
        
        Args:
            alias: 别名，如 "学校"、"公司"
            latitude: 纬度
            longitude: 经度
            address: 地址描述
            description: 额外说明
            created_by: 创建者ID
            guild_id: 服务器ID（如果为空则为全局别名）
        """
        alias_data = {
            "alias": alias.lower(),  # 统一小写存储
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude
            },
            "address": address,
            "description": description,
            "created_by": created_by,
            "guild_id": guild_id,  # None表示全局别名
        }
        
        result = await self.location_aliases_collection.update_one(
            {
                'alias': alias.lower(),
                'guild_id': guild_id  # 同一个服务器内的别名唯一
            },
            {'$set': alias_data},
            upsert=True
        )
        
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None
        }
    
    async def get_location_alias(self, alias: str, guild_id: str = None) -> Optional[Dict]:
        """
        获取位置别名
        优先查找服务器内的别名，如果没有则查找全局别名
        """
        # 先查找服务器特定的别名
        if guild_id:
            result = await self.location_aliases_collection.find_one({
                'alias': alias.lower(),
                'guild_id': guild_id
            })
            if result:
                return result
        
        # 查找全局别名
        result = await self.location_aliases_collection.find_one({
            'alias': alias.lower(),
            'guild_id': None
        })
        return result
    
    async def delete_location_alias(self, alias: str, guild_id: str = None) -> int:
        """删除位置别名"""
        result = await self.location_aliases_collection.delete_one({
            'alias': alias.lower(),
            'guild_id': guild_id
        })
        return result.deleted_count
    
    async def list_location_aliases(self, guild_id: str = None, include_global: bool = True) -> List[Dict]:
        """
        列出位置别名
        
        Args:
            guild_id: 服务器ID
            include_global: 是否包含全局别名
        """
        query = {}
        if guild_id:
            if include_global:
                query = {'$or': [{'guild_id': guild_id}, {'guild_id': None}]}
            else:
                query = {'guild_id': guild_id}
        else:
            query = {'guild_id': None}
        
        cursor = self.location_aliases_collection.find(query)
        aliases = []
        async for doc in cursor:
            doc['_id'] = str(doc['_id'])
            aliases.append(doc)
        return aliases
    
    async def close(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
            print("用户偏好数据库连接已关闭。")
