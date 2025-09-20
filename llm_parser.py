# llm_parser.py

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import pytz
from dotenv import load_dotenv
# 核心改动：导入异步客户端 AsyncOpenAI
from openai import AsyncOpenAI, APIError

load_dotenv()

class LLMParser:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        self.model = os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")

        if not api_key:
            raise ValueError("未在 .env 文件中找到 OPENAI_API_KEY")

        try:
            # 核心改动：实例化异步客户端
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            print(f"✅ LLM 解析器已初始化，使用模型: {self.model}")
        except Exception as e:
            print(f"❌ 初始化 OpenAI 客户端时出错: {e}")
            raise

    # _construct_prompt 方法保持不变
    def _construct_prompt(
        self,
        user_input: str,
        available_cuisines: List[str],
        available_tags: List[str]
    ) -> str:
        cuisines_str = ", ".join(f'"{c}"' for c in available_cuisines)
        tags_str = ", ".join(f'"{t}"' for t in available_tags)

        system_prompt = f"""
你是一个智能餐厅推荐助手机器人。你的任务是将用户的自然语言查询精确地解析成一个结构化的JSON对象。
你必须严格遵守以下规则：
1.  你的输出只能是一个JSON对象，不能包含任何其他文字、解释或代码块标记。
2.  根据用户意图，从提供的“可用菜系列表”和“可用标签列表”中选择最匹配的项。如果用户提到的菜系或标签不在列表中，将其归入 "keywords" 字段。
3.  解析用户的价格意图，并将其映射到 `price_range` 字段。价格范围是 `"$", "$$", "$$$", "$$$$"` 的列表。例如，“便宜的”可能对应 `["$"]`，“中等价位”可能对应 `["$$"]`，“不要太贵的”可能对应 `["$", "$$"]`。
4.  解析用户对时间的描述（例如“明天早上”，“后天晚上”）。

**可用信息参考:**
- 可用菜系列表: [{cuisines_str}]
- 可用标签列表: [{tags_str}]
- 价格符号: "$"(便宜), "$$"(中等), "$$$"(较贵), "$$$$"(昂贵)

**JSON输出结构:**
你必须输出一个包含 "filters" 和 "time_info" 两个键的JSON对象。
```json
{{
  "filters": {{
    "cuisine_type": ["string"],
    "price_range": ["string"],
    "min_rating": float,
    "keywords": ["string"]
  }},
  "time_info": {{
    "day_offset": integer,
    "time_of_day": "string"
  }}
}}
```

**字段解释:**
- `filters.cuisine_type`: 菜系列表。必须从“可用菜系列表”中选取。
- `filters.price_range`: 价格范围列表。例如 `["$", "$$"]`。
- `filters.min_rating`: 最低评分，浮点数。
- `filters.keywords`: 无法归类到菜系或标签的关键词列表。
- `time_info.day_offset`: 相对今天的天数偏移。0代表今天，1代表明天，2代表后天，-1代表昨天。默认为0。
- `time_info.time_of_day`: "morning" (早), "noon" (中), "afternoon" (下), "evening" (晚), "night" (夜)。如果未指定，默认为 "evening"。

**示例:**
- 用户输入: "明天晚上想吃便宜点的川菜，适合聚餐"
- JSON输出:
```json
{{
  "filters": {{
    "cuisine_type": ["川菜"],
    "price_range": ["$"],
    "keywords": ["适合聚餐"]
  }},
  "time_info": {{
    "day_offset": 1,
    "time_of_day": "evening"
  }}
}}
```
"""
        return system_prompt

    # _parse_llm_time_to_datetime 方法保持不变
    def _parse_llm_time_to_datetime(self, time_info: Dict, timezone_str: str = 'Asia/Shanghai') -> datetime:
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)

        day_offset = time_info.get("day_offset", 0)
        target_date = now + timedelta(days=day_offset)

        time_of_day = time_info.get("time_of_day", "evening")
        time_map = {
            "morning": 9, "noon": 12, "afternoon": 15,
            "evening": 19, "night": 22,
        }
        hour = time_map.get(time_of_day.lower(), 19)

        return target_date.replace(hour=hour, minute=0, second=0, microsecond=0)

    # parse_user_request 方法保持不变，因为 await 现在可以正确工作了
    async def parse_user_request(
        self, user_input: str, available_cuisines: List[str],
        available_tags: List[str]
    ) -> Tuple[Dict, Optional[datetime]]:
        system_prompt = self._construct_prompt(user_input, available_cuisines, available_tags)
        response_content = "" # 初始化, 以防 API 调用失败时引用
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请解析以下用户查询：'{user_input}'"}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            response_content = completion.choices[0].message.content
            parsed_data = json.loads(response_content)

            filters = parsed_data.get("filters", {})
            time_info = parsed_data.get("time_info")
            
            cleaned_filters = {k: v for k, v in filters.items() if v}

            query_dt = self._parse_llm_time_to_datetime(time_info) if time_info else datetime.now(pytz.timezone('Asia/Shanghai'))

            return cleaned_filters, query_dt

        except APIError as e:
            print(f"❌ OpenAI API 调用失败: {e}")
            return {}, None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ 解析LLM返回的JSON时失败: {e}")
            print(f"   - 原始返回内容: {response_content}")
            return {}, None
        except Exception as e:
            print(f"❌ 解析用户请求时发生未知错误: {e}")
            return {}, None

# 测试代码保持不变
async def main_test():
    print("--- 正在测试 LLM 解析器 ---")
    parser = LLMParser()
    mock_cuisines = ["川菜", "粤菜", "湘菜", "日料", "火锅", "烧烤", "西餐", "快餐"]
    mock_tags = ["适合聚餐", "环境好", "有包间", "连锁品牌", "情侣约会"]
    test_queries = [
        "明天晚上想吃便宜点的川菜，适合聚餐",
        "随便来点",
        "后天中午有没有评分高点的日料或者西餐",
        "找个带包间的火锅店",
        "有啥好吃的烧烤，不要太贵"
    ]
    for query in test_queries:
        print(f"\n[用户输入]: {query}")
        filters, dt = await parser.parse_user_request(query, mock_cuisines, mock_tags)
        print(f"[解析结果 - Filters]: {filters}")
        print(f"[解析结果 - Time]: {dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '未指定'}")
        print("-" * 20)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main_test())