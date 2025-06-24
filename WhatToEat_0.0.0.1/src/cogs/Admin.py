# cogs/Admin.py

import discord
from discord.ext import commands
from discord import app_commands # Crucial for app_commands decorators
from typing import Literal

class Admin(commands.Cog):
    """
    A cog for managing administrative functionalities,
    such as reloading other cogs.
    """
    def __init__(self, bot):
        """
        Initializes the Admin cog.

        Args:
            bot (commands.Bot): The bot instance.
        """
        self.bot = bot

    @commands.hybrid_command(name="reload", description="Reloads a specified bot cog.")
    # Add 'self' as the first argument for instance methods within a class
    # Use self.bot to access the bot instance
    async def reload(self, ctx: commands.Context, Cog: Literal["AudioFunc", "Admin"]):
        try:
            # Call .lower() on Cog to get the lowercase filename
            await self.bot.reload_extension(name="cogs." + Cog)
            await ctx.send(f"Successfully Reloaded **{Cog}.py**")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"Error: **{Cog}.py** is not loaded.")
        except commands.ExtensionNotFound:
            await ctx.send(f"Error: Could not find **{Cog}.py**.")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred while reloading **{Cog}.py**: {e}")

# This function is crucial for discord.py to load your cog
async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))