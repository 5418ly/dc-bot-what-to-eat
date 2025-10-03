# bot.py
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import RestaurantDB
from llm_parser import LLMParser
from crawler import GoogleMapsCrawler
from user_preferences import UserPreferencesDB
from utils import (
    create_restaurant_embed,
    create_help_embed,
    create_error_embed,
    create_no_results_embed,
    create_success_embed,
    create_crawler_summary_embed,
    create_location_info_embed
)


intents = discord.Intents.default()
intents.message_content = False
bot = commands.Bot(command_prefix="!", intents=intents)
db: RestaurantDB|None=None; llm_parser:LLMParser|None=None; crawler:GoogleMapsCrawler|None=None; user_prefs_db:UserPreferencesDB|None=None

@bot.event
async def on_ready():
    """当机器人成功连接到 Discord 时执行"""
    global db, llm_parser, crawler, user_prefs_db
    print(f'✅ {bot.user} 已成功登录并上线!')
    
    try:
        db = RestaurantDB()
        llm_parser = LLMParser()
        crawler = GoogleMapsCrawler()
        user_prefs_db = UserPreferencesDB()
        
        await db.connect_and_setup()
        await user_prefs_db.connect_and_setup()
        
        print("✅ 所有服务模块初始化成功。")
        synced = await bot.tree.sync()
        print(f"🔄 已同步 {len(synced)} 条斜杠命令。")
    except Exception as e:
        print(f"❌ 初始化服务或同步命令时发生严重错误: {e}")
        return
    
    await bot.change_presence(activity=discord.Game(name="输入 /find 找美食"))

