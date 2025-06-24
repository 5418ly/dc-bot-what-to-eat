# cogs/music.py

import discord
from discord.ext import commands
import yt_dlp

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}  # 用一个字典来管理每个服务器的播放队列

    def get_queue(self, ctx):
        # 获取或创建当前服务器的队列
        if ctx.guild.id not in self.queues:
            self.queues[ctx.guild.id] = []
        return self.queues[ctx.guild.id]

    def play_next(self, ctx):
        if ctx.guild.id in self.queues and self.queues[ctx.guild.id]:
            # 队列不为空，取出下一首歌
            queue = self.queues[ctx.guild.id]
            url = queue.pop(0) # 取出第一首歌
            
            # --- 和之前的播放逻辑几乎完全一样 ---
            ydl_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'no_warnings': True, 'source_address': '0.0.0.0'}
            ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    audio_url = info['url']
                    title = info.get('title', '未知标题')
                    
                    if 'http_headers' in info:
                        ffmpeg_options['headers'] = '\r\n'.join(f'{key}: {value}' for key, value in info['http_headers'].items())
                
                source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
                
                # 播放，并将 play_next 自身作为 after 回调
                ctx.voice_client.play(source, after=lambda e: self.play_next(ctx) if not e else print(f'播放错误: {e}'))
                
                # 创建一个异步任务来发送消息，避免阻塞 after 回调
                self.bot.loop.create_task(ctx.send(f'▶️ 正在播放: **{title}**'))

            except Exception as e:
                self.bot.loop.create_task(ctx.send(f'❌ 播放下一首时出错: {e}'))
                # 尝试播放队列里的再下一首
                self.play_next(ctx)

    @commands.command(name='play', help='播放音乐或添加到队列')
    async def play(self, ctx, *, url: str):
        voice_client = ctx.voice_client
        
        # 检查和加入频道
        if not ctx.author.voice:
            return await ctx.send("你必须先加入一个语音频道！")
        if voice_client is None:
            await ctx.author.voice.channel.connect()
        elif voice_client.channel != ctx.author.voice.channel:
            await voice_client.move_to(ctx.author.voice.channel)
            
        queue = self.get_queue(ctx)
        queue.append(url)
        await ctx.send(f"已将 `{url}` 添加到播放列表！")

        # 如果当前没有在播放，则开始播放队列
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            self.play_next(ctx)

    @commands.command(name='stop', help='停止播放并清空队列')
    async def stop(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_connected():
            queue = self.get_queue(ctx)
            queue.clear() # 清空队列
            voice_client.stop() # 停止当前播放
            await voice_client.disconnect()
            await ctx.send("已停止播放并离开频道。")

    @commands.command(name='skip', help='跳过当前歌曲')
    async def skip(self, ctx):
        voice_client = ctx.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop() # 停止当前歌曲，after回调会自动播放下一首
            await ctx.send("已跳过当前歌曲。")
        else:
            await ctx.send("当前没有歌曲正在播放。")

# 关键的最后一步：设置 Cog
# 这个异步函数是 discord.py 加载 Cog 时会调用的
async def setup(bot):
    await bot.add_cog(MusicCog(bot))
