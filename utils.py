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
        color=0x5865F2
    )
    
    # ... (find, nearby 等命令的说明保持不变) ...
    embed.add_field(
        name="🍴 主要命令",
        value=(
            "**`/find [query]`** - 用自然语言找餐厅。\n"
            "*示例: `/find 明天想吃便宜的川菜`*\n\n"
            "**`/nearby [location] [query]`** - 查找某地附近的餐厅。\n"
            "*示例: `/nearby 学校 找个评分高的`*\n\n"
        ),
        inline=False
    )
    embed.add_field(
        name="📍 个人位置",
        value=(
            "**`/location set [address]`** - 设置你的默认位置。\n"
            "**`/location show`** - 查看你的默认位置。\n"
            "**`/location clear`** - 清除你的默认位置。"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛠️ 管理员命令",
        value=(
            "**`/admin crawl`** - 爬取餐厅数据 (支持 `force_update` 等高级选项)。\n"
            "**`/admin add [id]`** - 添加或强制更新单个餐厅。\n"
            "**`/admin delete [id]`** - 删除餐厅 (别名: `/admin remove`)。\n\n"
            "**`/admin alias add`** - 添加位置别名（黑话）。\n"
            "  • **通过地址**: `/admin alias add alias:学校 address:广州大学城`\n"
            "  • **通过坐标**: `/admin alias add alias:家 latitude:23.123 longitude:113.456 address:我的家`\n\n" # <--- 更新示例
            "**`/admin alias list`** - 列出所有位置别名。\n"
            "**`/admin alias delete [alias]`** - 删除一个位置别名。"
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
    
    embed.add_field(name="📄 爬取页数", value=str(summary.get('pages_crawled', 0)), inline=True)
    embed.add_field(name="🔍 发现地点总数", value=str(summary.get('total_found', 0)), inline=True)
    embed.add_field(name="🗃️ 已存在并跳过", value=str(summary.get('already_exists', 0)), inline=True)
    
    embed.add_field(name="🆕 需要处理", value=str(summary.get('to_process', 0)), inline=True)
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

def create_location_info_embed(location: Dict) -> discord.Embed:
    """创建位置信息的嵌入消息"""
    coords = location['coordinates']
    embed = discord.Embed(
        title="📍 你的默认位置",
        color=discord.Color.blue()
    )
    
    if location.get('address'):
        embed.add_field(name="地址", value=location['address'], inline=False)
    
    embed.add_field(
        name="坐标", 
        value=f"`{coords['latitude']:.6f}, {coords['longitude']:.6f}`",
        inline=True
    )
    
    if location.get('radius'):
        embed.add_field(name="默认搜索半径", value=f"{location['radius']}米", inline=True)
    
    return embed
