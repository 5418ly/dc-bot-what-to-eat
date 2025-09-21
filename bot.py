# bot.py

import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# --- 导入我们自己的模块 ---
from database import RestaurantDB
from llm_parser import LLMParser
from crawler import GoogleMapsCrawler
from utils import (
    create_restaurant_embed,
    create_help_embed,
    create_error_embed,
    create_no_results_embed,
    create_success_embed,
    create_crawler_summary_embed
)

# # --- 初始化 ---
# load_dotenv()

# 设置 Bot 的权限 (Intents)
intents = discord.Intents.default()
intents.message_content = False # 斜杠命令不需要读取消息内容

# 创建 Bot 实例
bot = commands.Bot(command_prefix="!", intents=intents)

# 全局变量，在 on_ready 中实例化
db: RestaurantDB | None = None
llm_parser: LLMParser | None = None
crawler: GoogleMapsCrawler | None = None

# --- Bot 事件 ---

@bot.event
async def on_ready():
    """当机器人成功连接到 Discord 时执行"""
    global db, llm_parser, crawler
    print(f'✅ {bot.user} 已成功登录并上线!')
    
    try:
        # 实例化所有服务 (现在是非阻塞的)
        db = RestaurantDB()
        llm_parser = LLMParser()
        # crawler 的 __init__ 会调用 RestaurantDB 的 __init__，也是非阻塞的
        crawler = GoogleMapsCrawler() 
        
        # 显式地调用异步连接和设置方法
        await db.connect_and_setup() # <-- 新增的 await 调用
        
        print("✅ 所有服务模块初始化成功。")

        # 同步斜杠命令
        synced = await bot.tree.sync()
        print(f"🔄 已同步 {len(synced)} 条斜杠命令。")

    except Exception as e:
        print(f"❌ 初始化服务或同步命令时发生严重错误: {e}")
        return

    await bot.change_presence(activity=discord.Game(name="输入 /find 找美食"))


# --- 主要用户命令 ---

