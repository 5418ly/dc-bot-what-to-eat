# utils.py

import discord
from typing import Dict, List
from datetime import datetime
import pytz

def create_restaurant_embed(restaurant: Dict) -> discord.Embed:
    """为单个餐厅数据创建 Discord 嵌入式消息"""
    price_colors = {
        '$': 0x2ecc71,
        '$$': 0x3498db,
        '$$$': 0xf39c12,
        '$$$$': 0xe74c3c
    }
    color = price_colors.get(restaurant.get('price_range', '$$'), 0x95a5a6)
    
    embed = discord.Embed(
        title=restaurant.get('name', '未知餐厅'),
        description=f"📍 {restaurant.get('address', '未知地址')}",
        color=color
    )
    
    if restaurant.get('google_maps_url'):
        embed.url = restaurant['google_maps_url']

    if restaurant.get('cuisine_type'):
        embed.add_field(name="🍽️ 菜系", value=', '.join(restaurant['cuisine_type']), inline=True)
    
    if restaurant.get('price_range'):
        embed.add_field(name="💰 价格", value=restaurant['price_range'], inline=True)
    
    if restaurant.get('rating'):
        rating_text = f"{restaurant['rating']}/5.0"
        if restaurant.get('user_ratings_total'):
            rating_text += f" ({restaurant['user_ratings_total']}条评价)"
        embed.add_field(name="⭐ 评分", value=rating_text, inline=True)
        
    if restaurant.get('tags'):
        embed.add_field(name="🏷️ 标签", value=', '.join(restaurant['tags']), inline=False)
    
    if restaurant.get('image_url'):
        embed.set_image(url=restaurant['image_url'])
        
    embed.set_footer(text=f"Google Place ID: {restaurant.get('google_place_id', 'N/A')}")
    
    return embed

def create_help_embed() -> discord.Embed:
    """创建帮助信息的嵌入消息"""
    embed = discord.Embed(
        title="🤖 智能美食推荐官 - 使用指南",
        description="我能听懂你的话，帮你找到想吃的！所有命令都使用斜杠 `/` 开始。",
        color=0x5865F2 # Discord Blue
    )
    
    embed.add_field(
        name=" основная команда: `/find` (或 `/吃啥`)",
        value=(
            "用自然语言告诉我你想吃什么，我会尽力理解并为你推荐。\n"
            "**你可以这样说:**\n"
            "• `/find 明天中午想吃点便宜的川菜`\n"
            "• `/find 附近有没有评分高的日料`\n"
            "• `/find 找个适合情侣约会的西餐厅`\n"
            "• `/find 来点烧烤当夜宵`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛠️ 管理员命令",
        value=(
            "以下命令仅限服务器管理员使用：\n"
            "• `/crawl [纬度] [经度] [半径]` - 从指定地点爬取餐厅数据。\n"
            "  *示例: `/crawl 23.045 113.398 2000`*\n"
            "• `/add [google_place_id]` - 手动添加或更新一个餐厅。\n"
            "• `/delete [google_place_id]` - 从数据库中删除一个餐厅。"
        ),
        inline=False
    )
    
    embed.set_footer(text="我由 LLM 驱动，正在不断学习中！")
    return embed

def create_crawler_summary_embed(summary: Dict, location: Dict) -> discord.Embed:
    """为爬虫结果创建总结嵌入消息"""
    embed = discord.Embed(
        title="🗺️ Google Maps 数据爬取完成",
        description=f"中心点: `lat: {location['lat']}, lon: {location['lon']}`\n半径: `{location['radius']}米`",
        color=0x2ecc71
    )
    # 分行展示，更清晰
    embed.add_field(name="🔍 发现地点总数", value=str(summary.get('total_found', 0)), inline=True)
    embed.add_field(name="🗃️ 已存在并跳过", value=str(summary.get('already_exists', 0)), inline=True)
    embed.add_field(name=" xử lý mới", value=str(summary.get('to_process', 0)), inline=True)
    
    embed.add_field(name="✅ 成功添加/更新", value=str(summary.get('restaurants_added_or_updated', 0)), inline=True)
    embed.add_field(name="⏭️ 跳过的非餐厅", value=str(summary.get('non_restaurants_skipped', 0)), inline=True)
    embed.add_field(name="❌ 发生错误数", value=str(summary.get('errors', 0)), inline=True)
    
    return embed


def create_error_embed(message: str, title: str = "❌ 糟糕，出错了") -> discord.Embed:
    """创建错误信息的嵌入消息"""
    return discord.Embed(title=title, description=message, color=0xe74c3c)

def create_no_results_embed() -> discord.Embed:
    """创建未找到结果的嵌入消息"""
    return discord.Embed(
        title="🤔 换个条件试试？",
        description="根据你的要求，我没有找到正在营业的餐厅。\n可以尝试放宽筛选条件，或者换个时间再问我哦。",
        color=0xf1c40f
    )

def create_success_embed(message: str, title: str = "✅ 操作成功") -> discord.Embed:
    """创建成功操作的嵌入消息"""
    return discord.Embed(title=title, description=message, color=0x2ecc71)