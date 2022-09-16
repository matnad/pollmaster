import asyncio
import io
import json
import textwrap
import traceback
from contextlib import redirect_stdout

from discord.ext import commands
from discord import app_commands


class Eval(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="eval", description="""Evaluates a code""")
    @commands.is_owner()
    async def evall(self, ctx, *, body: str):
        self.bot.eval_wait = True
        try:
            await self.bot.websocket.send(json.dumps({'command': 'eval', 'content': body}).encode('utf-8'))
            msgs = []
            while True:
                try:
                    msg = await asyncio.wait_for(self.bot.responses.get(), timeout=3)
                except asyncio.TimeoutError:
                    break
                msgs.append(f'{msg["author"]}: {msg["response"]}')
            await ctx.send(' '.join(f'```py\n{m}\n```' for m in msgs))
        finally:
            self.bot.eval_wait = False

    @commands.hybrid_command(hidden=True, name='eval', description="""Evaluates a code""")
    @commands.is_owner()
    async def _eval(self, ctx, *, body: str):
        

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self.bot._last_result
        }

        env.update(globals())

        body = self.bot.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await ctx.send(f'```py\n{value}\n```')
            else:
                self.bot._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')


async def setup(bot):
    await bot.add_cog(Eval(bot))