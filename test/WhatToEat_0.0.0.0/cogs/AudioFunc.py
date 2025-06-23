# cogs/AudioFunc.py

import discord
from discord.ext import commands

class AudioFunc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="leave", aliases=["disconnect"])
    async def leave(self, ctx):
        voice_client = ctx.voice_client

        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            await ctx.send("Disconnected from the voice channel.")
        else:
            await ctx.send("I'm not connected to a voice channel.")

# Required setup function to load the cog
def setup(bot):
    bot.add_cog(AudioFunc(bot))
