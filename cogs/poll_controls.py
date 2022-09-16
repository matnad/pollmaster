import argparse
import datetime
import logging
import random
import shlex
import time
from string import ascii_lowercase

import discord
import pytz
from bson import ObjectId
from discord.ext import tasks, commands
from discord import app_commands
from essentials.exceptions import StopWizard
from essentials.multi_server import get_server_pre, ask_for_server, ask_for_channel
from essentials.settings import SETTINGS
from models.poll import Poll
from utils.misc import CustomFormatter
from utils.paginator import embed_list_paginated
from utils.poll_name_generator import generate_word

# A-Z Emojis for Discord
AZ_EMOJIS = [(b'\\U0001f1a'.replace(b'a', bytes(hex(224 + (6 + i))[2:], "utf-8"))).decode("unicode-escape") for i in
             range(26)]


class PollControls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ignore_next_removed_reaction = {}
        self.index = 0
        self.close_activate_polls.add_exception_type(KeyError)
        self.close_activate_polls.start()
        self.refresh_queue.start()

    def cog_unload(self):
        self.close_activate_polls.cancel()
        self.refresh_queue.cancel()

    # noinspection PyCallingNonCallable
    @tasks.loop(seconds=30)
    async def close_activate_polls(self):
        if hasattr(self.bot, 'db') and hasattr(self.bot.db, 'polls'):
            utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

            # auto-close polls
            query = self.bot.db.polls.find({'open': True, 'duration': {
                '$gte': utc_now - datetime.timedelta(weeks=8),
                '$lte': utc_now + datetime.timedelta(minutes=1)
            }})
            if query:
                for limit, pd in enumerate([poll async for poll in query]):
                    if limit >= 30:
                        print("More than 30 polls due to be closed! Throttling to 30 per 30 sec.")
                        logger.warning("More than 30 polls due to be closed! Throttling to 30 per 30 sec.")
                        break

                    # load poll (this will close the poll if necessary and update the DB)
                    p = Poll(self.bot, load=True)
                    if not p:
                        continue
                    await p.from_dict(pd)

                    # Check if Pollmaster is still present on the server
                    if not p.server:
                        # Bot is not present on that server. Close poll directly in the DB.
                        await self.bot.db.polls.update_one({'_id': p.id}, {'$set': {'open': False}})
                        logger.info(f"Closed poll on a server ({pd['server_id']}) without Pollmaster being present.")
                        continue
                    # Check if poll was closed and inform the sever if the poll is less than 2 hours past due
                    # (Closing old polls should only happen if the bot was offline for an extended period)
                    if not p.open:
                        if p.duration.replace(tzinfo=pytz.utc) >= utc_now - datetime.timedelta(hours=2):
                            # only send messages for polls that were supposed to expire in the past 2 hours
                            await p.channel.send('This poll has reached the deadline and is closed!')
                            await p.post_embed(p.channel)
                        else:
                            logger.info(f"Closing old poll: {p.id}")

            # auto-activate polls
            query = self.bot.db.polls.find({'active': False, 'activation': {
                '$gte': utc_now - datetime.timedelta(weeks=8),
                '$lte': utc_now + datetime.timedelta(minutes=1)
            }})
            if query:
                for limit, pd in enumerate([poll async for poll in query]):
                    if limit >= 10:
                        print("More than 10 polls due to be closed! Throttling to 10 per 30 sec.")
                        logger.warning("More than 10 polls due to be closed! Throttling to 10 per 30 sec.")
                        break

                    # load poll (this will activate the poll if necessary and update the DB)
                    p = Poll(self.bot, load=True)
                    await p.from_dict(pd)

                    # Check if Pollmaster is still present on the server
                    if not p.server:
                        # Bot is not present on that server. Close poll directly in the DB.
                        await self.bot.db.polls.update_one({'_id': p.id}, {'$set': {'active': True}})
                        logger.info(f"Activated poll on a server ({pd['server_id']}) without Pollmaster being present.")
                        continue
                    # Check if poll was activated and inform the sever if the poll is less than 2 hours past due
                    # (activating old polls should only happen if the bot was offline for an extended period)
                    if p.active:
                        if p.activation.replace(tzinfo=pytz.utc) >= utc_now - datetime.timedelta(hours=2):
                            # only send messages for polls that were supposed to expire in the past 2 hours
                            await p.channel.send('This poll has been scheduled and is active now!')
                            await p.post_embed(p.channel)
                        else:
                            logger.info(f"Activating old poll: {p.id}")

    @close_activate_polls.before_loop
    async def before_close_activate_polls(self):
        # print('close task waiting...')
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=5)
    async def refresh_queue(self):
        remove_list = []
        for pid, t in self.bot.refresh_blocked.items():
            if t - time.time() < 0:
                remove_list.append(pid)
                if self.bot.refresh_queue.get(pid, False):
                    query = await self.bot.db.polls.find_one({'_id': ObjectId(pid)})
                    if query:
                        p = Poll(self.bot, load=True)
                        if p:
                            await p.from_dict(query)
                            await p.refresh(self.bot.refresh_queue.get(pid))
                            del self.bot.refresh_queue[pid]

        # don't change dict while iterating
        for pid in remove_list:
            del self.bot.refresh_blocked[pid]

    @refresh_queue.before_loop
    async def before_refresh_queue(self):
        # print('refresh task waiting...')
        await self.bot.wait_until_ready()

    # General Methods
    @staticmethod
    def get_label(message: discord.Message):
        label = None
        if message and message.embeds:
            embed = message.embeds[0]
            label_object = embed.author
            if label_object:
                label_full = label_object.name
                if label_full and label_full.startswith('>> '):
                    label = label_full[3:]
        return label

    async def is_admin_or_creator(self, ctx, server, owner_id, error_msg=None):
        member = ctx.author
        # member = server.get_member(ctx.message.author.id)
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
                    await ctx.message.author.send(error_msg)
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
    # @commands.command()
    # async def t(self, ctx, *, test=None):
    #     """TEST"""
    #     server = await ask_for_server(self.bot, ctx.message)
    #     if not server:
    #         return
    #     p = await Poll.load_from_db(self.bot, str(server.id), 'test', ctx=ctx)
    #     print(await Vote.load_number_of_voters_for_poll(self.bot, p.id))

    @commands.hybrid_command(name="activate")
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

    @commands.hybrid_command(name="delete")
    async def delete(self, ctx, *, short=None):
        """Delete a poll. Parameter: <label>"""
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
                    error = f'Action failed. Poll could not be deleted. ' \
                            f'You should probably report his error to the dev, thanks!'
                    await self.say_error(ctx, error)

            else:
                error = f'Poll with label "{short}" was not found.'
                pre = await get_server_pre(self.bot, ctx.message.guild)
                footer = f'Type {pre}show to display all polls'
                await self.say_error(ctx, error, footer)

    @commands.hybrid_command(name="close")
    async def close(self, ctx, *, short=None):
        """Close a poll. Parameter: <label>"""
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

    @commands.hybrid_command(name="copy")
    async def copy(self, ctx, *, short=None):
        """Copy a poll. Parameter: <label>"""
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

    @commands.hybrid_command(name="export")
    async def export(self, ctx, *, short=None):
        """Export a poll. Parameter: <label>"""
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
                    error_text = f'You can only export closed polls. \n' \
                                 f'Please `{pre}close {short}` the poll first or wait for the deadline.'
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

    @commands.hybrid_command(name="show")
    async def show(self, ctx, short='open', start=0):
        """Show a list of open polls or show a specific poll.
        Parameters: "open" (default), "closed", "prepared" or <label>"""

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

    @commands.hybrid_command(name="draw")
    async def draw(self, ctx, short=None, opt=None):
        server = await ask_for_server(self.bot, ctx.message, short)
        if not server:
            return
        pre = await get_server_pre(self.bot, ctx.message.guild)
        if opt is None:
            error = f'No answer specified please use the following syntax: \n' \
                    f'`{pre}draw <poll_label> <answer_letter>`'
            await self.say_error(ctx, error)
            return
        if short is None:
            error = f'Please specify the label of a poll after the export command. \n' \
                    f'`{pre}export <poll_label>`'
            await self.say_error(ctx, error)
            return

        p = await Poll.load_from_db(self.bot, server.id, short)
        if p is not None:
            if p.options_reaction_default or p.options_reaction_emoji_only:
                error = f'Can\'t draw from emoji-only polls.'
                await self.say_error(ctx, error)
                return
            error = f'Insufficient permissions for this command.'
            if not await self.is_admin_or_creator(ctx, server, p.author.id, error_msg=error):
                return
            try:
                choice = ascii_lowercase.index(opt.lower())
            except ValueError:
                choice = 99
            if len(p.options_reaction) <= choice:
                error = f'Invalid answer "{opt}".'
                await self.say_error(ctx, error)
                return
            if p.open:
                await ctx.invoke(self.close, short=short)
            await p.load_full_votes()
            voter_list = []
            for vote in p.full_votes:
                if vote.choice == choice:
                    voter_list.append(vote.user_id)
            if not voter_list:
                error = f'No votes for option "{opt}".'
                await self.say_error(ctx, error)
                return
            # print(voter_list)
            winner_id = random.choice(voter_list)
            # winner = server.get_member(int(winner_id))
            winner = self.bot.get_user(int(winner_id))
            if not winner:
                error = f'Invalid winner drawn (id: {winner_id}).'
                await self.say_error(ctx, error)
                return
            text = f'The winner is: {winner.mention}'
            title = f'Drawing a random winner from "{opt.upper()}"...'
            await self.say_embed(ctx, text, title=title)
        else:
            error = f'Poll with label "{short}" was not found.'
            await self.say_error(ctx, error)
            await ctx.invoke(self.show)

    @commands.hybrid_command(name="cmd")
    async def cmd(self, ctx, *, cmd=None):
        """The old, command style way paired with the wizard."""
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
                # print(cmd)
                cmd = cmd.replace('“', '"')  # fix for iphone keyboard
                cmd = cmd.replace('”', '"')  # fix for iphone keyboard
                # print(cmd)
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
                error_text += '`' + '\n'.join(unknown_args) + '`'
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

    @commands.hybrid_command(name="quick")
    async def quick(self, ctx, *, cmd=None):
        """Create a quick poll with just a question and some options. Parameters: <Question> (optional)"""
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

    @commands.hybrid_command(name="prepare")
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

    @commands.hybrid_command(name="advanced")
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

    @commands.hybrid_command(name="new")
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
        # member = server.get_member(ctx.message.author.id)
        member = ctx.author
        if not member.guild_permissions.manage_guild:
            result = await self.bot.db.config.find_one({'_id': str(server.id)})
            if result and result.get('admin_role') not in [r.name for r in member.roles] and result.get(
                    'user_role') not in [r.name for r in member.roles]:
                await ctx.message.author.send('You don\'t have sufficient rights to start new polls on this server. '
                                              'A server administrator has to assign the user or admin role to you. '
                                              f'To view and set the permissions, an admin can use `{pre}userrole` and '
                                              f'`{pre}adminrole`')
                return

        # Create object
        poll = Poll(self.bot, ctx, server, channel)

        # Route to define object, passed as argument for different constructors
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
            # user = server.get_member(user_id)
            user = self.bot.get_user(user_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
        elif isinstance(channel, discord.DMChannel):
            user = await self.bot.fetch_user(user_id)  # only do this once
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(message_id)
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
                message = await channel.fetch_message(message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)
        else:
            return

        p = await Poll.load_from_db(self.bot, server.id, label)
        if not isinstance(p, Poll):
            return
        if not p.anonymous:
            # for anonymous polls we can't unvote because we need to hide reactions
            await p.unvote(user, emoji.name, message)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, data):
        # dont look at bot's own reactions
        user_id = data.user_id
        if user_id == self.bot.user.id:
            return

        # get emoji symbol
        emoji = data.emoji
        # if emoji:
        #     emoji_name = emoji.name
        if not emoji:
            return
        # check if we can find a poll label
        message_id = data.message_id
        channel_id = data.channel_id
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            server = channel.guild
            # user = server.get_member(user_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                try:
                    message = await channel.fetch_message(message_id)
                except discord.errors.Forbidden:
                    # Ignore Missing Access error
                    return
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
        elif isinstance(channel, discord.DMChannel):
            user = await self.bot.fetch_user(user_id)  # only do this once
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)
        elif not channel:
            # discord rapidly closes dm channels by design
            # put private channels back into the bots cache and try again
            user = await self.bot.fetch_user(user_id)  # only do this once
            await user.create_dm()
            channel = self.bot.get_channel(channel_id)
            message = self.bot.message_cache.get(message_id)
            if message is None:
                message = await channel.fetch_message(message_id)
                self.bot.message_cache.put(message_id, message)
            label = self.get_label(message)
            if not label:
                return
            server = await ask_for_server(self.bot, message, label)
        else:
            return

        p = await Poll.load_from_db(self.bot, server.id, label)
        if not isinstance(p, Poll):
            return
        # member = server.get_member(user_id)
        user = member = data.member
        # export
        if emoji.name == '📎':
            self.ignore_next_removed_reaction[str(message.id) + str(emoji)] = user_id
            self.bot.loop.create_task(message.remove_reaction(emoji, member))  # remove reaction

            # sending file
            file_name = await p.export()
            if file_name is not None:
                self.bot.loop.create_task(user.send('Sending you the requested export of "{}".'.format(p.short),
                                                    file=discord.File(file_name)
                                                    )
                                          )
            return

        # info

        elif emoji.name == '❔':
            self.ignore_next_removed_reaction[str(message.id) + str(emoji)] = user_id
            self.bot.loop.create_task(message.remove_reaction(emoji, member))  # remove reaction
            is_open = await p.is_open()
            embed = discord.Embed(title=f"Info for the {'CLOSED ' if not is_open else ''}poll \"{p.short}\"",
                                  description='', color=SETTINGS.color)
            embed.set_author(name=f" >> {p.short}", icon_url=SETTINGS.author_icon)

            # created by
            if (p.author != None):
                created_by = self.bot.get_user(int(p.author.id))
            else:
                created_by = "<Deleted User>"
            # created_by = server.get_member(int(p.author.id))
            embed.add_field(name=f'Created by:', value=f'{created_by}',
                            inline=False)

            # vote rights
            vote_rights = p.has_required_role(member)
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
            user_votes = await p.load_votes_for_user(user.id)
            choices = 'You have not voted yet.' if vote_rights else 'You can\'t vote in this poll.'
            if user_votes and len(user_votes) > 0:
                choices = ', '.join([p.options_reaction[v.choice] for v in user_votes])
            embed.add_field(
                name=f'{"Your current votes (can be changed as long as the poll is open):" if is_open else "Your final votes:"}',
                value=choices, inline=False)

            # weight
            if vote_rights:
                weight = 1
                if len(p.weights_roles) > 0:
                    valid_weights = [p.weights_numbers[p.weights_roles.index(r)] for r in
                                     list(set([n.name for n in member.roles]).intersection(set(p.weights_roles)))]
                    if len(valid_weights) > 0:
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

            await p.load_full_votes()
            # await p.load_vote_counts()
            await p.load_unique_participants()
            # send current details of who currently voted for what
            if not p.anonymous and len(p.full_votes) > 0:
                msg = '--------------------------------------------\n' \
                      'VOTES\n' \
                      '--------------------------------------------\n'
                for i, o in enumerate(p.options_reaction):
                    if not p.hide_count or not p.open:
                        if not p.options_reaction_default and not p.options_reaction_emoji_only:
                            msg += AZ_EMOJIS[i] + " "
                        msg += "**" + o + ":**"
                    c = 0
                    for vote in p.full_votes:
                        # member = server.get_member(int(vote.user_id))
                        member: discord.Member = self.bot.get_user(int(vote.user_id))
                        if not member or vote.choice != i:
                            continue
                        c += 1
                        name = member.display_name
                        if not name:
                            name = member.name
                        if not name:
                            name = "<Deleted User>"
                        msg += f'\n{name}'
                        if i in p.survey_flags:
                            msg += f': {vote.answer}'
                        if len(msg) > 1500:
                            await user.send(msg)
                            msg = ''
                    if c == 0 and (not p.hide_count or not p.open):
                        msg += '\nNo votes for this option yet.'
                    if not p.hide_count or not p.open:
                        msg += '\n\n'

                if len(msg) > 0:
                    await user.send(msg)
            elif (not p.open or not p.hide_count) and p.anonymous and len(p.survey_flags) > 0 and len(p.full_votes) > 0:
                msg = '--------------------------------------------\n' \
                      'Custom Answers (Anonymous)\n' \
                      '--------------------------------------------\n'
                has_answers = False
                for i, o in enumerate(p.options_reaction):
                    if i not in p.survey_flags:
                        continue
                    custom_answers = ''
                    for vote in p.full_votes:
                        if vote.choice == i:
                            has_answers = True
                            custom_answers += f'\n{vote.answer}'
                    if len(custom_answers) > 0:
                        if not p.options_reaction_emoji_only:
                            msg += AZ_EMOJIS[i] + " "
                        msg += "**" + o + ":**"
                        msg += custom_answers
                        msg += '\n\n'
                    if len(msg) > 1500:
                        await user.send(msg)
                        msg = ''
                if has_answers and len(msg) > 0:
                    await user.send(msg)
            return
        else:
            # Assume: User wants to vote with reaction
            # no rights, terminate function
            if not p.has_required_role(member):
                await message.remove_reaction(emoji, user)
                await member.send(f'You are not allowed to vote in this poll. Only users with '
                                  f'at least one of these roles can vote:\n{", ".join(p.roles)}')
                return

            # check if we need to remove reactions (this will trigger on_reaction_remove)
            if not isinstance(channel, discord.DMChannel) and (p.anonymous or p.hide_count):
                # immediately remove reaction and to be safe, remove all reactions
                self.ignore_next_removed_reaction[str(message.id) + str(emoji)] = user_id
                await message.remove_reaction(emoji, user)

                # clean up all reactions (prevent lingering reactions)
                for rct in message.reactions:
                    if rct.count > 1:
                        async for user in rct.users():
                            if user == self.bot.user:
                                continue
                            self.ignore_next_removed_reaction[str(message.id) + str(rct.emoji)] = user_id
                            self.bot.loop.create_task(rct.remove(user))

            # order here is crucial since we can't determine if a reaction was removed by the bot or user
            # update database with vote
            await p.vote(member, emoji.name, message)


async def setup(bot):
    global logger
    logger = logging.getLogger('discord')
    await bot.add_cog(PollControls(bot))
