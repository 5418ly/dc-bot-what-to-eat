import discord
import os
from discord.ext import commands

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Needed for voice-related commands

# Define command prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Token (get from environment or default)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") # IMPORTANT: Replace "YOUR_BOT_TOKEN_HERE" with your actual bot token or ensure it's set as an environment variable.

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    print("Bot is ready!")

    # Load cogs here after the bot is ready
    try:
        await bot.load_extension('cogs.AudioFunc')
        print("Cog 'AudioFunc' loaded successfully.")
    except Exception as e:
        print(f"Failed to load cog 'AudioFunc': {e}")


@bot.command()
async def join(ctx):
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel:
        return await ctx.send("You're not in a voice channel!")

    if not ctx.voice_client:
        await voice_channel.connect()
        await ctx.send(f"Joined {voice_channel.name}")
    else:
        await ctx.send("I'm already in a voice channel!")


@bot.command()
async def play(ctx, *, search):
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if not voice_channel:
        return await ctx.send("You're not in a voice channel!")

    if not ctx.voice_client:
        await voice_channel.connect()
        await ctx.send(f"Joined {voice_channel.name} to play music.")
    await ctx.send(f"Searching for: `{search}`") # Using backticks for monospace in Discord


@bot.command()
async def 吃啥(ctx):
    await ctx.send('以下是我建议: ')


# Run the bot
bot.run(DISCORD_BOT_TOKEN)