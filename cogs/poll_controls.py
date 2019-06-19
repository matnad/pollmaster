import argparse
import asyncio
import datetime
import logging
import re
import shlex

import discord
import pytz

from discord.ext import commands

from utils.misc import CustomFormatter
from models.poll import Poll
from utils.paginator import embed_list_paginated
from essentials.multi_server import get_server_pre, ask_for_server, ask_for_channel
from essentials.settings import SETTINGS
from utils.poll_name_generator import generate_word
from essentials.exceptions import StopWizard

# A-Z Emojis for Discord
AZ_EMOJIS = [(b'\\U0001f1a'.replace(b'a', bytes(hex(224 + (6 + i))[2:], "utf-8"))).decode("unicode-escape") for i in
             range(26)]


class PollControls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.close_polls())
        self.ignore_next_removed_reaction = {}

    # # General Methods

    def get_label(self, message: discord.Message):
        label = None
        if message and message.embeds:
            embed = message.embeds[0]
            label_object = embed.author
            if label_object:
                label_full = label_object.name
                if label_full and label_full.startswith('>> '):
                    label = label_full[3:]
        return label

    async def close_polls(self):
        """This function runs every 60 seconds to schedule prepared polls and close expired polls"""
        while True:
            try:
                if not hasattr(self.bot, 'db'):
                    await asyncio.sleep(30)
                    continue

                query = self.bot.db.polls.find({'active': False, 'activation': {"$not": re.compile("0")}})
                if query:
                    for pd in [poll async for poll in query]:
                        p = Poll(self.bot, load=True)
                        await p.from_dict(pd)
                        if not p.server:
                            continue
                        if p.active:
                            try:
                                await p.channel.send('This poll has been scheduled and is active now!')
                                await p.post_embed(p.channel)
                            except:
                                continue

                query = self.bot.db.polls.find({'open': True, 'duration': {"$not": re.compile("0")}})
                if query:
                    for pd in [poll async for poll in query]:
                        p = Poll(self.bot, load=True)
                        await p.from_dict(pd)
                        if not p.server:
                            continue
                        if not p.open:
                            try:
                                await p.channel.send('This poll has reached the deadline and is closed!')
                                await p.post_embed(p.channel)
                            except:
                                continue
            except AttributeError as ae:
                # Database not loaded yet
                logger.warning("Attribute Error in close_polls loop")
                logger.exception(ae)
                pass
            except Exception as ex:
                # Never break this loop due to an error
                logger.error("Other Error in close_polls loop")
                logger.exception(ex)
                pass

            await asyncio.sleep(60)

    def get_lock(self, server_id):
        if not self.bot.locks.get(server_id):
            self.bot.locks[server_id] = asyncio.Lock()
        return self.bot.locks.get(server_id)

    async def is_admin_or_creator(self, ctx, server, owner_id, error_msg=None):
        member = server.get_member(ctx.message.author.id)
        if member.id == owner_id:
            return True
        elif member.guild_permissions.manage_guild:
            return True
        else:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role') in [r.name for r in member.roles]:
                return True
            else:
                if error_msg is not None:
                    await ctx.send(ctx.message.author, error_msg)
                return False

    async def say_error(self, ctx, error_text, footer_text=None):
        embed = discord.Embed(title='', description=error_text, colour=SETTINGS.color)
        embed.set_author(name='Error', icon_url=SETTINGS.author_icon)
        if footer_text is not None:
            embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

    async def say_embed(self, ctx, say_text='', title='Pollmaster', footer_text=None):
        embed = discord.Embed(title='', description=say_text, colour=SETTINGS.color)
        embed.set_author(name=title, icon_url=SETTINGS.author_icon)
        if footer_text is not None:
            embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

    # Commands
    @commands.command()
    async def activate(self, ctx, *, short=None):
        """Activate a prepared poll. Parameter: <label>"""
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.guild)
            error = f'Please specify the label of a poll after the activate command. \n' \
                    f'`{pre}activate <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
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
                await p.save_to_db()
                await ctx.invoke(self.show, short)
            else:
                error = f'Poll with label "{short}" was not found. Listing prepared polls.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show, 'prepared')

    @commands.command()
    async def delete(self, ctx, *, short=None):
        '''Delete a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return
        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.guild)
            error = f'Please specify the label of a poll after the delete command. \n' \
                    f'`{pre}delete <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
            if p is not None:
                # Permission Check: Admin or Creator
                if not await self.is_admin_or_creator(
                        ctx, server,
                        p.author.id,
                        'You don\'t have sufficient rights to delete this poll. Please talk to the server admin.'
                ):
                    return False

                # Delete Poll
                result = await self.bot.db.polls.delete_one({'server_id': str(server.id), 'short': short})
                if result.deleted_count == 1:
                    say = f'Poll with label "{short}" was successfully deleted. This action can\'t be undone!'
                    title = 'Poll deleted'
                    await self.say_embed(ctx, say, title)
                else:
                    error = f'Action failed. Poll could not be deleted. You should probably report his error to the dev, thanks!'
                    await self.say_error(ctx, error)

            else:
                error = f'Poll with label "{short}" was not found.'
                pre = await get_server_pre(self.bot, ctx.message.guild)
                footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error, footer)

    @commands.command()
    async def close(self, ctx, *, short=None):
        '''Close a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.guild)
            error = f'Please specify the label of a poll after the close command. \n' \
                    f'`{pre}close <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
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
                error = f'Poll with label "{short}" was not found. Listing all open polls.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command()
    async def copy(self, ctx, *, short=None):
        '''Copy a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.guild)
            error = f'Please specify the label of a poll after the copy command. \n' \
                    f'`{pre}copy <poll_label>`'
            await self.say_error(ctx, error)

        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
            if p is not None:
                text = await get_server_pre(self.bot, server) + p.to_command()
                await self.say_embed(ctx, text, title="Paste this to create a copy of the poll")
            else:
                error = f'Poll with label "{short}" was not found. Listing all open polls.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command()
    async def export(self, ctx, *, short=None):
        '''Export a poll. Parameter: <label>'''
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return

        if short is None:
            pre = await get_server_pre(self.bot, ctx.message.guild)
            error = f'Please specify the label of a poll after the export command. \n' \
                    f'`{pre}export <poll_label>`'
            await self.say_error(ctx, error)
        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
            if p is not None:
                if p.open:
                    pre = await get_server_pre(self.bot, ctx.message.guild)
                    error_text = f'You can only export closed polls. \nPlease `{pre}close {short}` the poll first or wait for the deadline.'
                    await self.say_error(ctx, error_text)
                else:
                    # sending file
                    file_name = await p.export()
                    if file_name is not None:
                        await ctx.message.author.send('Sending you the requested export of "{}".'.format(p.short),
                                                      file=discord.File(file_name)
                                                      )
                        # await self.bot.send_file(
                        #     ctx.message.author,
                        #     file_name,
                        #     content='Sending you the requested export of "{}".'.format(p.short)
                        # )
                    else:
                        error_text = 'Could not export the requested poll. \nPlease report this to the developer.'
                        await self.say_error(ctx, error_text)
            else:
                error = f'Poll with label "{short}" was not found.'
                # pre = await get_server_pre(self.bot, ctx.message.server)
                # footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error)
                await ctx.invoke(self.show)

    @commands.command()
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
                # sort by newest first
                polls = [poll async for poll in query.sort('_id', -1)]
            else:
                return

            def item_fct(i, item):
                return f':black_small_square: **{item["short"]}**: {item["name"]}'

            title = f' Listing {short} polls'
            embed = discord.Embed(title='', description='', colour=SETTINGS.color)
            embed.set_author(name=title, icon_url=SETTINGS.author_icon)
            # await self.bot.say(embed=await self.embed_list_paginated(polls, item_fct, embed))
            # msg = await self.embed_list_paginated(ctx, polls, item_fct, embed, per_page=8)
            pre = await get_server_pre(self.bot, server)
            footer_text = f'type {pre}show <label> to display a poll. '
            msg = await embed_list_paginated(ctx, self.bot, pre, polls, item_fct, embed, footer_prefix=footer_text,
                                             per_page=10)
        else:
            p = await Poll.load_from_db(self.bot, server.id, short)
            if p is not None:
                error_msg = 'This poll is inactive and you have no rights to display or view it.'
                if not await p.is_active() and not await self.is_admin_or_creator(ctx, server, p.author, error_msg):
                    return
                await p.post_embed(ctx)
            else:
                error = f'Poll with label {short} was not found.'
                pre = await get_server_pre(self.bot, server)
                footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error, footer)

    @commands.command()
    async def cmd(self, ctx, *, cmd=None):
        '''The old, command style way paired with the wizard.'''
        # await self.say_embed(ctx, say_text='This command is temporarily disabled.')

        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return
        pre = await get_server_pre(self.bot, server)
        try:
            # generate the argparser and handle invalid stuff
            descr = 'Accept poll settings via commandstring. \n\n' \
                    '**Wrap all arguments in quotes like this:** \n' \
                    f'{pre}cmd -question \"What tea do you like?\" -o \"green, black, chai\"\n\n' \
                    'The Order of arguments doesn\'t matter. If an argument is missing, it will use the default value. ' \
                    'If an argument is invalid, the wizard will step in. ' \
                    'If the command string is invalid, you will get this error :)'
            parser = argparse.ArgumentParser(description=descr, formatter_class=CustomFormatter, add_help=False)
            parser.add_argument('-question', '-q')
            parser.add_argument('-label', '-l', default=str(await generate_word(self.bot, server.id)))
            parser.add_argument('-anonymous', '-a', action="store_true")
            parser.add_argument('-options', '-o')
            parser.add_argument('-survey_flags', '-sf', default='0')
            parser.add_argument('-multiple_choice', '-mc', default='1')
            parser.add_argument('-hide_votes', '-h', action="store_true")
            parser.add_argument('-roles', '-r', default='all')
            parser.add_argument('-weights', '-w', default='none')
            parser.add_argument('-prepare', '-p', default='-1')
            parser.add_argument('-deadline', '-d', default='0')

            helpstring = parser.format_help()
            helpstring = helpstring.replace("pollmaster.py", f"{pre}cmd ")

            if not cmd or len(cmd) < 2 or cmd == 'help':
                # Shlex will block if the string is empty
                await self.say_embed(ctx, say_text=helpstring)
                return

            try:
                cmd = cmd.rep45lace('“', '"')  # fix for iphone keyboard
                cmd = cmd.rep45lace('”', '"')  # fix for iphone keyboard
                cmds = shlex.split(cmd)
            except ValueError:
                await self.say_error(ctx, error_text=helpstring)
                return
            except:
                return

            try:
                args, unknown_args = parser.parse_known_args(cmds)
            except SystemExit:
                await self.say_error(ctx, error_text=helpstring)
                return
            except:
                return

            if unknown_args:
                error_text = f'**There was an error reading the command line options!**.\n' \
                             f'Most likely this is because you didn\'t surround the arguments with double quotes like this: ' \
                             f'`{pre}cmd -q "question of the poll" -o "yes, no, maybe"`' \
                             f'\n\nHere are the arguments I could not understand:\n'
                error_text += '`'+'\n'.join(unknown_args)+'`'
                error_text += f'\n\nHere are the arguments which are ok:\n'
                error_text += '`' + '\n'.join([f'{k}: {v}' for k, v in vars(args).items()]) + '`'

                await self.say_error(ctx, error_text=error_text, footer_text=f'type `{pre}cmd help` for details.')
                return

            # pass arguments to the wizard
            async def route(poll):
                await poll.set_name(ctx, force=args.question)
                await poll.set_short(ctx, force=args.label)
                await poll.set_anonymous(ctx, force=f'{"yes" if args.anonymous else "no"}')
                await poll.set_options_reaction(ctx, force=args.options)
                await poll.set_survey_flags(ctx, force=args.survey_flags)
                await poll.set_multiple_choice(ctx, force=args.multiple_choice)
                await poll.set_hide_vote_count(ctx, force=f'{"yes" if args.hide_votes else "no"}')
                await poll.set_roles(ctx, force=args.roles)
                await poll.set_weights(ctx, force=args.weights)
                await poll.set_preparation(ctx, force=args.prepare)
                await poll.set_duration(ctx, force=args.deadline)

            poll = await self.wizard(ctx, route, server)
            if poll:
                await poll.post_embed(poll.channel)

        except Exception as error:
            logger.error("ERROR IN pm!cmd")
            logger.exception(error)


    @commands.command()
    async def quick(self, ctx, *, cmd=None):
        '''Create a quick poll with just a question and some options. Parameters: <Question> (optional)'''
        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return

        async def route(poll):
            await poll.set_name(ctx, force=cmd)
            await poll.set_short(ctx, force=str(await generate_word(self.bot, server.id)))
            await poll.set_anonymous(ctx, force='no')
            await poll.set_options_reaction(ctx)
            await poll.set_multiple_choice(ctx, force='1')
            await poll.set_hide_vote_count(ctx, force='no')
            await poll.set_roles(ctx, force='all')
            await poll.set_weights(ctx, force='none')
            await poll.set_duration(ctx, force='0')

        poll = await self.wizard(ctx, route, server)
        if poll:
            await poll.post_embed(poll.channel)

    @commands.command()
    async def prepare(self, ctx, *, cmd=None):
        """Prepare a poll to use later. Parameters: <Question> (optional)"""
        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return

        async def route(poll):
            await poll.set_name(ctx, force=cmd)
            await poll.set_short(ctx)
            await poll.set_preparation(ctx)
            await poll.set_anonymous(ctx)
            await poll.set_options_reaction(ctx)
            await poll.set_survey_flags(ctx)
            await poll.set_multiple_choice(ctx)
            await poll.set_hide_vote_count(ctx)
            await poll.set_roles(ctx)
            await poll.set_weights(ctx)
            await poll.set_duration(ctx)

        poll = await self.wizard(ctx, route, server)
        if poll:
            await poll.post_embed(ctx.message.author)

    @commands.command()
    async def advanced(self, ctx, *, cmd=None):
        """Poll with more options. Parameters: <Question> (optional)"""
        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return

        async def route(poll):
            await poll.set_name(ctx, force=cmd)
            await poll.set_short(ctx)
            await poll.set_anonymous(ctx)
            await poll.set_options_reaction(ctx)
            await poll.set_survey_flags(ctx)
            await poll.set_multiple_choice(ctx)
            await poll.set_hide_vote_count(ctx)
            await poll.set_roles(ctx)
            await poll.set_weights(ctx)
            await poll.set_duration(ctx)

        poll = await self.wizard(ctx, route, server)
        if poll:
            await poll.post_embed(poll.channel)

    @commands.command()
    async def new(self, ctx, *, cmd=None):
        """Start the poll wizard to create a new poll step by step. Parameters: <Question> (optional)"""
        server = await ask_for_server(self.bot, ctx.message)
        if not server:
            return

        async def route(poll):
            await poll.set_name(ctx, force=cmd)
            await poll.set_short(ctx)
            await poll.set_anonymous(ctx)
            await poll.set_options_reaction(ctx)
            await poll.set_survey_flags(ctx, force='0')
            await poll.set_multiple_choice(ctx)
            await poll.set_hide_vote_count(ctx, force='no')
            await poll.set_roles(ctx, force='all')
            await poll.set_weights(ctx, force='none')
            await poll.set_duration(ctx)

        poll = await self.wizard(ctx, route, server)
        if poll:
            await poll.post_embed(poll.channel)

    # The Wizard!
    async def wizard(self, ctx, route, server):
        channel = await ask_for_channel(ctx, self.bot, server, ctx.message)
        if not channel:
            return

        pre = await get_server_pre(self.bot, server)

        # Permission Check
        member = server.get_member(ctx.message.author.id)
        if not member.guild_permissions.manage_guild:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role') not in [r.name for r in member.roles] and result.get(
                    'user_role') not in [r.name for r in member.roles]:
                await ctx.message.author.send('You don\'t have sufficient rights to start new polls on this server. '
                                            'A server administrator has to assign the user or admin role to you. '
                                            f'To view and set the permissions, an admin can use `{pre}userrole` and '
                                            f'`{pre}adminrole`')
                return

        ## Create object
        poll = Poll(self.bot, ctx, server, channel)

        ## Route to define object, passed as argument for different constructors
        if ctx.message and ctx.message.content and not ctx.message.content.startswith(f'{pre}cmd '):
            poll.wizard_messages.append(ctx.message)
        try:
            await route(poll)
            poll.finalize()
            await poll.clean_up(ctx.channel)
        except StopWizard:
            await poll.clean_up(ctx.channel)
            return

        # Finalize
        await poll.save_to_db()
        return poll

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, data):
        # get emoji symbol
        emoji = data.emoji
        if emoji:
            emoji = emoji.name
        if not emoji:
            return

        # check if removed by the bot.. this is a bit hacky but discord doesn't provide the correct info...
        message_id = data.message_id
        user_id = data.user_id
        if self.ignore_next_removed_reaction.get(str(message_id) + str(emoji)) == user_id:
            del self.ignore_next_removed_reaction[str(message_id) + str(emoji)]
            return

        # check if we can find a poll label
        message_id = data.message_id
        channel_id = data.channel_id
        channel = self.bot.get_channel(channel_id)

        if isinstance(channel, discord.TextChannel):
            server = channel.guild
            user = server.get_member(user_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
        elif isinstance(channel, discord.DMChannel):
            user = await self.bot.fetch_user(user_id)  # only do this once
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)

        elif not channel:
            # discord rapidly closes dm channels by desing
            # put private channels back into the bots cache and try again
            user = await self.bot.fetch_user(user_id)  # only do this once
            await user.create_dm()
            channel = self.bot.get_channel(channel_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)
        else:
            return

        # this is exclusive
        lock = self.get_lock(server.id)
        async with lock:
            p = await Poll.load_from_db(self.bot, server.id, label)
            if not isinstance(p, Poll):
                return
            if not p.anonymous:
                # for anonymous polls we can't unvote because we need to hide reactions
                await p.unvote(user, emoji, message, lock)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, data):
        # dont look at bot's own reactions
        user_id = data.user_id
        if user_id == self.bot.user.id:
            return

        # get emoji symbol
        emoji = data.emoji
        if emoji:
            emoji = emoji.name
        if not emoji:
            return

        # check if we can find a poll label
        message_id = data.message_id
        channel_id = data.channel_id
        channel = self.bot.get_channel(channel_id)

        if isinstance(channel, discord.TextChannel):
            server = channel.guild
            user = server.get_member(user_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
        elif isinstance(channel, discord.DMChannel):
            user = await self.bot.fetch_user(user_id)  # only do this once
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)

        elif not channel:
            # discord rapidly closes dm channels by desing
            # put private channels back into the bots cache and try again
            user = await self.bot.fetch_user(user_id)  # only do this once
            await user.create_dm()
            channel = self.bot.get_channel(channel_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(id=message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)
        else:
            return

        # fetch poll
        # create message object for the reaction sender, to get correct server
        # user_msg = copy.deepcopy(message)
        # user_msg.author = user
        # server = await ask_for_server(self.bot, user_msg, label)

        # this is exclusive to keep database access sequential
        # hopefully it will scale well enough or I need a different solution
        lock = self.get_lock(server.id)
        async with lock:
            p = await Poll.load_from_db(self.bot, server.id, label)
            if not isinstance(p, Poll):
                return

            # export
            if emoji == '📎':
                # sending file
                file_name = await p.export()
                if file_name is not None:
                    await user.send('Sending you the requested export of "{}".'.format(p.short),
                                              file=discord.File(file_name)
                                              )
                return

            # info
            member = server.get_member(user_id)
            if emoji == '❔':
                is_open = await p.is_open()
                embed = discord.Embed(title=f"Info for the {'CLOSED ' if not is_open else ''}poll \"{p.name}\"",
                                      description='', color=SETTINGS.color)
                embed.set_author(name=f" >> {p.short}", icon_url=SETTINGS.author_icon)

                # created by
                created_by = server.get_member(int(p.author.id))
                embed.add_field(name=f'Created by:', value=f'{created_by if created_by else "<Deleted User>"}', inline=False)

                # vote rights
                vote_rights = await p.has_required_role(member)
                embed.add_field(name=f'{"Can you vote?" if is_open else "Could you vote?"}',
                                value=f'{"✅" if vote_rights else "❎"}', inline=False)

                # edit rights
                edit_rights = False
                if str(member.id) == str(p.author.id):
                    edit_rights = True
                elif member.guild_permissions.manage_guild:
                    edit_rights = True
                else:
                    result = await self.bot.db.config.find_one({'_id': str(server.id)})
                    if result and result.get('admin_role') in [r.name for r in member.roles]:
                        edit_rights = True
                embed.add_field(name='Can you manage the poll?', value=f'{"✅" if edit_rights else "❎"}', inline=False)

                # choices
                choices = 'You have not voted yet.' if vote_rights else 'You can\'t vote in this poll.'
                if str(user.id) in p.votes:
                    if p.votes[str(user.id)]['choices'].__len__() > 0:
                        choices = ', '.join([p.options_reaction[c] for c in p.votes[str(user.id)]['choices']])
                embed.add_field(
                    name=f'{"Your current votes (can be changed as long as the poll is open):" if is_open else "Your final votes:"}',
                    value=choices, inline=False)

                # weight
                if vote_rights:
                    weight = 1
                    if p.weights_roles.__len__() > 0:
                        valid_weights = [p.weights_numbers[p.weights_roles.index(r)] for r in
                                         list(set([n.name for n in member.roles]).intersection(set(p.weights_roles)))]
                        if valid_weights.__len__() > 0:
                            weight = max(valid_weights)
                else:
                    weight = 'You can\'t vote in this poll.'
                embed.add_field(name='Weight of your votes:', value=weight, inline=False)

                # time left
                deadline = p.get_duration_with_tz()
                if not is_open:
                    time_left = 'This poll is closed.'
                elif deadline == 0:
                    time_left = 'Until manually closed.'
                else:
                    time_left = str(deadline - datetime.datetime.utcnow().replace(tzinfo=pytz.utc)).split('.', 2)[0]

                embed.add_field(name='Time left in the poll:', value=time_left, inline=False)

                await user.send(embed=embed)

                # send current details of who currently voted for what
                if (not p.open or not p.hide_count) and not p.anonymous and p.votes.__len__() > 0:
                    msg = '--------------------------------------------\n' \
                              'CURRENT VOTES\n' \
                              '--------------------------------------------\n'
                    for i, o in enumerate(p.options_reaction):
                        if not p.options_reaction_default:
                            msg += AZ_EMOJIS[i] + " "
                        msg += "**" +o+":**"
                        c = 0
                        for user_id in p.votes:
                            member = server.get_member(int(user_id))
                            if not member or i not in p.votes[str(user_id)]['choices']:
                                continue
                            c += 1
                            name = member.nick
                            if not name:
                                name = member.name
                            if not name:
                                name = "<Deleted User>"
                            msg += f'\n{name}'
                            if p.votes[str(user_id)]['weight'] != 1:
                                msg += f' (weight: {p.votes[str(user_id)]["weight"]})'
                            # msg += ': ' + ', '.join([AZ_EMOJIS[c]+" "+p.options_reaction[c] for c in p.votes[user_id]['choices']])
                            if i in p.survey_flags:
                                msg += f': {p.votes[str(user_id)]["answers"][p.survey_flags.index(i)]}'
                            if msg.__len__() > 1500:
                                await user.send(msg)
                                msg = ''
                        if c == 0:
                            msg += '\nNo votes for this option yet.'
                        msg += '\n\n'

                    if msg.__len__() > 0:
                        await user.send(msg)
                elif (not p.open or not p.hide_count) and p.anonymous and p.survey_flags.__len__() > 0 and p.votes.__len__() > 0:
                    msg = '--------------------------------------------\n' \
                          'Custom Answers (Anonymous)\n' \
                          '--------------------------------------------\n'
                    has_answers = False
                    for i, o in enumerate(p.options_reaction):
                        if i not in p.survey_flags:
                            continue
                        custom_answers = ''
                        for user_id in p.votes:
                            if i in p.votes[str(user_id)]["choices"]:
                                has_answers = True
                                custom_answers += f'\n{p.votes[str(user_id)]["answers"][p.survey_flags.index(i)]}'
                        if custom_answers.__len__() > 0:
                            msg += AZ_EMOJIS[i] + " "
                            msg += "**" + o + ":**"
                            msg += custom_answers
                            msg += '\n\n'
                        if msg.__len__() > 1500:
                            await user.send(msg)
                            msg = ''
                    if has_answers and msg.__len__() > 0:
                        await user.send(msg)
                return

            # Assume: User wants to vote with reaction
            # no rights, terminate function
            if not await p.has_required_role(member):
                await message.remove_reaction(emoji, user)
                await member.send(f'You are not allowed to vote in this poll. Only users with '
                                  f'at least one of these roles can vote:\n{", ".join(p.roles)}')
                return

            # check if we need to remove reactions (this will trigger on_reaction_remove)
            if not isinstance(channel, discord.DMChannel) and p.anonymous:
                # immediately remove reaction and to be safe, remove all reactions
                self.ignore_next_removed_reaction[str(message.id) + str(emoji)] = user_id
                asyncio.ensure_future(message.remove_reaction(emoji, user))

            # order here is crucial since we can't determine if a reaction was removed by the bot or user
            # update database with vote
            await p.vote(member, emoji, message, lock)

            # cant do this until we figure out how to see who removed the reaction?
            # for now MC 1 is like MC x
            # if isinstance(channel, discord.TextChannel) and p.multiple_choice == 1:
            #     # remove all other reactions
            #     # if lock._waiters.__len__() == 0:
            #     for r in message.reactions:
            #         if r.emoji and r.emoji != emoji:
            #             await message.remove_reaction(r.emoji, user)
            #     pass


def setup(bot):
    global logger
    logger = logging.getLogger('bot')
    bot.add_cog(PollControls(bot))
