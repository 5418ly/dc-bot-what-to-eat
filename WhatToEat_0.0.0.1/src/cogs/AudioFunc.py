# cogs/AudioFunc.py
import asyncio

import discord
import yt_dlp
from discord.ext import commands
import subprocess

from pyexpat.errors import messages

ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
}

CHANNELS = 2
RATE = 48000
CHUNK_SIZE = 4096

ffmpeg_options = {'options': '-vn -ar 48000 -ac 2 -ab 192k -filter:a "volume=0.5"'}

class AudioFunc(commands.Cog):
    """
    A cog for managing audio-related functionalities,
    such as disconnecting the bot from a voice channel.
    """
    def __init__(self, bot):
        """
        Initializes the AudioFunc cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot

    @commands.hybrid_command(name="leave", description="Leave Voice Chat")
    # Add descriptions for arguments for better UX in Discord
    async def leave(self, ctx):
        """
        Disconnects the bot from the voice channel it is currently in.

        Usage: !leave or !disconnect
        """
        voice_client = ctx.voice_client

        # Check if the bot is connected to a voice channel
        if voice_client and voice_client.is_connected():
            # Disconnect from the voice channel
            await voice_client.disconnect()
            await ctx.send("Disconnected from the voice channel.")
        else:
            # Inform the user if the bot is not connected
            await ctx.send("I'm not connected to a voice channel.")

    @commands.hybrid_command()
    async def join(self, ctx):
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("You're not in a voice channel!")

        if not ctx.voice_client:
            await voice_channel.connect()
            await ctx.send(f"Joined {voice_channel.name}")
        else:
            await ctx.send("I'm already in a voice channel!")

    @commands.hybrid_command()
    async def play(self,ctx,URL):
        """
          此函数将Bilibili音频流播放到Discord语音频道。
          它取代了本地PyAudio播放，直接将FFmpeg输出连接到Discord的语音客户端。
          """

        # 1. ========== 检查用户是否在语音频道 (Check if user is in a voice channel) ==========
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if not voice_channel:
            return await ctx.send("您不在语音频道中！请先加入一个语音频道。", delete_after=10)

        # 2. ========== 连接或移动到语音频道 (Connect or move to the voice channel) ==========
        if ctx.voice_client:  # 如果机器人已经连接到语音频道
            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                # 如果正在播放或暂停，停止当前播放以播放新音频
                ctx.voice_client.stop()
                await asyncio.sleep(0.5)  # 稍作等待，确保停止干净
            await ctx.send(f"正在离开当前频道并加入 {voice_channel.name} 播放新音频。", delete_after=10)
            await ctx.voice_client.move_to(voice_channel)
        else:  # 如果机器人未连接
            await voice_channel.connect()
            await ctx.send(f"已加入 {voice_channel.name}。", delete_after=10)

        # 3. ========== 使用 yt-dlp 获取音频流直链和Headers (Use yt-dlp to get direct audio stream URL and Headers) ==========
        # 注意：Discord的FFmpegPCMAudio通常可以直接处理yt-dlp提供的URL，
        # yt-dlp获取的http_headers通常是供yt-dlp自身下载时使用的，FFmpeg直接流式传输时可能不需要。
        print(f"正在从 {URL} 获取音频信息...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'cachedir': False,  # 禁用缓存以避免某些流的问题
            'geo_bypass': True,  # 尝试绕过地理限制，对Bilibili可能有用
        }

        audio_url = None
        video_title = '未知标题'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(URL, download=False)
                audio_url = info['url']
                video_title = info.get('title', '未知标题')
                # http_headers = info.get('http_headers', {}) # 此处保留，但请注意上述FFmpegPCMAudio的限制
                print(f"成功获取到音频流: {video_title}")

        except Exception as e:
            print(f"错误：无法获取音频流。请检查链接是否有效或网络连接。详细错误: {e}")
            await ctx.send("无法获取音频信息。请检查链接是否有效。", delete_after=15)
            # 如果获取失败，尝试断开连接以清理
            if ctx.voice_client and ctx.voice_client.is_connected():
                await ctx.voice_client.disconnect()
            return

        # 4. ========== 配置并启动 FFmpeg 进程用于Discord播放 (Configure and start FFmpeg for Discord playback) ==========
        print("正在配置FFmpeg进行实时转码...")

        # FFmpeg 选项，用于增强流媒体的鲁棒性
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.5"'  # -vn 禁用视频流，-filter:a "volume=0.5" 降低音量
        }

        try:
            # 创建一个Discord FFmpeg音频源。它将在内部调用ffmpeg并管理流。
            player = discord.FFmpegPCMAudio(
                source=audio_url,
                **ffmpeg_options
            )

            # 5. ========== 播放音频到Discord语音频道 (Play audio to Discord voice channel) ==========
            # after 回调函数会在播放结束或发生错误时被调用
            ctx.voice_client.play(player, after=lambda e: print(f'播放器错误: {e}') if e else print('播放完毕！'))

            await ctx.send(f"▶️ 正在播放: **{video_title}**", delete_after=60)

            # 可选：等待直到歌曲播放完毕
            while ctx.voice_client.is_playing():
                await asyncio.sleep(1)

        except Exception as e:
            print(f"播放过程中发生错误: {e}")
            await ctx.send(f"播放过程中发生错误: {e}", delete_after=15)\

        print("播放流程结束。")

    @commands.hybrid_command()
    async def skip(self,ctx):
        """
        跳过当前正在播放的歌曲。
        如果机器人正在播放音乐，它会停止当前播放。
        """
        voice_client = ctx.voice_client

        # 1. 检查机器人是否连接到语音频道
        if not voice_client:
            return await ctx.send("我目前没有连接到任何语音频道。", delete_after=10)

        # 2. 检查机器人是否正在播放音频
        if not voice_client.is_playing():
            return await ctx.send("我目前没有播放任何歌曲。", delete_after=10)

        # 3. 停止当前播放
        voice_client.stop()
        await ctx.send("已跳过当前歌曲！", delete_after=5)
        # 4. 可选：可以在这里添加逻辑来播放队列中的下一首歌曲
        # 例如：如果你的机器人有一个歌曲队列，你可以在这里调用播放下一首的函数!

# This is the required setup function for the cog.
# It is called by bot.load_extension() from your main bot file.
# For simple cog additions, it does not need to be 'async def'.
async def setup(bot):
    """
    Adds the AudioFunc cog to the bot.

    Args:
        bot (commands.Bot): The bot instance to add the cog to.
    """
    await bot.add_cog(AudioFunc(bot))