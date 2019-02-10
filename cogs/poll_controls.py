import copy
import logging
import discord

from discord.ext import commands
from .poll import Poll
from utils.paginator import embed_list_paginated
from essentials.multi_server import get_server_pre, ask_for_server, ask_for_channel
from essentials.settings import SETTINGS
from utils.poll_name_generator import generate_word
from essentials.exceptions import StopWizard


class PollControls:
    def __init__(self, bot):
        self.bot = bot

    # General Methods
    async def is_admin_or_creator(self, ctx, server, owner_id, error_msg=None):
        member = server.get_member(ctx.message.author.id)
        if member.id == owner_id:
            return True
        else:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role') in [r.name for r in member.roles]:
                return True
            else:
                if error_msg is not None:
                    await self.bot.send_message(ctx.message.author, error_msg)
                return False

    async def say_error(self, ctx, error_text, footer_text=None):
        embed = discord.Embed(title='', description=error_text, colour=SETTINGS.color)
        embed.set_author(name='Error', icon_url=SETTINGS.title_icon)
        if footer_text is not None:
            embed.set_footer(text=footer_text)
        await self.bot.say(embed=embed)

    async def say_embed(self, ctx, say_text='', title='Pollmaster', footer_text=None):
        embed = discord.Embed(title='', description=say_text, colour=SETTINGS.color)
        embed.set_author(name=title, icon_url=SETTINGS.title_icon)
        if footer_text is not None:
            embed.set_footer(text=footer_text)
        await self.bot.say(embed=embed)

    # Commands
    @commands.command(pass_context=True)
    async def activate(self, ctx, *, short=None):
        """Activate a prepared poll. Parameter: <label>"""
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.server)
            error = f'Please specify the label of a poll after the close command. \n' \
                    f'`{pre}activate <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, str(server.id), short)
            if p is not None:
                # check if already active, then just do nothing
                if await p.is_active():
                    return
                # Permission Check: Admin or Creator
                if not await self.is_admin_or_creator(
                        ctx, server,
                        p.author.id,
                        'You don\'t have sufficient rights to activate this poll. Please talk to the server admin.'
                ):
                    return

                # Activate Poll
                p.active = True
                if p.duration_type == 'timespan':
                    # add the the time between creation and activation to the duration
                    # -> "restart" the duration
                    p.duration += (p.get_activation_date() - p.time_created) / 60
                await p.save_to_db()
                await ctx.invoke(self.show, short)
            else:
                error = f'Poll with label "{short}" was not found.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command(pass_context=True)
    async def delete(self, ctx, *, short=None):
        '''Delete a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return
        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.server)
            error = f'Please specify the label of a poll after the close command. \n' \
                    f'`{pre}close <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, str(server.id), short)
            if p is not None:
                # Permission Check: Admin or Creator
                if not await self.is_admin_or_creator(
                        ctx, server,
                        p.author.id,
                        'You don\'t have sufficient rights to delete this poll. Please talk to the server admin.'
                ):
                    return False

                # Delete Poll
                result = await self.bot.db.polls.delete_one({'server_id': server.id, 'short': short})
                if result.deleted_count == 1:
                    say = f'Poll with label "{short}" was successfully deleted. This action can\'t be undone!'
                    title = 'Poll deleted'
                    await self.say_embed(ctx, say, title)
                else:
                    error = f'Action failed. Poll could not be deleted. You should probably report his error to the dev, thanks!`'
                    await self.say_error(ctx, error)

            else:
                error = f'Poll with label "{short}" was not found.'
                pre = await get_server_pre(self.bot, ctx.message.server)
                footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error, footer)

    @commands.command(pass_context=True)
    async def close(self, ctx, *, short=None):
        '''Close a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.server)
            error = f'Please specify the label of a poll after the close command. \n' \
                    f'`{pre}close <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, str(server.id), short)
            if p is not None:
                # Permission Check: Admin or Creator
                if not await self.is_admin_or_creator(
                        ctx, server,
                        p.author.id,
                        'You don\'t have sufficient rights to close this poll. Please talk to the server admin.'
                ):
                    return False

                # Close Poll
                p.open = False
                await p.save_to_db()
                await ctx.invoke(self.show, short)
            else:
                error = f'Poll with label "{short}" was not found.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command(pass_context=True)
    async def export(self, ctx, *, short=None):
        '''Export a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.server)
            error = f'Please specify the label of a poll after the close command. \n' \
                    f'`{pre}close <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, str(server.id), short)
            if p is not None:
                if p.open:
                    pre = await get_server_pre(self.bot, ctx.message.server)
                    error_text = f'You can only export closed polls. \nPlease `{pre}close {short}` the poll first or wait for the deadline.'
                    await self.say_error(ctx, error_text)
                else:
                    # sending file
                    file = await p.export()
                    if file is not None:
                        await self.bot.send_file(
                            ctx.message.author,
                            file,
                            content='Sending you the requested export of "{}".'.format(p.short)
                        )
                    else:
                        error_text = 'Could not export the requested poll. \nPlease report this to the developer.'
                        await self.say_error(ctx, error_text)
            else:
                error = f'Poll with label "{short}" was not found.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command(pass_context=True)
    async def show(self, ctx, short='open', start=0):
        '''Show a list of open polls or show a specific poll. Parameters: "open" (default), "closed", "prepared" or <label>'''

        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short in ['open', 'closed', 'prepared']:
            query = None
            if short == 'open':
                query = self.bot.db.polls.find({'server_id': str(server.id), 'open': True, 'active': True})
            elif short == 'closed':
                query = self.bot.db.polls.find({'server_id': str(server.id), 'open': False, 'active': True})
            elif short == 'prepared':
                query = self.bot.db.polls.find({'server_id': str(server.id), 'active': False})

            if query is not None:
                polls = [poll async for poll in query]
            else:
                return

            def item_fct(item):
                return f':black_small_square: **{item["short"]}**: {item["name"]}'

            title = f' Listing {short} polls'
            embed = discord.Embed(title='', description='', colour=SETTINGS.color)
            embed.set_author(name=title, icon_url=SETTINGS.title_icon)
            # await self.bot.say(embed=await self.embed_list_paginated(polls, item_fct, embed))
            # msg = await self.embed_list_paginated(ctx, polls, item_fct, embed, per_page=8)
            pre = await get_server_pre(self.bot, server)
            footer_text = ''  # f'type {pre}show <label> to display a poll.
            msg = await embed_list_paginated(self.bot, pre, polls, item_fct, embed, footer_prefix=footer_text,
                                             per_page=8)
        else:
            p = await Poll.load_from_db(self.bot, str(server.id), short)
            if p is not None:
                error_msg = 'This poll is inactive and you have no rights to display or view it.'
                if not await p.is_active() and not await self.is_admin_or_creator(ctx, server, p.author, error_msg):
                    return
                await p.post_embed()
            else:
                error = f'Poll with label {short} was not found.'
                pre = await get_server_pre(self.bot, server)
                footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error, footer)

    @commands.command(pass_context=True)
    async def quick(self, ctx, *, cmd=None):
        '''Create a quick poll with just a question and some options. Parameters: <Question> (optional)'''

        async def route(poll):
            await poll.set_name(force=cmd)
            await poll.set_short(force=str(await generate_word(self.bot, ctx.message.server.id)))
            await poll.set_anonymous(force='no')
            await poll.set_multiple_choice(force='no')
            await poll.set_options_reaction()
            await poll.set_roles(force='all')
            await poll.set_weights(force='none')
            await poll.set_duration(force='0')

        poll = await self.wizard(ctx, route)
        if poll:
            await poll.post_embed()

    @commands.command(pass_context=True)
    async def prepare(self, ctx, *, cmd=None):
        '''Prepare a poll to use later. Parameters: <Question> (optional) '''

        async def route(poll):
            await poll.set_name(force=cmd)
            await poll.set_short()
            await poll.set_preparation()
            await poll.set_anonymous()
            await poll.set_multiple_choice()
            if poll.reaction:
                await poll.set_options_reaction()
            else:
                await poll.set_options_traditional()
            await poll.set_roles()
            await poll.set_weights()
            await poll.set_duration()

        poll = await self.wizard(ctx, route)
        if poll:
            await poll.post_embed(destination=ctx.message.author)

    @commands.command(pass_context=True)
    async def new(self, ctx, *, cmd=None):
        '''Start the poll wizard to create a new poll step by step. Parameters: <Question> (optional) '''

        async def route(poll):
            await poll.set_name(force=cmd)
            await poll.set_short()
            await poll.set_anonymous()
            await poll.set_multiple_choice()
            if poll.reaction:
                await poll.set_options_reaction()
            else:
                await poll.set_options_traditional()
            await poll.set_roles()
            await poll.set_weights()
            await poll.set_duration()

        poll = await self.wizard(ctx, route)
        if poll:
            await poll.post_embed()

    # The Wizard!
    async def wizard(self, ctx, route):
        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return

        channel = await ask_for_channel(self.bot, server, ctx.message)
        if not channel:
            return

        # Permission Check
        member = server.get_member(ctx.message.author.id)
        result = await self.bot.db.config.find_one({'_id': str(server.id)})
        if result and result.get('admin_role') not in [r.name for r in member.roles] and result.get(
                'user_role') not in [r.name for r in member.roles]:
            await self.bot.send_message(ctx.message.author,
                                        'You don\'t have sufficient rights to start new polls on this server. Please talk to the server admin.')
            return

        ## Create object
        poll = Poll(self.bot, ctx, server, channel)

        ## Route to define object, passed as argument for different constructors
        try:
            await route(poll)
            poll.finalize()
        except StopWizard:
            return

        # Finalize
        await poll.save_to_db()
        return poll

    # BOT EVENTS (@bot.event)
    async def on_reaction_add(self, reaction, user):
        if user != self.bot.user:

            if reaction.emoji.startswith(('⏪', '⏩')):
                return

            # only look at our polls
            try:
                short = reaction.message.embeds[0]['author']['name'][3:]
                if not reaction.message.embeds[0]['author']['name'].startswith('>> ') or not short:
                    return
            except IndexError:
                return

            # create message object for the reaction
            user_msg = copy.deepcopy(reaction.message)
            user_msg.author = user

            server = await ask_for_server(self.bot, user_msg, short)
            if str(user_msg.channel.type) == 'private':
                user = server.get_member(user.id)
                user_msg.author = user

            # fetch poll
            p = await Poll.load_from_db(self.bot, server.id, short)
            if p is None:
                return

            # export
            if (reaction.emoji == '📎'):
                # sending file
                file = await p.export()
                if file is not None:
                    await self.bot.send_file(
                        user,
                        file,
                        content='Sending you the requested export of "{}".'.format(p.short)
                    )
                return

            # no rights, terminate function
            if not await p.has_required_role(user):
                await self.bot.remove_reaction(reaction.message, reaction.emoji, user)
                await self.bot.send_message(user, f'You are not allowed to vote in this poll. Only users with '
                                                  f'at least one of these roles can vote:\n{", ".join(p.roles)}')
                return

            # order here is crucial since we can't determine if a reaction was removed by the bot or user
            # update database with vote
            await p.vote(user, reaction.emoji, reaction.message)

            # check if we need to remove reactions (this will trigger on_reaction_remove)
            if str(reaction.message.channel.type) != 'private':
                if p.anonymous:
                    # immediately remove reaction
                    await self.bot.remove_reaction(reaction.message, reaction.emoji, user)
                elif not p.multiple_choice:
                    # remove all other reactions
                    for r in reaction.message.reactions:
                        if r != reaction:
                            await self.bot.remove_reaction(reaction.message, r.emoji, user)

    async def on_reaction_remove(self, reaction, user):
        if reaction.emoji.startswith(('⏪', '⏩')):
            return

        # only look at our polls
        try:
            short = reaction.message.embeds[0]['author']['name'][3:]
            if not reaction.message.embeds[0]['author']['name'].startswith('>> ') or not short:
                return
        except IndexError:
            return

        # create message object for the reaction
        user_msg = copy.deepcopy(reaction.message)
        user_msg.author = user

        server = await ask_for_server(self.bot, user_msg, short)
        if str(user_msg.channel.type) == 'private':
            user = server.get_member(user.id)
            user_msg.author = user

        # fetch poll
        p = await Poll.load_from_db(self.bot, server.id, short)
        if p is None:
            return
        if not p.anonymous:
            # for anonymous polls we can't unvote because we need to hide reactions
            await p.unvote(user, reaction.emoji, reaction.message)


def setup(bot):
    global logger
    logger = logging.getLogger('bot')
    bot.add_cog(PollControls(bot))
