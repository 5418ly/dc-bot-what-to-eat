# crawler.py

import os
import asyncio
import json
from typing import Dict, List, Any

import googlemaps
from dotenv import load_dotenv
# 核心改动：导入异步客户端 AsyncOpenAI
from openai import AsyncOpenAI

from database import RestaurantDB

load_dotenv()

class GoogleMapsCrawler:
    def __init__(self):
        gmaps_key = os.getenv("GOOGLE_MAPS_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_base = os.getenv("OPENAI_API_BASE")
        self.llm_model = os.getenv("LLM_MODEL_NAME", "gpt-4-turbo-preview")

        if not gmaps_key:
            raise ValueError("未在 .env 文件中找到 GOOGLE_MAPS_API_KEY")
        if not openai_key:
            raise ValueError("未在 .env 文件中找到 OPENAI_API_KEY")

        self.gmaps = googlemaps.Client(key=gmaps_key)
        # 核心改动：实例化异步客户端
        self.llm_client = AsyncOpenAI(api_key=openai_key, base_url=openai_base)
        self.db = RestaurantDB()
        self.gmaps_key = gmaps_key
        print("✅ Google Maps 爬虫已初始化")

    def get_place_id_from_plus_code(self, plus_code: str) -> str:
        """
        使用 Geocoding API 将 Google Plus Code 转换为 Place ID。

        Args:
            plus_code: Google Plus Code, 例如 "3V7V+2M 广州市" 或 "87G83V7V+2M"。

        Returns:
            如果找到，返回对应的 Place ID 字符串；否则返回 None。
        """
        print(f"🗺️ 正在通过 Plus Code '{plus_code}' 查询 Place ID...")
        try:
            # 使用 Geocoding API 进行查询
            geocode_result = self.gmaps.geocode(address=plus_code, language='zh-CN')

            if not geocode_result:
                print("   - ❌ Geocoding API 未返回任何结果。")
                return None

            # geocode_result 是一个列表，我们取第一个结果
            first_result = geocode_result[0]
            place_id = first_result.get('place_id')

            if place_id:
                found_address = first_result.get('formatted_address', '未知地址')
                print(f"   - ✅ 找到 Place ID: {place_id} (地址: {found_address})")
                return place_id
            else:
                print("   - ❌ 查询结果中不包含 Place ID。")
                return None

        except Exception as e:
            print(f"   - ❌调用 Geocoding API 时出错: {e}")
            return None

    def _construct_llm_prompt_for_structuring(self) -> str:
        """为LLM构建用于结构化 Google Place 数据的系统提示。"""
        # 注意: 這個 Prompt 是整個爬蟲的靈魂，需要精心設計
        return """
你是一个数据处理专家，专门从 Google Maps API 返回的原始 JSON 数据中提取和清洗餐厅信息。
你的任务是：
1. 分析提供的地点数据，判断它是否是一个餐厅、咖啡馆、酒吧、面包店或任何提供堂食/外卖餐饮服务的场所。
2. 如果它不是餐饮场所（例如：超市、公园、五金店），你必须只返回 `{"is_restaurant": false}`。
3. 如果是餐饮场所，你必须提取信息并严格按照以下 JSON 结构返回数据。不要添加任何额外字段。

**输出 JSON 结构:**
```json
{
  "is_restaurant": true,
  "name": "string",
  "cuisine_type": ["string"],
  "price_range": "string",
  "tags": ["string"],
  "rating": float,
  "user_ratings_total": integer
}
```

**字段提取规则:**
- `is_restaurant`: (boolean) 必须为 `true`。
- `name`: (string) 直接使用地点名称。
- `cuisine_type`: (Array of Strings) 基于地点名称 (`name`) 和类型 (`types`) 推断出核心菜系。例如，"海底捞火锅" 应该提取出 "火锅" 和 "川菜"。 "Starbucks" 应该提取出 "咖啡"。力求精准和简洁，最多3个。
- `price_range`: (string) 将 Google 的 `price_level` (0-4的数字) 映射为 `$` 符号。0 或 1 -> "$", 2 -> "$$", 3 -> "$$$", 4 -> "$$$$". 如果没有 `price_level`，则留空 ""。
- `tags`: (Array of Strings) 根据 `types`, `name` 和用户评论摘要(`reviews`)推断出描述性标签。例如："适合聚餐", "环境好", "外卖", "连锁品牌"等。选择最相关的3-5个标签。
- `rating`: (float) 直接使用评分 `rating`。
- `user_ratings_total`: (integer)直接使用 `user_ratings_total`。
"""

    async def _structure_with_llm(self, place_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用 LLM 清洗和结构化单个地点的数据。
        """
        system_prompt = self._construct_llm_prompt_for_structuring()
        
        # 为了减少token消耗并聚焦关键信息，我们只传递部分关键字段给LLM
        essential_details = {
            "name": place_details.get("name"),
            "types": place_details.get("types"),
            "rating": place_details.get("rating"),
            "user_ratings_total": place_details.get("user_ratings_total"),
            "price_level": place_details.get("price_level"),
            "reviews": place_details.get("reviews", [])[:2], # 只取前两个评论作为参考
        }
        
        try:
            completion = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请处理这个地点的数据: {json.dumps(essential_details, ensure_ascii=False)}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            response_data = json.loads(completion.choices[0].message.content)
            return response_data
        except Exception as e:
            print(f"❌ LLM 处理地点 '{place_details.get('name')}' 时出错: {e}")
            return {"is_restaurant": False}

    async def _process_place(self, place_id: str) -> Dict:
        """
        获取单个地点的详细信息，通过LLM处理，并准备存入数据库。
        """
        print(f"   - 正在处理 Place ID: {place_id}")
        
        # Google API 调用可能因为网络问题失败，需要try-except
        try:
            place_details = self.gmaps.place(
                place_id,
                fields=[
                    'place_id', 'name', 'formatted_address', 'geometry', 'type',
                    'rating', 'user_ratings_total', 'price_level', 'opening_hours',
                    'website', 'photo', 'url', 'reviews'  # <--- 修改: 'photos' -> 'photo'
                ]
            )['result']
        except Exception as e:
            print(f"   - ❌ 调用 Google Place Details API 失败 (Place ID: {place_id}): {e}")
            return {"status": "api_error"}
        
        structured_data = await self._structure_with_llm(place_details)

        if not structured_data.get("is_restaurant"):
            print(f"   - ⏭️  跳过非餐厅地点: {place_details.get('name')}")
            return {"status": "skipped"}

        # --- 组合最终的数据库文档 ---
        final_doc = {
            "google_place_id": place_details['place_id'],
            "name": structured_data.get('name', place_details['name']),
            "address": place_details.get('formatted_address'),
            "location": {
                "type": "Point",
                "coordinates": [
                    place_details['geometry']['location']['lng'],
                    place_details['geometry']['location']['lat']
                ]
            },
            "rating": structured_data.get('rating'),
            "user_ratings_total": structured_data.get('user_ratings_total'),
            "price_range": structured_data.get('price_range'),
            "cuisine_type": structured_data.get('cuisine_type', []),
            "tags": structured_data.get('tags', []),
            "google_maps_url": place_details.get('url'),
            "opening_hours": {},
        }

        # <--- 修改: 'photos' -> 'photo'
        if place_details.get('photo'):
            photo_ref = place_details['photo'][0]['photo_reference']
            final_doc['image_url'] = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_ref}&key={self.gmaps_key}"

        # 处理营业时间 (保持不变)
        if place_details.get('opening_hours', {}).get('weekday_text'):
            hours_map = {}
            weekday_mapping = {"星期一": "monday", "星期二": "tuesday", "星期三": "wednesday", 
                               "星期四": "thursday", "星期五": "friday", "星期六": "saturday", "星期日": "sunday"}
            
            # 兼容英文环境
            weekday_mapping.update({"Monday": "monday", "Tuesday": "tuesday", "Wednesday": "wednesday",
                                    "Thursday": "thursday", "Friday": "friday", "Saturday": "saturday", "Sunday": "sunday"})

            for line in place_details['opening_hours']['weekday_text']:
                day, hours = line.split(': ', 1)
                day_en = weekday_mapping.get(day)
                if day_en:
                    # 将本地化文本标准化
                    hours_normalized = hours.replace('24 小时营业', '00:00-24:00').replace('休息', 'Closed').replace('Open 24 hours', '00:00-24:00')
                    hours_map[day_en] = hours_normalized.strip()
            final_doc['opening_hours'] = hours_map
        
        try:
            await self.db.add_or_update_restaurant(final_doc)
            print(f"   - ✅ 成功添加/更新餐厅: {final_doc['name']}")
            return {"status": "success", "name": final_doc['name']}
        except Exception as e:
            print(f"   - ❌ 存入数据库失败: {final_doc['name']}, 错误: {e}")
            return {"status": "db_error"}

    async def crawl_area(self, latitude: float, longitude: float, radius_meters: int, max_results: int = 60) -> Dict:
        """
        爬取指定区域内的餐厅，支持分页，并跳过数据库中已存在的地点。
        """
        print(f"\n🚀 开始爬取区域: lat={latitude}, lon={longitude}, radius={radius_meters}m")
        print(f"   - 最大结果数限制: {max_results}")
        
        # 1. (保持不变) 分页获取所有潜在的 Place ID
        all_place_ids = set()
        next_page_token = None
        page_num = 1
        
        while len(all_place_ids) < max_results:
            print(f"   - 正在请求第 {page_num} 页...")
            try:
                if next_page_token is None:
                    places_result = self.gmaps.places_nearby(location=(latitude, longitude), radius=radius_meters, language='zh-CN')
                else:
                    await asyncio.sleep(2) 
                    places_result = self.gmaps.places_nearby(page_token=next_page_token)
            except Exception as e:
                print(f"   - ❌ 请求 Google Nearby Search API 失败: {e}")
                break

            current_page_ids = {place['place_id'] for place in places_result.get('results', [])}
            all_place_ids.update(current_page_ids)
            print(f"     - 本页找到 {len(current_page_ids)} 个地点，总计 {len(all_place_ids)} 个。")

            next_page_token = places_result.get('next_page_token')
            if not next_page_token:
                print("   - ✅ 没有更多页面了。")
                break
            page_num += 1

        print(f"🔎 搜索结束，共发现 {len(all_place_ids)} 个不重复的潜在地点。")

        # --- 核心改动：检查数据库中已存在的地点 ---
        if not all_place_ids:
             # 如果一个地点都没找到，直接返回
            return {
                "total_found": 0, "already_exists": 0, "to_process": 0,
                "restaurants_added_or_updated": 0, "non_restaurants_skipped": 0, "errors": 0,
            }

        place_ids_list = list(all_place_ids)
        print(f"   - 正在检查数据库中已存在的 {len(place_ids_list)} 个地点...")
        
        # 2. 批量查询数据库
        existing_places_cursor = self.db.collection.find(
            {'google_place_id': {'$in': place_ids_list}},
            {'_id': 0, 'google_place_id': 1} # 只返回 place_id 字段以节省带宽
        )
        
        # 将已存在的 place_id 存入一个集合以便快速查找
        existing_place_ids = {doc['google_place_id'] async for doc in existing_places_cursor}
        
        # 3. 计算出需要新处理的 place_id
        place_ids_to_process = [pid for pid in place_ids_list if pid not in existing_place_ids]
        
        num_existing = len(existing_place_ids)
        num_to_process = len(place_ids_to_process)
        
        print(f"   - 检查完成: {num_existing} 个地点已存在将被跳过，{num_to_process} 个新地点需要处理。")
        
        if not place_ids_to_process:
            print("🏁 本次没有需要处理的新地点，爬取提前结束。")
            # 即使没有新地点，也要返回一个完整的统计摘要
            return {
                "total_found": len(all_place_ids),
                "already_exists": num_existing,
                "to_process": 0,
                "restaurants_added_or_updated": 0,
                "non_restaurants_skipped": 0,
                "errors": 0,
            }

        # 4. (保持不变) 并发处理需要处理的新地点
        tasks = [self._process_place(pid) for pid in place_ids_to_process]
        results = await asyncio.gather(*tasks)
        
        # 5. 更新统计结果
        success_count = sum(1 for r in results if r.get('status') == 'success')
        skipped_count = sum(1 for r in results if r.get('status') == 'skipped')
        error_count = len(results) - success_count - skipped_count
        
        summary = {
            "total_found": len(all_place_ids),
            "already_exists": num_existing, # 新增统计项
            "to_process": num_to_process,   # 新增统计项
            "restaurants_added_or_updated": success_count,
            "non_restaurants_skipped": skipped_count,
            "errors": error_count,
        }
        print(f"🏁 爬取完成: {summary}")
        return summary

# ================== 测试代码 ==================
async def main_test():
    crawler = GoogleMapsCrawler()
    # 示例：以广州大学城为中心，爬取2公里范围
    lat, lon = 23.045, 113.398
    radius = 2000
    await crawler.crawl_area(latitude=lat, longitude=lon, radius_meters=radius)
    crawler.db.close() # 关闭数据库连接

if __name__ == '__main__':
    asyncio.run(main_test())
