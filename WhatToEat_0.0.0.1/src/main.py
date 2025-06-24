import discord
import os
from discord.ext import commands
import asyncio

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Needed for voice-related commands

# Define command prefix
bot = commands.Bot(command_prefix='!', intents=intents)

# Token (get from environment or default)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


# --- Load Cogs ---
async def load_extensions():
    initial_extensions = [
        'cogs.AudioFunc',  # Your existing audio cog
        'cogs.Admin'       # Load your new admin cog
    ]

    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            print(f"Loaded {extension}")
        except commands.ExtensionAlreadyLoaded:
            print(f"Warning: {extension} already loaded.")
        except commands.ExtensionNotFound:
            print(f"Error: {extension} not found.")
        except Exception as e:
            print(f"Failed to load {extension}: {e}")


@bot.event
async def on_ready():
    await load_extensions()  # Load cogs when the bot is ready
    print(f'We have logged in as {bot.user}')
    print("Bot is ready!")


@bot.hybrid_command()
async def 吃啥(ctx):
    await ctx.send('以下是我建议: ')


# Run the bot
async def main():
    async with bot:
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())