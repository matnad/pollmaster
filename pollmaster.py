import os
import aiohttp


from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

#os.environ['dbltoken'] = 'ABC' #for website..
from cogs.utils import get_pre

os.environ['mongoDB'] = 'mongodb://localhost:27017/pollmaster'

# async def get_pre(bot, message):
#     '''Gets the prefix for the server.'''
#     print(str(message.content))
#     try:
#         result = await bot.db.config.find_one({'_id': str(message.server.id)})
#     except AttributeError:
#         return '!'
#     if not result or not result.get('prefix'):
#         return '!'
#     return result.get('prefix')

bot = commands.Bot(command_prefix=get_pre)
dbltoken = os.environ.get('dbltoken')

extensions = ['cogs.config','cogs.poll_controls']
for ext in extensions:
    bot.load_extension(ext)

@bot.event
async def on_ready():

    mongo = AsyncIOMotorClient(os.environ.get('mongodb'))
    bot.db = mongo.pollmaster
    bot.session = aiohttp.ClientSession()
    print(bot.db)
    # document = {'key': 'value'}
    # result = await bot.db.test_collection.insert_one(document)
    # print('result %s' % repr(result.inserted_id))


bot.run('NDQ0ODMxNzIwNjU5ODc3ODg5.DdhqZw.fsicJ8FffOYn670uPGuC4giXIlk')