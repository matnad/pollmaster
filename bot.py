import asyncio
import io
import json
import logging
import textwrap
import traceback
from contextlib import redirect_stdout

import aiohttp
import discord
import websockets
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

from essentials.membercache import MemberCache
from essentials.messagecache import MessageCache
from essentials.multi_server import get_pre
from essentials.settings import SETTINGS


class ClusterBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        self.pipe = kwargs.pop('pipe')
        self.cluster_name = kwargs.pop('cluster_name')
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        super().__init__(**kwargs, loop=loop)
        self.websocket = None
        self._last_result = None
        self.ws_task = None
        self.responses = asyncio.Queue()
        self.eval_wait = False
        log = logging.getLogger(f"Cluster#{self.cluster_name}")
        log.setLevel(logging.DEBUG)
        log.handlers = [logging.FileHandler(f'cluster-{self.cluster_name}.log', encoding='utf-8', mode='a')]

        log.info(f'[Cluster#{self.cluster_name}] {kwargs["shard_ids"]}, {kwargs["shard_count"]}')
        self.log = log

        self.owner = None
        self.db = None
        self.session = None
        self.emoji_dict = None
        self.pre = None

        self.remove_command('help')
        self.load_extension("cogs.eval")
        extensions = ['cogs.config', 'cogs.poll_controls', 'cogs.help', 'cogs.db_api', 'cogs.admin']
        for ext in extensions:
            self.load_extension(ext)

        self.message_cache = MessageCache(self)
        self.refresh_blocked = {}
        self.refresh_queue = {}

        self.loop.create_task(self.ensure_ipc())
        self.run(kwargs['token'])

    async def on_message(self, message):
        # allow case insensitive prefix
        prefix = await get_pre(self, message)
        if type(prefix) == tuple:
            prefixes = (t.lower() for t in prefix)
            for pfx in prefixes:
                if len(pfx) >= 1 and message.content.lower().startswith(pfx.lower()):
                    # print("Matching", message.content, "with", pfx)
                    message.content = pfx + message.content[len(pfx):]
                    await self.process_commands(message)
                    break
        else:
            if message.content.lower().startswith(prefix.lower()):
                message.content = prefix + message.content[len(prefix):]
                await self.process_commands(message)

    async def on_ready(self):
        self.owner = await self.fetch_user(SETTINGS.owner_id)
        mongo = AsyncIOMotorClient(SETTINGS.mongo_db)
        self.db = mongo.pollmaster
        self.session = aiohttp.ClientSession()
        with open('utils/emoji-compact.json', encoding='utf-8') as emojson:
            self.emoji_dict = json.load(emojson)
        self.pre = {entry['_id']: entry.get('prefix', 'pm!') async for entry in
                   self.db.config.find({}, {'_id', 'prefix'})}
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="pm!help"))

        self.log.info(f'[Cluster#{self.cluster_name}] Ready called.')
        self.pipe.send(1)
        self.pipe.close()

    async def on_guild_join(self, server):
        result = await self.db.config.find_one({'_id': str(server.id)})
        if result is None:
            await self.db.config.update_one(
                {'_id': str(server.id)},
                {'$set': {'prefix': 'pm!', 'admin_role': 'polladmin', 'user_role': 'polluser'}},
                upsert=True
            )
            self.pre[str(server.id)] = 'pm!'

    async def on_shard_ready(self, shard_id):
        self.log.info(f'[Cluster#{self.cluster_name}] Shard {shard_id} ready')

    async def on_command_error(self, ctx, exc):
        if not isinstance(exc, (commands.CommandNotFound, commands.NotOwner)):
            self.log.critical(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            # await ctx.send("check logs")

    async def on_error(self, *args, **kwargs):
        self.log.critical(traceback.format_exc())

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    async def close(self, *args, **kwargs):
        self.log.info("shutting down")
        await self.websocket.close()
        await super().close()

    async def exec(self, code):
        env = {
            'bot': self,
            '_': self._last_result
        }

        env.update(globals())

        body = self.cleanup_code(code)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return f'{e.__class__.__name__}: {e}'

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            f'{value}{traceback.format_exc()}'
        else:
            value = stdout.getvalue()

            if ret is None:
                if value:
                    return str(value)
                else:
                    return 'None'
            else:
                self._last_result = ret
                return f'{value}{ret}'

    async def websocket_loop(self):
        while True:
            try:
                msg = await self.websocket.recv()
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise
            data = json.loads(msg, encoding='utf-8')
            if self.eval_wait and data.get('response'):
                await self.responses.put(data)
            cmd = data.get('command')
            if not cmd:
                continue
            if cmd == 'ping':
                ret = {'response': 'pong'}
                self.log.info("received command [ping]")
            elif cmd == 'eval':
                self.log.info(f"received command [eval] ({data['content']})")
                content = data['content']
                data = await self.exec(content)
                ret = {'response': str(data)}
            else:
                ret = {'response': 'unknown command'}
            ret['author'] = self.cluster_name
            self.log.info(f"responding: {ret}")
            try:
                await self.websocket.send(json.dumps(ret).encode('utf-8'))
            except websockets.ConnectionClosed as exc:
                if exc.code == 1000:
                    return
                raise

    async def ensure_ipc(self):
        self.websocket = w = await websockets.connect('ws://localhost:42069')
        await w.send(self.cluster_name.encode('utf-8'))
        try:
            await w.recv()
            self.ws_task = self.loop.create_task(self.websocket_loop())
            self.log.info("ws connection succeeded")
        except websockets.ConnectionClosed as exc:
            self.log.warning(f"! couldnt connect to ws: {exc.code} {exc.reason}")
            self.websocket = None
            raise