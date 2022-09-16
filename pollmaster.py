import json
import sys
import traceback
import asyncio

import aiohttp
import discord
import logging


from essentials.messagecache import MessageCache
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

from essentials.multi_server import get_pre
from essentials.settings import SETTINGS

syncOnce = False

bot_config = {
    'command_prefix': get_pre,
    'case_insensitive': True,
    'pm_help': False,
    'status': discord.Status.online,
    'owner_id': SETTINGS.owner_id,
    'fetch_offline_members': False,
    'max_messages': 15000
}
intents = discord.Intents.default()
intents.messages = True
intents.members = True
intents.reactions = True
intents.message_content = True
intents.guilds = True
intents.presences = True
bot = commands.AutoShardedBot(**bot_config, intents=intents)
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
fh.setLevel(logging.INFO)
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
async def setup(bot):
    for ext in extensions:
        await bot.load_extension(ext)

@bot.event
async def on_message(message):
    # allow case insensitive prefix
    prefix = await get_pre(bot, message)
    if type(prefix) == tuple:
        prefixes = (t.lower() for t in prefix)
        for pfx in prefixes:
            if len(pfx) >= 1 and message.content.lower().startswith(pfx.lower()):
                # print("Matching", message.content, "with", pfx)
                message.content = pfx + message.content[len(pfx):]
                await bot.process_commands(message)
                break
    else:
        if message.content.lower().startswith(prefix.lower()):
            message.content = prefix + message.content[len(prefix):]
            await bot.process_commands(message)


@bot.event
async def on_ready():
    global syncOnce
    await bot.wait_until_ready()
    if not syncOnce:
        await bot.tree.sync()
        syncOnce = True
    
    bot.owner = await bot.fetch_user(SETTINGS.owner_id)

    # load emoji list
    with open('utils/emoji-compact.json', encoding='utf-8') as emojson:
        bot.emoji_dict = json.load(emojson)

    # # check discord server configs
    # try:
    #     db_server_ids = [entry['_id'] async for entry in bot.db.config.find({}, {})]
    #     for server in bot.guilds:
    #         if str(server.id) not in db_server_ids:
    #             # create new config entry
    #             await bot.db.config.update_one(
    #                 {'_id': str(server.id)},
    #                 {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
    #                 upsert=True
    #             )
    # except:
    #     print("Problem verifying servers.")

    # cache prefixes
    bot.pre = {entry['_id']: entry.get('prefix', 'pm!') async for entry in bot.db.config.find({}, {'_id', 'prefix'})}

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="pm!help"))

    print("Bot running.")


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
            commands.MissingPermissions,
            discord.errors.Forbidden,
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

async def main():
    async with bot:
        mongo = AsyncIOMotorClient(SETTINGS.mongo_db)
        bot.db = mongo.pollmaster
        bot.session = aiohttp.ClientSession()
        await setup(bot)
        await bot.start(SETTINGS.bot_token)

asyncio.run(main())



