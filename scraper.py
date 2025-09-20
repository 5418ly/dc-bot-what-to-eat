import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
import googlemaps
from pymongo import MongoClient, GEOSPHERE
from pymongo.errors import ConnectionFailure, OperationFailure
import logging
from dataclasses import dataclass, field
from openai import OpenAI
import requests

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Restaurant:
    """餐厅数据模型 - 符合指定的JSON结构"""
    name: str
    address: str
    location: Dict[str, Any]  # GeoJSON Point
    cuisine_type: List[str] = field(default_factory=list)
    price_range: str = "$"
    rating: Optional[float] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    opening_hours: Optional[Dict[str, str]] = None
    tags: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "address": self.address,
            "location": self.location,
            "cuisine_type": self.cuisine_type,
            "price_range": self.price_range,
            "rating": self.rating,
            "google_maps_url": self.google_maps_url,
            "image_url": self.image_url,
            "opening_hours": self.opening_hours,
            "tags": self.tags,
            "last_updated": self.last_updated
        }

class SearchConfig:
    """搜索配置 - 非敏感参数"""
    def __init__(self, 
                 location: Tuple[float, float] = (31.2304, 121.4737),  # 上海市中心
                 radius: int = 3000,
                 max_pages: int = 3,
                 fetch_details: bool = True):
        """
        初始化搜索配置
        
        Args:
            location: 中心点坐标 (latitude, longitude)
            radius: 搜索半径（米）
            max_pages: 最多获取的页数
            fetch_details: 是否获取详细信息
        """
        self.location = location
        self.radius = radius
        self.max_pages = max_pages
        self.fetch_details = fetch_details
        
        logger.info(f"搜索配置: 位置={location}, 半径={radius}米, 最大页数={max_pages}")

class APIConfig:
    """API配置管理类 - 从环境变量加载敏感数据"""
    
    def __init__(self):
        # Google Maps API配置
        self.GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.GOOGLE_MAPS_API_KEY:
            raise ValueError("请设置环境变量 GOOGLE_MAPS_API_KEY")
        
        # MongoDB配置
        self.MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        self.MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'restaurant_db')
        self.MONGO_COLLECTION_NAME = os.getenv('MONGO_COLLECTION_NAME', 'restaurants')
        
        # OpenAI配置（可选）
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL')  # 支持自定义endpoint
        self.OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')  # 支持自定义模型
        
        # 日志输出配置信息（隐藏敏感数据）
        logger.info(f"API配置加载完成:")
        logger.info(f"  - Google Maps API: {'已配置' if self.GOOGLE_MAPS_API_KEY else '未配置'}")
        logger.info(f"  - MongoDB: {self.MONGO_DB_NAME}.{self.MONGO_COLLECTION_NAME}")
        logger.info(f"  - OpenAI: {'已配置' if self.OPENAI_API_KEY else '未配置'}")
        if self.OPENAI_BASE_URL:
            logger.info(f"  - OpenAI Base URL: {self.OPENAI_BASE_URL}")
        if self.OPENAI_API_KEY:
            logger.info(f"  - OpenAI Model: {self.OPENAI_MODEL}")

