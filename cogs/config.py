import discord
from discord.ext import commands

class Config:

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @commands.has_permissions(manage_server=True)
    async def prefix(self, ctx, *, pre):
        '''Set a custom prefix for the server.'''
        server = ctx.message.server
        # result = await self.bot.db.config.find_one({'_id': str(server_id)})
        # print(f'result: `{result}`')
        # if not result:
        #     await self.bot.db.config.insert_one({'_id': str(server_id)}, {'$set': {'_id': str(server_id), 'prefix': str(pre)}})
        #     self.bot.say(f'The server prefix has been set to `{pre}` Use `{pre}prefix <prefix>` to change it again.')
        #     return
        #result['prefix'] = str(pre)

        if pre.endswith('\w'):
            pre = pre[:-2]+' '
            msg = f'The server prefix has been set to `{pre}` Use `{pre}prefix <prefix>` to change it again.'
        else:
            msg = f'The server prefix has been set to `{pre}` Use `{pre}prefix <prefix>` to change it again. ' \
                  f'If you would like to add a trailing whitespace to the prefix, use `{pre}prefix {pre}\w`.'

        await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'prefix': str(pre)}}, upsert=True)
        await self.bot.say(msg)

    @commands.command(pass_context=True)
    @commands.has_permissions(manage_server=True)
    async def adminrole(self, ctx, *, role=None):
        '''Set or show the Admin Role. Members with this role can create polls and manage ALL polls. Parameter: <role> (optional)'''
        server = ctx.message.server

        if not role:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role'):
                await self.bot.say(f'The admin role restricts which users are able to create and manage ALL polls on this server. \n'
                                   f'The current admin role is `{result.get("admin_role")}`. '
                                   f'To change it type `{result.get("prefix")}adminrole <role name>`')
            else:
                await self.bot.say(f'The admin role restricts which users are able to create and manage ALL polls on this server.  \n'
                                   f'No admin role set. '
                                   f'To set one type `{result["prefix"]}adminrole <role name>`')
        elif role in [r.name for r in server.roles]:
            await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'admin_role': str(role)}}, upsert=True)
            await self.bot.say(f'Server role `{role}` can now manage all polls.')
        else:
            await self.bot.say(f'Server role `{role}` not found.')

    @commands.command(pass_context=True)
    @commands.has_permissions(manage_server=True)
    async def userrole(self, ctx, *, role=None):
        '''Set or show the User Role. Members with this role can create polls and manage their own polls. Parameter: <role> (optional)'''
        server = ctx.message.server

        if not role:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('user_role'):
                await self.bot.say(f'The user role restricts which users are able to create and manage their own polls.  \n'
                                   f'The current user role is `{result.get("user_role")}`. '
                                   f'To change it type `{result.get("prefix")}userrole <role name>`')
            else:
                await self.bot.say(f'The user role restricts which users are able to create and manage their own polls.  \n'
                                   f'No user role set. '
                                   f'To set one type `{result.get("prefix")}userrole <role name>`')
        elif role in [r.name for r in server.roles]:
            await self.bot.db.config.update_one({'_id': str(server.id)}, {'$set': {'user_role': str(role)}}, upsert=True)
            await self.bot.say(f'Server role `{role}` can now create and manage their own polls.')
        else:
            await self.bot.say(f'Server role `{role}` not found.')

def setup(bot):
    bot.add_cog(Config(bot))