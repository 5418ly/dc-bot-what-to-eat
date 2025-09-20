import discord
from typing import Dict, List
from datetime import datetime
import pytz

def parse_command_args(content: str) -> Dict:
    """
    解析命令参数
    示例: 吃啥 菜系=川菜,粤菜 价格=$$ 评分=4.5 附近=1000
    """
    parts = content.split()
    if len(parts) <= 1:
        return {}
    
    filters = {}
    for part in parts[1:]:
        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip().lower()
            
            # 映射常见的中文参数到英文
            mapping = {
                '菜系': 'cuisine_type',
                '类型': 'cuisine_type',
                '价格': 'price_range',
                '评分': 'min_rating',
                '标签': 'tags',
                '关键词': 'keyword',
                '附近': 'max_distance',
                '距离': 'max_distance'
            }
            
            if key in mapping:
                filters[mapping[key]] = value
            else:
                filters[key] = value
    
    return filters

def create_restaurant_embed(restaurant: Dict) -> discord.Embed:
    """创建餐厅信息的Discord嵌入消息"""
    # 设置嵌入颜色（根据价格范围）
    price_colors = {
        '$': 0x2ecc71,      # 绿色 - 便宜
        '$$': 0x3498db,     # 蓝色 - 中等
        '$$$': 0xf39c12,    # 橙色 - 较贵
        '$$$$': 0xe74c3c    # 红色 - 昂贵
    }
    color = price_colors.get(restaurant.get('price_range', '$$'), 0x95a5a6)
    
    embed = discord.Embed(
        title=restaurant['name'],
        description=f"📍 {restaurant.get('address', '未知地址')}",
        color=color
    )
    
    # 添加菜系信息
    if restaurant.get('cuisine_type'):
        cuisines = ', '.join(restaurant['cuisine_type'])
        embed.add_field(name="🍽️ 菜系", value=cuisines, inline=True)
    
    # 添加价格范围
    if restaurant.get('price_range'):
        embed.add_field(name="💰 价格", value=restaurant['price_range'], inline=True)
    
    # 添加评分
    if restaurant.get('rating'):
        rating_stars = '⭐' * int(restaurant['rating'])
        embed.add_field(name="⭐ 评分", value=f"{restaurant['rating']}/5.0 {rating_stars}", inline=True)
    
    # 添加营业时间（当天）
    if restaurant.get('opening_hours'):
        tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz)
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        today = weekdays[now.weekday()]
        
        if today in restaurant['opening_hours']:
            hours = restaurant['opening_hours'][today]
            embed.add_field(name="⏰ 今日营业时间", value=hours, inline=True)
    
    # 添加标签
    if restaurant.get('tags'):
        tags = ', '.join(restaurant['tags'])
        embed.add_field(name="🏷️ 标签", value=tags, inline=False)
    
    # 添加Google Maps链接
    if restaurant.get('google_maps_url'):
        embed.add_field(
            name="🗺️ 地图", 
            value=f"[查看地图]({restaurant['google_maps_url']})", 
            inline=False
        )
    
    # 设置图片
    if restaurant.get('image_url'):
        embed.set_image(url=restaurant['image_url'])
    
    # 设置页脚
    embed.set_footer(text="🍴 祝您用餐愉快！")
    
    return embed

def create_help_embed() -> discord.Embed:
    """创建帮助信息的嵌入消息"""
    embed = discord.Embed(
        title="🍽️ 餐厅推荐机器人使用指南",
        description="让我来帮你决定今天吃什么！",
        color=0x3498db
    )
    
    embed.add_field(
        name="📝 基本用法",
        value="`吃啥` - 随机推荐3家正在营业的餐厅",
        inline=False
    )
    
    embed.add_field(
        name="🔍 高级筛选",
        value=(
            "`吃啥 菜系=川菜`\n"
            "`吃啥 价格=$$`\n"
            "`吃啥 评分=4.5`\n"
            "`吃啥 标签=适合聚餐`\n"
            "`吃啥 关键词=火锅`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎯 组合筛选",
        value="`吃啥 菜系=川菜,粤菜 价格=$-$$ 评分=4.0`",
        inline=False
    )
    
    embed.add_field(
        name="💰 价格说明",
        value=(
            "$ = 人均30元以下\n"
            "$$ = 人均30-60元\n"
            "$$$ = 人均60-100元\n"
            "$$$$ = 人均100元以上"
        ),
        inline=False
    )
    
    embed.set_footer(text="提示: 默认只显示正在营业的餐厅")
    
    return embed

def create_error_embed(message: str) -> discord.Embed:
    """创建错误信息的嵌入消息"""
    embed = discord.Embed(
        title="❌ 出错了",
        description=message,
        color=0xe74c3c
    )
    return embed

def create_no_results_embed() -> discord.Embed:
    """创建无结果的嵌入消息"""
    embed = discord.Embed(
        title="😔 没有找到餐厅",
        description="根据您的筛选条件，没有找到符合要求或正在营业的餐厅。\n请尝试放宽筛选条件。",
        color=0xf39c12
    )
    return embed