class RestaurantFetcher:
    """获取餐厅数据的主类"""
    
    def __init__(self, api_config: APIConfig, search_config: SearchConfig = None):
        """
        初始化
        
        Args:
            api_config: API配置对象
            search_config: 搜索配置对象
        """
        self.api_config = api_config
        self.search_config = search_config or SearchConfig()
        self.gmaps = googlemaps.Client(key=api_config.GOOGLE_MAPS_API_KEY)
        
        # 连接MongoDB
        self.mongo_client = MongoClient(api_config.MONGO_URI)
        self.db = self.mongo_client[api_config.MONGO_DB_NAME]
        self.collection = self.db[api_config.MONGO_COLLECTION_NAME]
        
        # 测试连接
        self._test_connections()
        
        # 创建地理空间索引
        self._setup_indexes()
        
        # 初始化OpenAI客户端（如果有API密钥）
        self.openai_client = None
        if api_config.OPENAI_API_KEY:
            try:
                # 构建OpenAI客户端参数
                openai_kwargs = {
                    'api_key': api_config.OPENAI_API_KEY
                }
                
                # 如果设置了自定义base_url
                if api_config.OPENAI_BASE_URL:
                    openai_kwargs['base_url'] = api_config.OPENAI_BASE_URL
                    logger.info(f"使用自定义OpenAI Base URL: {api_config.OPENAI_BASE_URL}")
                
                self.openai_client = OpenAI(**openai_kwargs)
                
                # 测试连接
                self._test_openai_connection()
                
            except Exception as e:
                logger.warning(f"OpenAI客户端初始化失败: {str(e)}")
                self.openai_client = None
    
    def _test_connections(self):
        """测试数据库连接"""
        try:
            self.mongo_client.admin.command('ping')
            logger.info("MongoDB连接成功")
        except ConnectionFailure:
            logger.error("MongoDB连接失败")
            raise
    
    def _test_openai_connection(self):
        """测试OpenAI连接"""
        if not self.openai_client:
            return
            
        try:
            # 发送一个简单的测试请求
            response = self.openai_client.chat.completions.create(
                model=self.api_config.OPENAI_MODEL,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            logger.info(f"OpenAI连接测试成功 (Model: {self.api_config.OPENAI_MODEL})")
        except Exception as e:
            logger.warning(f"OpenAI连接测试失败: {str(e)}")
            # 不抛出异常，允许继续运行（使用规则推断）
    
    def _setup_indexes(self):
        """设置MongoDB索引"""
        try:
            # 创建地理空间2dsphere索引
            self.collection.create_index([("location", GEOSPHERE)])
            # 创建name的唯一复合索引（name + address组合唯一）
            self.collection.create_index([("name", 1), ("address", 1)], unique=True)
            logger.info("MongoDB索引创建成功")
        except Exception as e:
            logger.warning(f"索引创建警告: {str(e)}")
    
    def search_restaurants_nearby(self, location: Tuple[float, float] = None, 
                                 radius: int = None,
                                 max_pages: int = None) -> List[Dict]:
        """
        搜索附近的餐厅
        
        Args:
            location: 中心点坐标 (latitude, longitude)
            radius: 搜索半径（米）
            max_pages: 最多获取的页数
            
        Returns:
            餐厅列表
        """
        # 使用默认配置或传入的参数
        location = location or self.search_config.location
        radius = radius or self.search_config.radius
        max_pages = max_pages or self.search_config.max_pages
            
        restaurants = []
        next_page_token = None
        page_count = 0
        
        try:
            while page_count < max_pages:
                if next_page_token:
                    time.sleep(2)  # 等待token生效
                    results = self.gmaps.places_nearby(
                        page_token=next_page_token
                    )
                else:
                    results = self.gmaps.places_nearby(
                        location=location,
                        radius=radius,
                        type='restaurant'
                    )
                
                restaurants.extend(results.get('results', []))
                page_count += 1
                
                logger.info(f"获取第 {page_count} 页，本页包含 {len(results.get('results', []))} 家餐厅")
                
                next_page_token = results.get('next_page_token')
                if not next_page_token:
                    break
                    
            logger.info(f"搜索完成，共找到 {len(restaurants)} 家餐厅")
            return restaurants
            
        except Exception as e:
            logger.error(f"搜索餐厅时出错: {str(e)}")
            raise
    
    def get_place_details(self, place_id: str) -> Dict:
        """
        获取地点详细信息
        
        Args:
            place_id: Google地点ID
            
        Returns:
            地点详细信息
        """
        try:
            # 修正字段名称：types -> type, photos -> photo
            result = self.gmaps.place(
                place_id=place_id,
                fields=[
                    'name', 
                    'formatted_address', 
                    'geometry',
                    'rating', 
                    'user_ratings_total', 
                    'price_level',
                    'formatted_phone_number', 
                    'website', 
                    'url',
                    'opening_hours',
                    'current_opening_hours',  # 添加当前营业时间
                    'type',  # 修正：types -> type
                    'business_status',
                    'photo',  # 修正：photos -> photo
                    'editorial_summary',
                    'vicinity',
                    'plus_code',
                    'international_phone_number'
                ],
                language='zh-CN'  # 请求中文结果
            )
            return result.get('result', {})
        except Exception as e:
            logger.error(f"获取地点详情失败 {place_id}: {str(e)}")
            return {}
    
    def _convert_price_level(self, price_level: Optional[int]) -> str:
        """
        转换Google的价格等级到$符号
        
        Args:
            price_level: Google的价格等级 (0-4)
            
        Returns:
            价格范围字符串
        """
        if price_level is None:
            return "$$"  # 默认中等价位
        
        price_map = {
            0: "$",
            1: "$",
            2: "$$",
            3: "$$$",
            4: "$$$$"
        }
        return price_map.get(price_level, "$$")
    
    def _format_opening_hours(self, opening_hours: Optional[Dict], 
                             current_opening_hours: Optional[Dict] = None) -> Optional[Dict[str, str]]:
        """
        格式化营业时间
        
        Args:
            opening_hours: Google返回的营业时间数据
            current_opening_hours: 当前营业时间数据（优先使用）
            
        Returns:
            格式化后的营业时间
        """
        # 优先使用current_opening_hours
        hours_data = current_opening_hours or opening_hours
        
        if not hours_data or 'weekday_text' not in hours_data:
            return None
        
        weekday_text = hours_data.get('weekday_text', [])
        if not weekday_text:
            return None
        
        # 星期映射（中文到英文）
        weekday_map = {
            '星期一': 'monday',
            '星期二': 'tuesday',
            '星期三': 'wednesday',
            '星期四': 'thursday',
            '星期五': 'friday',
            '星期六': 'saturday',
            '星期日': 'sunday',
            '周一': 'monday',
            '周二': 'tuesday',
            '周三': 'wednesday',
            '周四': 'thursday',
            '周五': 'friday',
            '周六': 'saturday',
            '周日': 'sunday',
            'Monday': 'monday',
            'Tuesday': 'tuesday',
            'Wednesday': 'wednesday',
            'Thursday': 'thursday',
            'Friday': 'friday',
            'Saturday': 'saturday',
            'Sunday': 'sunday'
        }
        
        formatted_hours = {}
        for text in weekday_text:
            # 解析格式：'星期一: 11:00 – 22:00' 或 'Monday: 11:00 AM – 10:00 PM'
            parts = text.split(': ', 1)
            if len(parts) == 2:
                day_zh = parts[0].split(':')[0]  # 处理可能的冒号
                for zh, en in weekday_map.items():
                    if zh in day_zh or en in day_zh:
                        hours = parts[1].strip()
                        if '休息' in hours or 'Closed' in hours:
                            hours = 'Closed'
                        formatted_hours[en] = hours
                        break
        
        # 确保所有天都有值
        all_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day in all_days:
            if day not in formatted_hours:
                formatted_hours[day] = 'Unknown'
        
        return formatted_hours
    
    def _get_photo_url(self, photos: Any) -> Optional[str]:
        """
        获取餐厅照片URL
        
        Args:
            photos: Google返回的照片数据（可能是列表或单个对象）
            
        Returns:
            照片URL
        """
        if not photos:
            return None
        
        try:
            # 处理不同的照片数据格式
            photo_list = []
            if isinstance(photos, list):
                photo_list = photos
            elif isinstance(photos, dict):
                photo_list = [photos]
            else:
                return None
            
            if not photo_list:
                return None
            
            # 获取第一张照片
            first_photo = photo_list[0]
            photo_reference = first_photo.get('photo_reference')
            
            if photo_reference:
                # 构建Google Places Photos API URL
                url = f"https://maps.googleapis.com/maps/api/place/photo"
                params = {
                    'maxwidth': 800,
                    'photoreference': photo_reference,
                    'key': self.api_config.GOOGLE_MAPS_API_KEY
                }
                # 获取实际的图片URL（通过重定向）
                response = requests.get(url, params=params, allow_redirects=False)
                if response.status_code == 302:
                    return response.headers.get('Location')
                else:
                    # 返回API URL
                    return f"{url}?maxwidth=800&photoreference={photo_reference}&key={self.api_config.GOOGLE_MAPS_API_KEY}"
        except Exception as e:
            logger.warning(f"获取照片URL失败: {str(e)}")
        
        return None
    
    def _infer_cuisine_and_tags(self, name: str, types: List[str], 
                                address: str = "") -> Tuple[List[str], List[str]]:
        """
        推断餐厅的菜系类型和标签
        
        Args:
            name: 餐厅名称
            types: Google返回的类型列表
            address: 餐厅地址
            
        Returns:
            (菜系列表, 标签列表)
        """
        cuisine_types = []
        tags = []
        
        # 使用LLM推断（如果可用）
        if self.openai_client:
            try:
                prompt = f"""
                分析以下餐厅信息，返回JSON格式的菜系和标签：
                餐厅名称：{name}
                地址：{address}
                Google类型：{types}
                
                请返回如下JSON格式（不要有其他文字）：
                {{
                    "cuisine_type": ["菜系1", "菜系2"],
                    "tags": ["标签1", "标签2", "标签3"]
                }}
                
                菜系示例：川菜、粤菜、江浙菜、湘菜、东北菜、西餐、日料、韩料、火锅、烧烤、快餐、咖啡轻食、面食、清真菜等
                标签示例：适合聚餐、有包间、24小时营业、连锁品牌、网红店、老字号、适合约会、有停车位、环境优雅、性价比高等
                """
                
                response = self.openai_client.chat.completions.create(
                    model=self.api_config.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个餐厅分类专家，精通各种菜系。请直接返回JSON格式结果。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=200
                )
                
                result_text = response.choices[0].message.content.strip()
                # 尝试提取JSON部分
                if '{' in result_text and '}' in result_text:
                    json_start = result_text.index('{')
                    json_end = result_text.rindex('}') + 1
                    json_str = result_text[json_start:json_end]
                    result = json.loads(json_str)
                    cuisine_types = result.get('cuisine_type', [])
                    tags = result.get('tags', [])
                    logger.debug(f"LLM推断成功: {name} -> 菜系={cuisine_types}, 标签={tags}")
                
            except Exception as e:
                logger.warning(f"LLM推断失败 ({name}): {str(e)}")
        
        # 如果LLM推断失败或不可用，使用规则推断
        if not cuisine_types:
            cuisine_keywords = {
                '川菜': ['川', '麻辣', '水煮', '回锅肉', '毛血旺', '辣子鸡'],
                '粤菜': ['粤', '广东', '茶餐厅', '早茶', '点心', '烧腊', '煲仔饭'],
                '江浙菜': ['江浙', '江南', '本帮', '淮扬', '杭帮'],
                '湘菜': ['湘', '湖南', '剁椒', '湘西'],
                '东北菜': ['东北', '哈尔滨', '锅包肉'],
                '火锅': ['火锅', '涮', '麻辣烫', '串串'],
                '日料': ['日本', '日式', '寿司', '刺身', '拉面', '居酒屋', '和食'],
                '韩料': ['韩国', '韩式', '烤肉', '泡菜', '石锅', '部队锅'],
                '西餐': ['西餐', '牛排', '意大利', 'Pizza', 'Pasta', '法式', '德国', '汉堡'],
                '烧烤': ['烧烤', '烤肉', 'BBQ', '烤串', '烤鱼'],
                '快餐': ['快餐', 'KFC', '麦当劳', '汉堡王', 'McDonald', 'Burger', '德克士'],
                '咖啡轻食': ['咖啡', 'Coffee', 'Cafe', '星巴克', 'Starbucks', '瑞幸'],
                '面食': ['面', '拉面', '刀削面', '兰州', '重庆小面'],
                '清真菜': ['清真', '新疆', '兰州', '羊肉', '烤羊'],
                '海鲜': ['海鲜', '海鲜', '水产', '鱼', '虾', '蟹'],
                '素食': ['素食', '素菜', '斋'],
                '甜品': ['甜品', '甜点', '蛋糕', '面包', 'Bakery'],
            }
            
            name_lower = name.lower()
            for cuisine, keywords in cuisine_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in name_lower:
                        cuisine_types.append(cuisine)
                        break
            
            if not cuisine_types:
                cuisine_types = ['其他']
        
        # 推断标签
        if not tags:
            tags = []
            
            # 根据Google types推断
            if 'bar' in types:
                tags.append('有酒吧')
            if 'cafe' in types:
                tags.append('咖啡厅')
            if 'meal_delivery' in types:
                tags.append('支持外送')
            if 'meal_takeaway' in types:
                tags.append('支持外带')
                
            # 根据名称推断
            brand_keywords = ['海底捞', 'KFC', '麦当劳', '星巴克', '必胜客', '肯德基', 
                            '汉堡王', '德克士', '瑞幸', '喜茶', '奈雪']
            if any(brand in name for brand in brand_keywords):
                tags.append('连锁品牌')
            
            if any(keyword in name for keyword in ['老字号', '老店', '传统']):
                tags.append('老字号')
                
            if any(keyword in name for keyword in ['自助', 'Buffet']):
                tags.append('自助餐')
            
            # 默认标签
            if not tags:
                tags = ['餐厅']
        
        return cuisine_types, tags
    
    def format_restaurant_data(self, place_data: Dict, detail_data: Dict = None) -> Restaurant:
        """
        格式化餐厅数据为指定的JSON结构
        
        Args:
            place_data: 基本地点数据
            detail_data: 详细地点数据
            
        Returns:
            格式化后的Restaurant对象
        """
        # 合并数据
        data = {**place_data}
        if detail_data:
            data.update(detail_data)
        
        # 提取坐标
        geometry = data.get('geometry', {})
        location = geometry.get('location', {})
        lat = location.get('lat', 0)
        lng = location.get('lng', 0)
        
        # GeoJSON格式的位置信息（注意：MongoDB要求[经度, 纬度]的顺序）
        geo_location = {
            "type": "Point",
            "coordinates": [lng, lat]  # [longitude, latitude]
        }
        
        # 获取名称和地址
        name = data.get('name', '')
        address = data.get('formatted_address', data.get('vicinity', ''))
        
        # 处理类型字段（type或types）
        types = data.get('type', data.get('types', []))
        if not isinstance(types, list):
            types = [types] if types else []
        
        # 推断菜系和标签
        cuisine_types, tags = self._infer_cuisine_and_tags(
            name,
            types,
            address
        )
        
        # 格式化营业时间
        opening_hours = self._format_opening_hours(
            data.get('opening_hours'),
            data.get('current_opening_hours')
        )
        
        # 获取照片URL
        image_url = self._get_photo_url(data.get('photo', data.get('photos')))
        
        # Google Maps URL
        google_maps_url = data.get('url')
        if not google_maps_url and data.get('place_id'):
            google_maps_url = f"https://www.google.com/maps/place/?q=place_id:{data['place_id']}"
        
        # 创建Restaurant对象
        restaurant = Restaurant(
            name=name,
            address=address,
            location=geo_location,
            cuisine_type=cuisine_types,
            price_range=self._convert_price_level(data.get('price_level')),
            rating=data.get('rating'),
            google_maps_url=google_maps_url,
            image_url=image_url,
            opening_hours=opening_hours,
            tags=tags,
            last_updated=datetime.now()
        )
        
        return restaurant
    
    def save_to_mongodb(self, restaurants: List[Restaurant]) -> int:
        """
        保存餐厅数据到MongoDB
        
        Args:
            restaurants: 餐厅列表
            
        Returns:
            保存的文档数量
        """
        try:
            if not restaurants:
                return 0
            
            inserted_count = 0
            updated_count = 0
            
            for restaurant in restaurants:
                doc = restaurant.to_dict()
                
                # 使用name和address作为唯一标识，进行upsert操作
                filter_query = {
                    "name": doc["name"],
                    "address": doc["address"]
                }
                
                # 更新或插入
                result = self.collection.update_one(
                    filter_query,
                    {"$set": doc},
                    upsert=True
                )
                
                if result.upserted_id:
                    inserted_count += 1
                    logger.debug(f"插入新餐厅: {doc['name']}")
                elif result.modified_count > 0:
                    updated_count += 1
                    logger.debug(f"更新餐厅: {doc['name']}")
            
            logger.info(f"处理完成: 新增 {inserted_count} 家，更新 {updated_count} 家餐厅")
            return inserted_count + updated_count
            
        except Exception as e:
            logger.error(f"保存到MongoDB失败: {str(e)}")
            raise
    
    def fetch_and_save(self, location: Tuple[float, float] = None, 
                      radius: int = None,
                      fetch_details: bool = None) -> Dict[str, Any]:
        """
        主方法：获取并保存餐厅数据
        
        Args:
            location: 中心点坐标 (latitude, longitude)
            radius: 搜索半径（米）
            fetch_details: 是否获取详细信息
            
        Returns:
            执行结果统计
        """
        # 使用默认值或传入的参数
        location = location or self.search_config.location
        radius = radius or self.search_config.radius
        fetch_details = fetch_details if fetch_details is not None else self.search_config.fetch_details
            
        logger.info(f"开始获取位置 {location} 半径 {radius}米内的餐厅")
        
        # 搜索餐厅
        places = self.search_restaurants_nearby(location, radius)
        
        # 格式化数据
        restaurants = []
        for i, place in enumerate(places):
            try:
                logger.info(f"处理进度: {i+1}/{len(places)} - {place.get('name', 'Unknown')}")
                
                # 获取详细信息
                detail_data = None
                if fetch_details:
                    detail_data = self.get_place_details(place['place_id'])
                    time.sleep(0.5)  # 避免请求过快
                
                # 格式化数据
                restaurant = self.format_restaurant_data(place, detail_data)
                restaurants.append(restaurant)
                
            except Exception as e:
                logger.error(f"处理餐厅数据失败: {str(e)}")
                continue
        
        # 保存到MongoDB
        saved_count = self.save_to_mongodb(restaurants)
        
        # 返回统计结果
        result = {
            "total_found": len(places),
            "processed": len(restaurants),
            "saved": saved_count,
            "location": {
                "latitude": location[0],
                "longitude": location[1]
            },
            "radius": radius,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"处理完成: {json.dumps(result, indent=2, ensure_ascii=False)}")
        return result
    
    def query_restaurants(self, filters: Dict = None, limit: int = 10) -> List[Dict]:
        """
        查询餐厅数据
        
        Args:
            filters: 查询条件
            limit: 返回数量限制
            
        Returns:
            餐厅列表
        """
        try:
            query = filters or {}
            cursor = self.collection.find(query).limit(limit)
            
            restaurants = []
            for doc in cursor:
                # 将ObjectId转换为字符串
                doc['_id'] = str(doc['_id'])
                restaurants.append(doc)
            
            return restaurants
            
        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            return []
    
    def find_nearby_restaurants(self, center: Tuple[float, float], 
                               max_distance_meters: int = 1000,
                               limit: int = 10) -> List[Dict]:
        """
        查找附近的餐厅（使用MongoDB地理查询）
        
        Args:
            center: 中心点坐标 (latitude, longitude)
            max_distance_meters: 最大距离（米）
            limit: 返回数量限制
            
        Returns:
            餐厅列表
        """
        try:
            # MongoDB地理查询
            query = {
                "location": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [center[1], center[0]]  # [lng, lat]
                        },
                        "$maxDistance": max_distance_meters
                    }
                }
            }
            
            cursor = self.collection.find(query).limit(limit)
            
            restaurants = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                restaurants.append(doc)
            
            return restaurants
            
        except Exception as e:
            logger.error(f"地理查询失败: {str(e)}")
            return []

