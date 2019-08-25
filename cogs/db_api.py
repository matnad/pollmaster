import dbl
import asyncio
import logging

from discord.ext import commands

from essentials.settings import SETTINGS


class DiscordBotsOrgAPI(commands.Cog):
    """Handles interactions with the discordbots.org API"""

    def __init__(self, bot):
        self.bot = bot
        self.token = SETTINGS.dbl_token
        self.dblpy = dbl.Client(self.bot, self.token)
        self.bot.loop.create_task(self.update_stats())

    async def update_stats(self):
        """This function runs every 30 minutes to automatically update your server count"""

        while True:
            logger.info('attempting to post server count')
            try:
                if SETTINGS.mode == 'production':
                    await self.dblpy.post_server_count()
                logger.info('posted server count ({})'.format(len(self.bot.guilds)))
                sum_users = 0
                for guild in self.bot.guilds:
                    sum_users += len(guild.members)
                logger.info(f'total users served by the bot: {sum_users}')
            except Exception as e:
                logger.exception('Failed to post server count\n{}: {}'.format(type(e).__name__, e))
            await asyncio.sleep(1800)


def setup(bot):
    global logger
    logger = logging.getLogger('discord')
    bot.add_cog(DiscordBotsOrgAPI(bot))