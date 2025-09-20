from pymongo import MongoClient
import random
from datetime import datetime

# --- MongoDB 连接信息 ---
MONGO_URI = "mongodb://root:1145141919810***@RP4.internal:27017/"
DATABASE_NAME = 'restaurant_db_test'
COLLECTION_NAME = 'restaurants'

# --- 模拟数据生成函数 ---
def generate_random_restaurant_data(num_restaurants=20):
    restaurants = []
    
    # 模拟大学城中心点附近的坐标
    base_lon = 113.39  # 广州大学城附近经度
    base_lat = 23.05   # 广州大学城附近纬度

    # 常见餐厅分类
    cuisine_types = ["中餐", "火锅", "日料", "韩料", "西餐", "快餐", "小吃", "烧烤", "甜品"]
    
    # 价格范围
    price_ranges = ["$", "$$", "$$$", "$$$$"]
    
    # 餐厅名称前缀/后缀
    name_prefixes = ["美味", "老字号", "新潮", "小胖", "开心"]
    name_suffixes = ["小馆", "餐厅", "美食", "酒家", "厨房", "坊"]

    for i in range(num_restaurants):
        name = f"{random.choice(name_prefixes)}{random.choice(cuisine_types)}{random.choice(name_suffixes)}"
        address = f"大学城XX路{random.randint(1, 200)}号"
        
        # 随机生成坐标，模拟在大学城附近
        lon = round(base_lon + random.uniform(-0.02, 0.02), 5) # 经度波动
        lat = round(base_lat + random.uniform(-0.02, 0.02), 5) # 纬度波动

        # 随机选择菜系 (1到3个)
        num_cuisines = random.randint(1, 3)
        selected_cuisines = random.sample(cuisine_types, num_cuisines)
        
        rating = round(random.uniform(3.5, 5.0), 1)
        
        # 简单生成营业时间 (统一格式)
        opening_hours = {day: f"{random.randint(8, 10)}:00-{random.randint(21, 23)}:00" for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
        
        # 随机标签
        tags = random.sample(["适合聚餐", "学生党最爱", "味道正宗", "环境好", "性价比高", "夜宵", "早餐", "下午茶"], random.randint(1, 4))
        
        restaurant = {
            "name": name,
            "address": address,
            "location": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "cuisine_type": selected_cuisines,
            "price_range": random.choice(price_ranges),
            "rating": rating,
            "google_maps_url": f"https://maps.google.com/?q={name.replace(' ', '+')}+{address.replace(' ', '+')}",
            "image_url": f"https://picsum.photos/seed/{i+1}/600/400", # 使用lorempicsum生成随机图片
            "opening_hours": opening_hours,
            "tags": tags,
            "last_updated": datetime.utcnow()
        }
        restaurants.append(restaurant)
    return restaurants

# --- 数据库操作 ---
def insert_test_data(data):
    client = None # 初始化 client 为 None
    try:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        # 插入前先清空集合，确保每次都是新数据 (可选)
        # collection.delete_many({}) 
        # print(f"已清空集合 '{COLLECTION_NAME}'")

        if data:
            result = collection.insert_many(data)
            print(f"成功插入 {len(result.inserted_ids)} 条测试餐厅数据到 '{COLLECTION_NAME}' 集合。")
        else:
            print("没有数据可供插入。")

    except Exception as e:
        print(f"插入数据时发生错误: {e}")
    finally:
        if client:
            client.close()

if __name__ == "__main__":
    num_restaurants_to_generate = 30 # 生成30个测试餐厅
    test_data = generate_random_restaurant_data(num_restaurants_to_generate)
    insert_test_data(test_data)