@bot.tree.command(name="find", description="通过自然语言描述来查找餐厅")
@app_commands.describe(query="你想吃什么？例如：'明天中午的便宜川菜' 或 '附近评分高的日料'")
async def find_restaurant(interaction: discord.Interaction, query: str):
    if not (db and llm_parser):
        await interaction.response.send_message(embed=create_error_embed("机器人服务尚未准备就绪，请稍后再试。"), ephemeral=True)
        return

    # 1. 立即响应，防止超时
    await interaction.response.defer(thinking=True)

    try:
        # 2. 从数据库获取上下文信息
        available_cuisines = await db.get_all_cuisine_types()
        available_tags = await db.get_all_tags()

        # 3. 使用 LLM 解析用户请求
        filters, query_time = await llm_parser.parse_user_request(query, available_cuisines, available_tags)

        # 如果LLM无法解析，给用户一个友好提示
        if not filters and not query_time:
             await interaction.followup.send(embed=create_error_embed("抱歉，我没太理解你的意思，可以换个说法吗？","🤔 理解失败"))
             return

        # 4. 从数据库查找餐厅
        restaurants = await db.find_restaurants(
            filters=filters,
            query_time=query_time,
            count=3
        )

        # 5. 发送结果
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

            # 一次性发送所有 embed (最多10个)
            await interaction.followup.send(embeds=embeds_to_send)

    except Exception as e:
        print(f"❌ 在执行 /find 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"处理你的请求时发生未知错误。\n`{e}`"))


# 创建别名
@bot.tree.command(name="吃啥", description="通过自然语言描述来查找餐厅（/find 的别名）")
@app_commands.describe(query="你想吃什么？例如：'明天中午的便宜川菜' 或 '附近评分高的日料'")
async def find_restaurant_alias(interaction: discord.Interaction, query: str):
    await find_restaurant(interaction, query)


@bot.tree.command(name="help", description="显示机器人使用指南")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(embed=create_help_embed(), ephemeral=True)


# --- 管理员命令组 ---

# 创建一个命令组, 并设置默认权限为 "管理员"
admin_group = app_commands.Group(name="admin", description="管理员专用命令", default_permissions=discord.Permissions(administrator=True))


@admin_group.command(name="crawl", description="从指定经纬度和半径爬取 Google Maps 餐厅数据")
@app_commands.describe(
    latitude="中心纬度", 
    longitude="中心经度", 
    radius="搜索半径（米）",
    max_results="要爬取的最大地点数 (默认20, 最多60)"
)
async def crawl_command(interaction: discord.Interaction, latitude: float, longitude: float, radius: int, max_results: int = 20):
    if not crawler:
        await interaction.response.send_message(embed=create_error_embed("爬虫服务尚未准备就绪。"), ephemeral=True)
        return

    # 对 max_results 进行范围限制
    if not 1 <= max_results <= 60:
        await interaction.response.send_message(
            embed=create_error_embed("参数错误", "`max_results` 的值必须在 1 到 60 之间。"),
            ephemeral=True
        )
        return

    # 立即响应
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        # 将 max_results 传递给爬虫方法
        summary = await crawler.crawl_area(latitude, longitude, radius, max_results)
        
        location_info = {"lat": latitude, "lon": longitude, "radius": radius}
        summary_embed = create_crawler_summary_embed(summary, location_info)
        summary_embed.description += f"\n最大结果数设置: `{max_results}`" # 在摘要中也显示这个信息
        
        await interaction.followup.send(embed=summary_embed)
    except Exception as e:
        print(f"❌ 在执行 /admin crawl 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"爬取过程中发生错误: {e}"))


@admin_group.command(name="add", description="通过 Google Plus Code 或 Place ID 添加餐厅")
@app_commands.describe(identifier="餐厅的 Google Plus Code (如 '3V7V+2M 广州市') 或 Place ID")
async def add_command(interaction: discord.Interaction, identifier: str):
    if not (crawler and db):
        await interaction.response.send_message(embed=create_error_embed("相关服务尚未准备就绪。"), ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    place_id_to_process = None

    # 智能判断输入是 Plus Code 还是 Place ID
    # Place ID 通常以 "ChIJ" 开头，且长度很长。这是一个简单但有效的判断方法。
    if identifier.strip().startswith("ChIJ"):
        print("ℹ️ 输入被识别为 Place ID。")
        place_id_to_process = identifier.strip()
    else:
        print("ℹ️ 输入被识别为 Plus Code，正在尝试转换...")
        # 调用我们新写的方法来转换 Plus Code
        place_id_to_process = crawler.get_place_id_from_plus_code(identifier)
    
    # 如果经过转换后还是没有 Place ID，则操作失败
    if not place_id_to_process:
        await interaction.followup.send(embed=create_error_embed(
            f"无法通过你提供的标识符 `{identifier}` 找到有效的地点。\n"
            "请确保输入的是正确的 Google Plus Code 或 Place ID。"
        ))
        return

    # --- 后续流程与之前完全相同 ---
    try:
        # 复用爬虫中的处理单个地点的逻辑
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
    if not db:
        await interaction.response.send_message(embed=create_error_embed("数据库服务尚未准备就绪。"), ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        # 在删除前先查找，以便获取餐厅名称用于反馈
        restaurant_to_delete = await db.get_restaurant_by_place_id(google_place_id)
        if not restaurant_to_delete:
            await interaction.followup.send(embed=create_error_embed(f"数据库中不存在 Place ID 为 `{google_place_id}` 的餐厅。"))
            return

        deleted_count = await db.delete_restaurant_by_place_id(google_place_id)
        if deleted_count > 0:
            await interaction.followup.send(embed=create_success_embed(f"已成功从数据库中删除餐厅: **{restaurant_to_delete.get('name')}**"))
        else:
            # 这种情况理论上不会发生，因为我们前面已经检查过了
            await interaction.followup.send(embed=create_error_embed(f"尝试删除失败，数据库中未找到该记录。"))
    except Exception as e:
        print(f"❌ 在执行 /admin delete 命令时出错: {e}")
        await interaction.followup.send(embed=create_error_embed(f"删除过程中发生错误: {e}"))

# 将命令组注册到 bot 的命令树中
bot.tree.add_command(admin_group)


# --- 启动 Bot ---
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
        # 机器人关闭时，确保数据库连接被关闭
        if db:
            db.close()
        print("ℹ️ 机器人已关闭。")

if __name__ == '__main__':
    main()