def main():
    """主函数示例"""
    
    try:
        # 加载API配置（从环境变量）
        api_config = APIConfig()
        
        # 设置搜索配置（非敏感数据，可直接配置）
        search_config = SearchConfig(
            location=(31.2304, 121.4737),  # 上海市中心
            radius=2000,                    # 2公里半径
            max_pages=2,                    # 最多获取2页
            fetch_details=True              # 获取详细信息
        )
        
        # 创建fetcher实例
        fetcher = RestaurantFetcher(api_config, search_config)
        
        # 执行获取和保存
        result = fetcher.fetch_and_save()
        
        # 输出结果
        print("\n" + "="*60)
        print("执行结果:")
        print("="*60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 查询示例
        print("\n" + "="*60)
        print("查询已保存的餐厅示例:")
        print("="*60)
        
        # 查询评分高于4.5的餐厅
        high_rated = fetcher.query_restaurants(
            filters={"rating": {"$gte": 4.5}},
            limit=5
        )
        
        for restaurant in high_rated:
            print(f"\n餐厅名称: {restaurant['name']}")
            print(f"  地址: {restaurant['address']}")
            print(f"  菜系: {', '.join(restaurant.get('cuisine_type', []))}")
            print(f"  评分: {restaurant.get('rating', 'N/A')}")
            print(f"  价格: {restaurant.get('price_range', 'N/A')}")
            print(f"  标签: {', '.join(restaurant.get('tags', []))}")
        
        # 地理位置查询示例
        print("\n" + "="*60)
        print("查询附近1公里内的餐厅:")
        print("="*60)
        
        nearby = fetcher.find_nearby_restaurants(
            center=search_config.location,
            max_distance_meters=1000,
            limit=5
        )
        
        for restaurant in nearby:
            print(f"- {restaurant['name']} ({restaurant.get('rating', 'N/A')}星)")
        
    except Exception as e:
        logger.error(f"执行失败: {str(e)}")
        raise

if __name__ == "__main__":
    main()