@bot.tree.command(name="find", description="通过自然语言描述来查找餐厅")
@app_commands.describe(query="你想吃什么？例如：'明天中午的便宜川菜' 或 '附近评分高的日料'")
async def find_restaurant(interaction: discord.Interaction, query: str):
    if not (db and llm_parser):
        await interaction.response.send_message(embed=create_error_embed("机器人服务尚未准备就绪，请稍后再试。"), ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        available_cuisines = await db.get_all_cuisine_types()
        available_tags = await db.get_all_tags()
        
        filters, query_time = await llm_parser.parse_user_request(query, available_cuisines, available_tags)
        
        if not filters and not query_time:
             await interaction.followup.send(embed=create_error_embed("抱歉，我没太理解你的意思，可以换个说法吗？","🤔 理解失败"))
             return
        
        restaurants = await db.find_restaurants(
            filters=filters,
            query_time=query_time,
            count=3
        )
        
        if not restaurants:
            await interaction.followup.send(embed=create_no_results_embed())
        else:
            embeds_to_send = []
            intro_embed = discord.Embed(
                title=f"🍴 为你找到 {len(restaurants)} 家符合 '{query}' 的餐厅",
                color=discord.Color.green()
            )
            embeds_to_send.append(intro_embed)
            
            for restaurant in restaurants:
                embeds_to_send.append(create_restaurant_embed(restaurant))
            
            await interaction.followup.send(embeds=embeds_to_send)
    except Exception as e:
        print(f"❌ 在执行 /find 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"处理你的请求时发生未知错误。\n`{e}`"))

@bot.tree.command(name="nearby", description="查找指定地点附近的餐厅")
@app_commands.describe(
    location="地点描述，可以是地址、别名（如'学校'）或坐标",
    query="你想吃什么？（可选）"
)
async def find_nearby(interaction: discord.Interaction, location: str, query: str = ""):
    if not (db and llm_parser and crawler and user_prefs_db):
        await interaction.response.send_message(
            embed=create_error_embed("机器人服务尚未准备就绪，请稍后再试。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # 1. 解析位置
        lat, lng = None, None
        location_desc = location
        
        # 先检查是否是别名（黑话）
        guild_id = str(interaction.guild_id) if interaction.guild else None
        alias_data = await user_prefs_db.get_location_alias(location, guild_id)
        
        if alias_data:
            lat = alias_data['coordinates']['latitude']
            lng = alias_data['coordinates']['longitude']
            location_desc = alias_data.get('address') or f"别名: {location}"
            print(f"✅ 使用位置别名: {location} -> ({lat}, {lng})")
        else:
            # 尝试地理编码
            lat, lng = crawler.get_coordinates_from_address(location)
            if not lat or not lng:
                await interaction.followup.send(
                    embed=create_error_embed(
                        f"无法识别位置 '{location}'。\n"
                        "请尝试:\n"
                        "• 使用更详细的地址\n"
                        "• 使用 `/location set` 设置默认位置\n"
                        "• 让管理员用 `/admin alias add` 添加位置别名"
                    )
                )
                return
        
        # 2. 解析餐厅查询条件
        available_cuisines = await db.get_all_cuisine_types()
        available_tags = await db.get_all_tags()
        
        filters, query_time = await llm_parser.parse_user_request(
            query if query else "附近的餐厅", 
            available_cuisines, 
            available_tags
        )
        
        # 3. 添加位置过滤（在数据库中查找该位置附近的餐厅）
        restaurants = await db.find_restaurants_near_location(
            latitude=lat,
            longitude=lng,
            radius_meters=2000,  # 默认2公里
            filters=filters,
            query_time=query_time,
            count=3
        )
        
        # 4. 发送结果
        if not restaurants:
            await interaction.followup.send(
                embed=create_no_results_embed()
            )
        else:
            embeds_to_send = []
            intro_embed = discord.Embed(
                title=f"🍴 在 {location_desc} 附近找到 {len(restaurants)} 家餐厅",
                description=f"坐标: `{lat:.4f}, {lng:.4f}`",
                color=discord.Color.green()
            )
            if query:
                intro_embed.description += f"\n查询: {query}"
            embeds_to_send.append(intro_embed)
            
            for restaurant in restaurants:
                embeds_to_send.append(create_restaurant_embed(restaurant))
            
            await interaction.followup.send(embeds=embeds_to_send)
            
    except Exception as e:
        print(f"❌ 在执行 /nearby 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"处理你的请求时发生未知错误。\n`{e}`"))

@bot.tree.command(name="吃啥", description="通过自然语言描述来查找餐厅（/find 的别名）")
@app_commands.describe(query="你想吃什么？例如：'明天中午的便宜川菜' 或 '附近评分高的日料'")
async def find_restaurant_alias(interaction: discord.Interaction, query: str):
    await find_restaurant(interaction, query)

@bot.tree.command(name="help", description="显示机器人使用指南")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(embed=create_help_embed(), ephemeral=True)

# ===== 用户位置偏好命令组 =====
location_group = app_commands.Group(name="location", description="管理你的位置偏好")

@location_group.command(name="set", description="设置你的默认查询位置")
@app_commands.describe(location="地址或地点名称")
async def set_location(interaction: discord.Interaction, location: str):
    if not (crawler and user_prefs_db):
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        lat, lng = crawler.get_coordinates_from_address(location)
        if not lat or not lng:
            await interaction.followup.send(
                embed=create_error_embed(f"无法识别地址 '{location}'，请使用更详细的地址。")
            )
            return
        
        user_id = str(interaction.user.id)
        await user_prefs_db.set_default_location(
            user_id=user_id,
            latitude=lat,
            longitude=lng,
            address=location
        )
        
        await interaction.followup.send(
            embed=create_success_embed(
                f"✅ 已设置你的默认位置为:\n**{location}**\n坐标: `{lat:.4f}, {lng:.4f}`"
            )
        )
    except Exception as e:
        print(f"❌ 设置默认位置时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"设置失败: {e}"))

@location_group.command(name="show", description="查看你的默认位置")
async def show_location(interaction: discord.Interaction):
    if not user_prefs_db:
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        user_id = str(interaction.user.id)
        location = await user_prefs_db.get_default_location(user_id)
        
        if not location:
            await interaction.followup.send(
                embed=create_error_embed(
                    "你还没有设置默认位置。\n使用 `/location set` 来设置。",
                    "ℹ️ 未设置"
                )
            )
        else:
            coords = location['coordinates']
            embed = create_location_info_embed(location)
            await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"❌ 查看默认位置时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"查询失败: {e}"))

@location_group.command(name="clear", description="清除你的默认位置")
async def clear_location(interaction: discord.Interaction):
    if not user_prefs_db:
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        user_id = str(interaction.user.id)
        count = await user_prefs_db.clear_default_location(user_id)
        
        if count > 0:
            await interaction.followup.send(
                embed=create_success_embed("✅ 已清除你的默认位置。")
            )
        else:
            await interaction.followup.send(
                embed=create_error_embed("你本来就没有设置默认位置。", "ℹ️ 提示")
            )
    except Exception as e:
        print(f"❌ 清除默认位置时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"操作失败: {e}"))

bot.tree.add_command(location_group)

# ===== 管理员命令组 =====
admin_group = app_commands.Group(name="admin", description="管理员专用命令")

@admin_group.command(name="crawl", description="从指定经纬度和半径爬取 Google Maps 餐厅数据")
@app_commands.describe(
    latitude="中心纬度", 
    longitude="中心经度", 
    radius="搜索半径（米）",
    max_results="最大地点数 (默认60, 0表示不限制)",
    start_page="起始页码（默认1）",
    end_page="结束页码（默认-1表示到最后一页）"
)
async def crawl_command(
    interaction: discord.Interaction, 
    latitude: float, 
    longitude: float, 
    radius: int, 
    max_results: int = 60,
    start_page: int = 1,
    end_page: int = -1,
    force_update: bool = False # <--- 新增参数
):
    # ... 权限和参数验证 ...
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(embed=create_error_embed("此命令仅限管理员使用。", "⛔ 权限不足"), ephemeral=True); return
    if not crawler:
        await interaction.response.send_message(embed=create_error_embed("爬虫服务尚未准备就绪。"), ephemeral=True); return
    if radius > 50000:
        await interaction.response.send_message(embed=create_error_embed("搜索半径不能超过 50,000 米。"), ephemeral=True); return
    if start_page < 1 or (end_page != -1 and end_page < start_page) or max_results < 0:
        await interaction.response.send_message(embed=create_error_embed("参数错误，请检查页码或最大结果数。"), ephemeral=True); return

    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        # 将 force_update 传递给爬虫
        summary = await crawler.crawl_area(
            latitude=latitude, 
            longitude=longitude, 
            radius_meters=radius, 
            max_results=max_results,
            start_page=start_page,
            end_page=end_page,
            force_update=force_update # <--- 传递参数
        )
        
        location_info = {"lat": latitude, "lon": longitude, "radius": radius}
        summary_embed = create_crawler_summary_embed(summary, location_info)
        
        # 在摘要中显示参数信息
        params_info = f"\n**爬取参数:**\n"
        params_info += f"• 最大结果数: `{'不限制' if max_results == 0 else max_results}`\n"
        params_info += f"• 页码范围: `{start_page}` 到 `{'最后' if end_page == -1 else end_page}`\n"
        params_info += f"• 强制更新: `{'是' if force_update else '否'}`" # <--- 显示新参数状态
        summary_embed.description += params_info
        
        await interaction.followup.send(embed=summary_embed)
    except Exception as e:
        print(f"❌ 在执行 /admin crawl 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"爬取过程中发生错误: {e}"))

@admin_group.command(name="add", description="通过 Google Plus Code 或 Place ID 添加餐厅")
@app_commands.describe(identifier="餐厅的 Google Plus Code (如 '3V7V+2M 广州市') 或 Place ID")
async def add_command(interaction: discord.Interaction, identifier: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=create_error_embed("此命令仅限管理员使用。", "⛔ 权限不足"),
            ephemeral=True
        )
        return
    
    if not (crawler and db):
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
        
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    place_id_to_process = None
    
    if identifier.strip().startswith("ChIJ"):
        print("ℹ️ 输入被识别为 Place ID。")
        place_id_to_process = identifier.strip()
    else:
        print("ℹ️ 输入被识别为 Plus Code，正在尝试转换...")
        place_id_to_process = crawler.get_place_id_from_plus_code(identifier)
    
    if not place_id_to_process:
        await interaction.followup.send(embed=create_error_embed(
            f"无法通过你提供的标识符 `{identifier}` 找到有效的地点。\n"
            "请确保输入的是正确的 Google Plus Code 或 Place ID。"
        ))
        return
    
    try:
        result = await crawler._process_place(place_id_to_process)
        if result.get("status") == "success":
            await interaction.followup.send(embed=create_success_embed(f"成功添加/更新餐厅: **{result.get('name')}**"))
        elif result.get("status") == "skipped":
            await interaction.followup.send(embed=create_error_embed(f"此地点 ({place_id_to_process}) 被判断为非餐厅，已跳过。", "操作中断"))
        else:
            await interaction.followup.send(embed=create_error_embed(f"无法添加此地点，请检查 Place ID 或查看后台日志。"))
    except Exception as e:
        print(f"❌ 在执行 /admin add 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"添加过程中发生错误: {e}"))

@admin_group.command(name="delete", description="从数据库中删除一个餐厅")
@app_commands.describe(google_place_id="要删除的餐厅的 Google Place ID")
async def delete_command(interaction: discord.Interaction, google_place_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=create_error_embed("此命令仅限管理员使用。", "⛔ 权限不足"),
            ephemeral=True
        )
        return
    
    if not db:
        await interaction.response.send_message(
            embed=create_error_embed("数据库服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        restaurant_to_delete = await db.get_restaurant_by_place_id(google_place_id)
        if not restaurant_to_delete:
            await interaction.followup.send(embed=create_error_embed(f"数据库中不存在 Place ID 为 `{google_place_id}` 的餐厅。"))
            return
        
        deleted_count = await db.delete_restaurant_by_place_id(google_place_id)
        if deleted_count > 0:
            await interaction.followup.send(embed=create_success_embed(f"已成功从数据库中删除餐厅: **{restaurant_to_delete.get('name')}**"))
        else:
            await interaction.followup.send(embed=create_error_embed(f"尝试删除失败，数据库中未找到该记录。"))
    except Exception as e:
        print(f"❌ 在执行 /admin delete 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"删除过程中发生错误: {e}"))

# ===== 位置别名（黑话）管理 =====
alias_group = app_commands.Group(name="alias", description="位置别名管理", parent=admin_group)

@alias_group.command(name="add", description="添加或更新位置别名（可通过地址或坐标）")
@app_commands.describe(
    alias="别名，如 '学校'、'公司'",
    address="地址(可选, 如果提供坐标则此项仅为描述)",
    latitude="纬度(可选, 与经度配对使用)",
    longitude="经度(可选, 与纬度配对使用)",
    description="额外说明（可选）",
    global_alias="是否为全局别名（默认仅本服务器可用）"
)
async def add_alias(
    interaction: discord.Interaction, 
    alias: str,
    address: str = None,
    latitude: float = None,
    longitude: float = None,
    description: str = None,
    global_alias: bool = False
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(embed=create_error_embed("此命令仅限管理员使用。", "⛔ 权限不足"), ephemeral=True)
        return
    
    if not (crawler and user_prefs_db):
        await interaction.response.send_message(embed=create_error_embed("相关服务尚未准备就绪。"), ephemeral=True)
        return

    # --- 参数验证 ---
    has_coords = latitude is not None and longitude is not None
    has_address = address is not None

    if not has_coords and not has_address:
        await interaction.response.send_message(embed=create_error_embed("必须提供地址或完整的经纬度坐标。"), ephemeral=True)
        return
        
    if (latitude is not None) != (longitude is not None):
        await interaction.response.send_message(embed=create_error_embed("经度和纬度必须同时提供。"), ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)
    
    lat_to_save, lng_to_save = latitude, longitude
    address_to_save = address

    try:
        # 如果没有提供坐标，则通过地址获取
        if not has_coords:
            print(f"ℹ️ 未提供坐标，正在通过地址 '{address}' 获取...")
            lat_to_save, lng_to_save = crawler.get_coordinates_from_address(address)
            if not lat_to_save or not lng_to_save:
                await interaction.followup.send(embed=create_error_embed(f"无法识别地址 '{address}'。"))
                return
        else:
            print(f"ℹ️ 已直接提供坐标 ({lat_to_save}, {lng_to_save})，跳过API调用。")

        guild_id = None if global_alias else (str(interaction.guild_id) if interaction.guild else None)
        
        await user_prefs_db.add_location_alias(
            alias=alias,
            latitude=lat_to_save,
            longitude=lng_to_save,
            address=address_to_save, # address_to_save 可能是 None，但数据库设计可以接受
            description=description,
            created_by=str(interaction.user.id),
            guild_id=guild_id
        )
        
        scope = "全局" if global_alias else "本服务器"
        
        # 创建更清晰的成功消息
        success_message = (
            f"✅ 已添加/更新位置别名:\n"
            f"• **别名**: `{alias}`\n"
            f"• **坐标**: `{lat_to_save:.6f}, {lng_to_save:.6f}`\n"
            f"• **地址描述**: `{address_to_save or '未提供'}`\n"
            f"• **作用域**: {scope}"
        )
        if description:
            success_message += f"\n• **说明**: {description}"
            
        await interaction.followup.send(
            embed=create_success_embed(success_message)
        )
    except Exception as e:
        print(f"❌ 添加位置别名时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"添加失败: {e}"))

@alias_group.command(name="list", description="列出所有位置别名")
@app_commands.describe(include_global="是否包含全局别名（默认是）")
async def list_aliases(interaction: discord.Interaction, include_global: bool = True):
    if not user_prefs_db:
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        guild_id = str(interaction.guild_id) if interaction.guild else None
        aliases = await user_prefs_db.list_location_aliases(guild_id, include_global)
        
        if not aliases:
            await interaction.followup.send(
                embed=create_error_embed("当前没有可用的位置别名。", "ℹ️ 提示")
            )
            return
        
        embed = discord.Embed(
            title="📍 位置别名列表",
            color=discord.Color.blue()
        )
        
        for alias_data in aliases[:25]:  # 最多显示25个
            scope = "🌍 全局" if alias_data.get('guild_id') is None else "🏠 本服务器"
            coords = alias_data['coordinates']
            value = f"{scope}\n位置: {alias_data.get('address', '未知')}\n坐标: `{coords['latitude']:.4f}, {coords['longitude']:.4f}`"
            if alias_data.get('description'):
                value += f"\n说明: {alias_data['description']}"
            
            embed.add_field(
                name=f"**{alias_data['alias']}**",
                value=value,
                inline=False
            )
        
        if len(aliases) > 25:
            embed.set_footer(text=f"仅显示前25个，共有{len(aliases)}个别名")
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"❌ 列出位置别名时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"查询失败: {e}"))

@alias_group.command(name="delete", description="删除位置别名")
@app_commands.describe(
    alias="要删除的别名",
    global_alias="是否删除全局别名"
)
async def delete_alias(interaction: discord.Interaction, alias: str, global_alias: bool = False):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            embed=create_error_embed("此命令仅限管理员使用。", "⛔ 权限不足"),
            ephemeral=True
        )
        return
    
    if not user_prefs_db:
        await interaction.response.send_message(
            embed=create_error_embed("相关服务尚未准备就绪。"), 
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        guild_id = None if global_alias else (str(interaction.guild_id) if interaction.guild else None)
        count = await user_prefs_db.delete_location_alias(alias, guild_id)
        
        if count > 0:
            scope = "全局" if global_alias else "本服务器"
            await interaction.followup.send(
                embed=create_success_embed(f"✅ 已删除{scope}别名: **{alias}**")
            )
        else:
            await interaction.followup.send(
                embed=create_error_embed(f"未找到别名 '{alias}'。")
            )
    except Exception as e:
        print(f"❌ 删除位置别名时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"删除失败: {e}"))

bot.tree.add_command(admin_group)

def main():
    """主函数，用于启动机器人"""
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ 致命错误: 未在 .env 文件中找到 DISCORD_TOKEN。")
        return
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ 致命错误: 无效的 Discord Token。请检查 .env 文件中的 DISCORD_TOKEN。")
    except Exception as e:
        print(f"❌ 运行机器人时发生意外错误: {e}")
    finally:
        if db:
            asyncio.run(db.close())
        if user_prefs_db:
            asyncio.run(user_prefs_db.close())
        print("ℹ️ 机器人已关闭。")

if __name__ == '__main__':
    main()
