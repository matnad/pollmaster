import dbl
import logging

from discord.ext import tasks, commands

from essentials.settings import SETTINGS


class DiscordBotsOrgAPI(commands.Cog):
    """Handles interactions with the discordbots.org API"""

    def __init__(self, bot):
        self.bot = bot
        if SETTINGS.mode != "development":
            self.token = SETTINGS.dbl_token
            self.dblpy = dbl.DBLClient(self.bot, self.token)
            self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    @tasks.loop(minutes=10.0)
    async def update_stats(self):
        """This function runs every 10 minutes to automatically update your server count"""
        logger.info('Attempting to post server count')
        try:
            await self.dblpy.post_guild_count()
            logger.info('Posted server count ({})'.format(self.dblpy.guild_count()))
            sum_users = 0
            for guild in self.bot.guilds:
                sum_users += len(guild.members)
            logger.info(f'total users served by the bot: {sum_users}')
        except Exception as e:
            logger.exception('Failed to post server count\n{}: {}'.format(type(e).__name__, e))


async def setup(bot):
    global logger
    logger = logging.getLogger('discord')
    await bot.add_cog(DiscordBotsOrgAPI(bot))
