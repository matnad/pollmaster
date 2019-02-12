import traceback
import logging
import aiohttp
import discord

from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

from essentials.multi_server import get_pre
from essentials.settings import SETTINGS
from utils.import_old_database import import_old_database

bot_config = {
    'command_prefix': get_pre,
    'pm_help': False,
    'status': discord.Status.online,
    'owner_id': SETTINGS.owner_id,
    'fetch_offline_members': False,
    'max_messages': 200000
}

bot = commands.Bot(**bot_config)
bot.remove_command('help')

# logger
# create logger with 'spam_application'
logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('pollmaster.log')
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

extensions = ['cogs.config', 'cogs.poll_controls', 'cogs.help', 'cogs.db_api']
for ext in extensions:
    bot.load_extension(ext)


@bot.event
async def on_ready():
    bot.owner = await bot.get_user_info(str(SETTINGS.owner_id))

    mongo = AsyncIOMotorClient(SETTINGS.mongo_db)
    bot.db = mongo.pollmaster
    bot.session = aiohttp.ClientSession()
    print(bot.db)
    await bot.change_presence(game=discord.Game(name=f'V2 IS HERE >> pm!help'))

    # check discord server configs
    try:
        db_server_ids = [entry['_id'] async for entry in bot.db.config.find({}, {})]
        for server in bot.servers:
            if server.id not in db_server_ids:
                # create new config entry
                await bot.db.config.update_one(
                    {'_id': str(server.id)},
                    {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
                    upsert=True
                )
                try:
                    await import_old_database(bot, server)
                    print(str(server), "updated.")
                except:
                    print(str(server.id), "failed.")
    except:
        print("Problem verifying servers.")

    print("Servers verified. Bot running.")


@bot.event
async def on_command_error(e, ctx):
    if SETTINGS.log_errors:
        ignored_exceptions = (
            commands.MissingRequiredArgument,
            commands.CommandNotFound,
            commands.DisabledCommand,
            commands.BadArgument,
            commands.NoPrivateMessage,
            commands.CheckFailure,
            commands.CommandOnCooldown,
        )

        if isinstance(e, ignored_exceptions):
            # log warnings
            logger.warning(f'{type(e).__name__}: {e}\n{"".join(traceback.format_tb(e.__traceback__))}')
            return

        # log error
        logger.error(f'{type(e).__name__}: {e}\n{"".join(traceback.format_tb(e.__traceback__))}')

        if SETTINGS.msg_errors:
            # send discord message for unexpected errors
            e = discord.Embed(
                title=f"Error With command: {ctx.command.name}",
                description=f"```py\n{type(e).__name__}: {e}\n```\n\nContent:{ctx.message.content}"
                            f"\n\tServer: {ctx.message.server}\n\tChannel: <#{ctx.message.channel.id}>"
                            f"\n\tAuthor: <@{ctx.message.author.id}>",
                timestamp=ctx.message.timestamp
            )
            await bot.send_message(bot.owner, embed=e)


@bot.event
async def on_server_join(server):
    result = await bot.db.config.find_one({'_id': str(server.id)})
    if result is None:
        await bot.db.config.update_one(
            {'_id': str(server.id)},
            {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
            upsert=True
        )


bot.run(SETTINGS.bot_token, reconnect=True)