import logging
from discord.ext import commands
from discord import app_commands
from discord import Role

class Config(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="prefix", description="""Set a custom prefix for the server.""")
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx, *, pre:str):
        server = ctx.message.guild
        if pre.endswith('\w'):
            pre = pre[:-2]+' '
            if len(pre.strip) > 0:
                msg = f'The server prefix has been set to `{pre}` Use `{pre}prefix <prefix>` to change it again.'
            else:
                await ctx.send('Invalid prefix.')
                return
        else:
            msg = f'The server prefix has been set to `{pre}` Use `{pre}prefix <prefix>` to change it again. ' \
                  f'If you would like to add a trailing whitespace to the prefix, use `{pre}prefix {pre}\w`.'

        await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'prefix': str(pre)}}, upsert=True)
        self.bot.pre[str(server.id)] = str(pre)
        await ctx.send(msg)

    @commands.hybrid_command(name="adminrole", description="Set or show the Admin Role. Members with this role can create polls and manage ALL polls.")
    @commands.has_permissions(manage_guild=True)
    async def adminrole(self, ctx, *, role: Role = None):
        server = ctx.message.guild

        if not role:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role'):
                await ctx.send(f'The admin role restricts which users are able to create and manage ALL polls on this server. \n'
                                   f'The current admin role is `{result.get("admin_role")}`. '
                                   f'To change it type `{result.get("prefix")}adminrole <role name>`')
            else:
                await ctx.send(f'The admin role restricts which users are able to create and manage ALL polls on this server.  \n'
                                   f'No admin role set. '
                                   f'To set one type `{result.get("prefix")}adminrole <role name>`')
        elif role in [r.name for r in server.roles]:
            await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'admin_role': str(role)}}, upsert=True)
            await ctx.send(f'Server role `{role}` can now manage all polls.')
        else:
            await ctx.send(f'Server role `{role}` not found.')

    @commands.hybrid_command(name="userrole", description="Set or show the User Role. Members with this role can create polls and manage their own polls.")
    @commands.has_permissions(manage_guild=True)
    async def userrole(self, ctx, *, role: Role=None):
        
        server = ctx.message.guild

        if not role:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('user_role'):
                await ctx.send(f'The user role restricts which users are able to create and manage their own polls.  \n'
                                   f'The current user role is `{result.get("user_role")}`. '
                                   f'To change it type `{result.get("prefix")}userrole <role name>`')
            else:
                await ctx.send(f'The user role restricts which users are able to create and manage their own polls.  \n'
                                   f'No user role set. '
                                   f'To set one type `{result.get("prefix")}userrole <role name>`')
        elif role in [r.name for r in server.roles]:
            await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'user_role': str(role)}}, upsert=True)
            await ctx.send(f'Server role `{role}` can now create and manage their own polls.')
        else:
            await ctx.send(f'Server role `{role}` not found.')


async def setup(bot):
    global logger
    logger = logging.getLogger('discord')
    await bot.add_cog(Config(bot))