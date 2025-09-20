import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import RestaurantDB
from utils import (
    parse_command_args, 
    create_restaurant_embed,
    create_help_embed,
    create_error_embed,
    create_no_results_embed
)

# 加载环境变量
load_dotenv()

# 设置机器人意图
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# 创建机器人实例
bot = commands.Bot(command_prefix='!', intents=intents)

# 数据库实例
db = None

@bot.event
async def on_ready():
    """机器人启动时的事件"""
    global db
    print(f'✅ {bot.user} 已经上线!')
    print(f'📊 连接到 {len(bot.guilds)} 个服务器')
    
    # 初始化数据库连接
    try:
        db = RestaurantDB()
        print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
    
    # 设置机器人状态
    await bot.change_presence(
        activity=discord.Game(name="输入 '吃啥' 获取餐厅推荐")
    )

@bot.event
async def on_message(message):
    """处理消息事件"""
    # 忽略机器人自己的消息
    if message.author == bot.user:
        return
    
    # 检查是否是"吃啥"命令
    if message.content.startswith('吃啥'):
        await handle_restaurant_command(message)
    elif message.content in ['帮助', 'help', '使用说明']:
        await message.channel.send(embed=create_help_embed())
    
    # 处理其他命令
    await bot.process_commands(message)

async def handle_restaurant_command(message):
    """处理餐厅推荐命令"""
    if not db:
        await message.channel.send(embed=create_error_embed("数据库连接失败，请稍后再试"))
        return
    
    try:
        # 解析命令参数
        filters = parse_command_args(message.content)
        
        # 发送"正在查找"消息
        thinking_msg = await message.channel.send("🔍 正在为您寻找合适的餐厅...")
        
        # 从数据库获取餐厅
        restaurants = db.get_random_restaurants(
            count=3,
            filters=filters,
            check_open=True
        )
        
        # 删除"正在查找"消息
        await thinking_msg.delete()
        
        if not restaurants:
            await message.channel.send(embed=create_no_results_embed())
            return
        
        # 发送餐厅推荐
        intro_embed = discord.Embed(
            title="🍴 为您推荐以下餐厅",
            description=f"根据您的要求，为您推荐了 {len(restaurants)} 家餐厅：",
            color=0x2ecc71
        )
        await message.channel.send(embed=intro_embed)
        
        # 发送每个餐厅的详细信息
        for i, restaurant in enumerate(restaurants, 1):
            embed = create_restaurant_embed(restaurant)
            embed.title = f"{i}. {embed.title}"
            await message.channel.send(embed=embed)
        
        # 添加反应表情供用户快速选择
        if len(restaurants) > 0:
            footer_embed = discord.Embed(
                description="祝您用餐愉快！如需更多推荐，请再次输入 `吃啥`",
                color=0x95a5a6
            )
            await message.channel.send(embed=footer_embed)
            
    except Exception as e:
        print(f"错误: {e}")
        await message.channel.send(
            embed=create_error_embed(f"抱歉，获取餐厅信息时出错了: {str(e)}")
        )

@bot.command(name='ping')
async def ping(ctx):
    """测试命令"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! 延迟: {latency}ms')

@bot.command(name='stats')
async def stats(ctx):
    """显示机器人统计信息"""
    if not db:
        await ctx.send("数据库未连接")
        return
    
    try:
        total = db.collection.count_documents({})
        embed = discord.Embed(
            title="📊 机器人统计",
            color=0x3498db
        )
        embed.add_field(name="餐厅总数", value=f"{total} 家", inline=True)
        embed.add_field(name="服务器数", value=f"{len(bot.guilds)} 个", inline=True)
        embed.add_field(name="延迟", value=f"{round(bot.latency * 1000)}ms", inline=True)
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"获取统计信息失败: {e}")

@bot.event
async def on_guild_join(guild):
    """加入新服务器时的事件"""
    print(f"✅ 加入了新服务器: {guild.name} (ID: {guild.id})")

@bot.event
async def on_guild_remove(guild):
    """离开服务器时的事件"""
    print(f"❌ 离开了服务器: {guild.name} (ID: {guild.id})")

# 错误处理
@bot.event
async def on_command_error(ctx, error):
    """命令错误处理"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ 缺少必要参数: {error}")
    else:
        await ctx.send(f"❌ 发生错误: {error}")

def main():
    """主函数"""
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ 未找到 DISCORD_TOKEN，请检查 .env 文件")
        return
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ 无效的机器人令牌")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        if db:
            db.close()

if __name__ == '__main__':
    main()