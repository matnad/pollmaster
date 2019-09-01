import json
import sys
import traceback

import aiohttp
import discord
import logging


from essentials.messagecache import MessageCache
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

from essentials.multi_server import get_pre
from essentials.settings import SETTINGS

bot_config = {
    'command_prefix': get_pre,
    'pm_help': False,
    'status': discord.Status.online,
    'owner_id': SETTINGS.owner_id,
    'fetch_offline_members': False,
    'max_messages': 15000
}

bot = commands.AutoShardedBot(**bot_config)
bot.remove_command('help')

bot.message_cache = MessageCache(bot)
bot.refresh_blocked = {}
bot.refresh_queue = {}

# logger
# create logger with 'spam_application'
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('pollmaster.log',  encoding='utf-8', mode='w')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

extensions = ['cogs.config', 'cogs.poll_controls', 'cogs.help', 'cogs.db_api', 'cogs.admin']
for ext in extensions:
    bot.load_extension(ext)


@bot.event
async def on_ready():
    bot.owner = await bot.fetch_user(SETTINGS.owner_id)

    mongo = AsyncIOMotorClient(SETTINGS.mongo_db)
    bot.db = mongo.pollmaster
    bot.session = aiohttp.ClientSession()
    print(bot.db)

    # load emoji list
    with open('utils/emoji-compact.json', encoding='utf-8') as emojson:
        bot.emoji_dict = json.load(emojson)

    # check discord server configs
    try:
        db_server_ids = [entry['_id'] async for entry in bot.db.config.find({}, {})]
        for server in bot.guilds:
            if str(server.id) not in db_server_ids:
                # create new config entry
                await bot.db.config.update_one(
                    {'_id': str(server.id)},
                    {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
                    upsert=True
                )
    except:
        print("Problem verifying servers.")

    # cache prefixes
    bot.pre = {entry['_id']: entry['prefix'] async for entry in bot.db.config.find({}, {'_id', 'prefix'})}

    game = discord.Game("Democracy 4")
    await bot.change_presence(status=discord.Status.online, activity=game)

    print("Servers verified. Bot running.")


@bot.event
async def on_command_error(ctx, e):

    if hasattr(ctx.cog, 'qualified_name') and ctx.cog.qualified_name == "Admin":
        # Admin cog handles the errors locally
        return

    if SETTINGS.log_errors:
        ignored_exceptions = (
            commands.MissingRequiredArgument,
            commands.CommandNotFound,
            commands.DisabledCommand,
            commands.BadArgument,
            commands.NoPrivateMessage,
            commands.CheckFailure,
            commands.CommandOnCooldown,
            commands.MissingPermissions
        )

        if isinstance(e, ignored_exceptions):
            # log warnings
            # logger.warning(f'{type(e).__name__}: {e}\n{"".join(traceback.format_tb(e.__traceback__))}')
            return

        # log error
        logger.error(f'{type(e).__name__}: {e}\n{"".join(traceback.format_tb(e.__traceback__))}')
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)

        if SETTINGS.msg_errors:
            # send discord message for unexpected errors
            e = discord.Embed(
                title=f"Error With command: {ctx.command.name}",
                description=f"```py\n{type(e).__name__}: {str(e)}\n```\n\nContent:{ctx.message.content}"
                            f"\n\tServer: {ctx.message.server}\n\tChannel: <#{ctx.message.channel}>"
                            f"\n\tAuthor: <@{ctx.message.author}>",
                timestamp=ctx.message.timestamp
            )
            await ctx.send(bot.owner, embed=e)

        # if SETTINGS.mode == 'development':
        raise e


@bot.event
async def on_guild_join(server):
    result = await bot.db.config.find_one({'_id': str(server.id)})
    if result is None:
        await bot.db.config.update_one(
            {'_id': str(server.id)},
            {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
            upsert=True
        )
        bot.pre[str(server.id)] = 'pm!'

bot.run(SETTINGS.bot_token)
