import logging

from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # every commands needs owner permissions
    async def cog_check(self, ctx):
        return self.bot.owner == ctx.author

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Only the owner can use this module. Join the support discord server if you are having "
                           "any problems. This usage has been logged.")
            logger.warning(f'User {ctx.author} ({ctx.author.id}) has tried to access a restricted '
                           f'command via {ctx.message.content}.')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing a required argument for this command.")
        else:
            logger.warning(error)

    @commands.hybrid_command(aliases=['r'], description="Reloads cogs")
    async def reload(self, ctx, *, cog):
        if cog == 'c':
            cog = 'poll_controls'

        logger.info(f'Trying to reload cog: cogs.{cog}.')

        reply = ''
        try:
            await self.bot.reload_extension('cogs.'+cog)
            reply = f'Extension "cogs.{cog}" successfully reloaded.'
        except commands.ExtensionNotFound:
            reply = f'Extension "cogs.{cog}" not found.'
        except commands.NoEntryPointError:
            reply = f'Extension "cogs.{cog}" is missing a setup function.'
        except commands.ExtensionFailed:
            reply = f'Extension "cogs.{cog}" failed to start.'
        except commands.ExtensionNotLoaded:
            reply = f'Extension "cogs.{cog}" is not loaded... trying to load it. '
            try:
                await self.bot.load_extension('cogs.'+cog)
            except commands.ExtensionAlreadyLoaded:
                reply += f'Could not load or reload extension since it is already loaded...'
            except commands.ExtensionNotFound:
                reply += f'Extension "cogs.{cog}" not found.'
            except commands.ExtensionFailed:
                reply = f'Extension "cogs.{cog}" failed to start.'
        finally:
            logger.info(reply)
            await ctx.send(reply)


async def setup(bot):
    global logger
    logger = logging.getLogger('discord')
    await bot.add_cog(Admin(bot))