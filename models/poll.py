import asyncio
import codecs
import datetime
import logging
import os
import random
import re
import time
from string import ascii_lowercase
from uuid import uuid4

import dateparser
import discord
import pytz
import regex
from bson import ObjectId
from utils.afm import AFM
from pytz import UnknownTimeZoneError
from unidecode import unidecode

from essentials.exceptions import *
from essentials.multi_server import get_pre
from essentials.settings import SETTINGS
from models.vote import Vote
from utils.misc import possible_timezones

logger = logging.getLogger('discord')

# Helvetica is the closest font to Whitney (discord uses Whitney) in afm
# This is used to estimate text width and adjust the layout of the embeds
script_dir = os.path.dirname(__file__) #<-- absolute dir the script is in
rel_path = "phvr8a.afm"

with open(script_dir + "/" + rel_path, 'rb') as fh:
    afm = AFM(fh)

# A-Z Emojis for Discord
AZ_EMOJIS = [(b'\\U0001f1a'.replace(b'a', bytes(hex(224 + (6 + i))[2:], "utf-8"))).decode("unicode-escape") for i in
             range(26)]


class Poll:
    def __init__(self, bot, ctx=None, server=None, channel=None, load=False):

        self.bot = bot
        self.cursor_pos = 0

        self.vote_counts = {}
        self.vote_counts_weighted = {}
        self.full_votes = []
        self.unique_participants = set()

        if not load and ctx:
            if server is None:
                server = ctx.message.guild

            if channel is None:
                channel = ctx.message.channel

            self.id = None

            self.author = ctx.message.author

            self.server = server
            self.channel = channel

            self.name = "Quick Poll"
            self.short = str(uuid4())[0:23]
            self.anonymous = False
            self.hide_count = False
            self.reaction = True
            self.multiple_choice = 1
            self.options_reaction = ['yes', 'no']
            self.options_reaction_default = False
            self.options_reaction_emoji_only = False
            self.survey_flags = []
            # self.options_traditional = []
            # self.options_traditional_default = False
            self.roles = ['@everyone']
            self.weights_roles = []
            self.weights_numbers = []
            self.duration = 0
            self.duration_tz = 0.0
            self.time_created = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

            self.open = True
            self.active = True
            self.activation = 0
            self.activation_tz = 0.0
            self.votes = {}

            self.wizard_messages = []

    @staticmethod
    def get_preset_options(number):
        if number == 1:
            return ['✅', '❎']
        elif number == 2:
            return ['👍', '🤐', '👎']
        elif number == 3:
            return ['😍', '👍', '🤐', '👎', '🤢']
        elif number == 4:
            return ['in favour', 'against', 'abstaining']

    async def is_open(self, update_db=True):
        if self.server is None:
            self.open = True
            return
        if self.open and self.duration != 0 \
                and datetime.datetime.utcnow().replace(tzinfo=pytz.utc) > self.get_duration_with_tz():
            self.open = False
            if update_db:
                await self.save_to_db()
        return self.open

    async def is_active(self, update_db=True):
        if self.server is None:
            self.active = False
            return
        if not self.active and self.activation != 0 \
                and datetime.datetime.utcnow().replace(tzinfo=pytz.utc) > self.get_activation_with_tz():
            self.active = True
            if update_db:
                await self.save_to_db()
        return self.active

    async def wizard_says(self, ctx, text, footer=True):
        embed = discord.Embed(title="Poll creation Wizard", description=text, color=SETTINGS.color)
        if footer:
            embed.set_footer(text="Type `stop` to cancel the wizard.")
        msg = await ctx.send(embed=embed)
        self.wizard_messages.append(msg)
        return msg

    async def wizard_says_edit(self, message, text, add=False):
        if add and message.embeds.__len__() > 0:
            text = message.embeds[0].description + text
        embed = discord.Embed(title="Poll creation Wizard", description=text, color=SETTINGS.color)
        embed.set_footer(text="Type `stop` to cancel the wizard.")
        return await message.edit(embed=embed)

    async def add_error(self, message, error):
        text = ''
        if message.embeds.__len__() > 0:
            text = message.embeds[0].description + '\n\n:exclamation: ' + error
        return await self.wizard_says_edit(message, text)

    async def add_vaild(self, message, string):
        text = ''
        if message.embeds.__len__() > 0:
            text = message.embeds[0].description + '\n\n✅ ' + string
        return await self.wizard_says_edit(message, text)

    async def get_user_reply(self, ctx):
        """Pre-parse user input for wizard"""
        def check(m):
            return m.author == self.author
        try:
            reply = await self.bot.wait_for('message', timeout=600, check=check)
        except asyncio.TimeoutError:
            raise StopWizard

        if reply and reply.content:
            self.wizard_messages.append(reply)
            if reply.content.startswith(await get_pre(self.bot, reply)):
                await self.wizard_says(ctx, f'You can\'t use bot commands during the Poll Creation Wizard.\n'
                                       f'Stopping the Wizard and then executing the command:\n`{reply.content}`',
                                       footer=False)
                raise StopWizard
            elif reply.content.lower() == 'stop':
                await self.wizard_says(ctx, 'Poll Wizard stopped.', footer=False)
                raise StopWizard

            else:
                return reply.content
        else:
            raise InvalidInput

    @staticmethod
    def sanitize_string(string):
        """Sanitize user input for wizard"""
        # sanitize input
        if string is None:
            raise InvalidInput
        string = regex.sub("\p{C}+", "", string)
        if set(string).issubset(set(' ')):
            raise InvalidInput
        return string

    async def set_name(self, ctx, force=None):
        """Set the Question / Name of the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            min_len = 3
            max_len = 400
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif min_len <= in_reply.__len__() <= max_len:
                return in_reply
            else:
                raise InvalidInput

        try:
            self.name = await get_valid(force)
            return
        except InputError:
            pass

        text = ("**What is the question of your poll?**\n"
                "Try to be descriptive without writing more than one sentence.")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.name = await get_valid(reply)
                await self.add_vaild(message, self.name)
                break
            except InvalidInput:
                await self.add_error(message, '**Keep the poll question between 3 and 400 valid characters**')

    async def set_short(self, ctx, force=None):
        """Set the label of the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            min_len = 2
            max_len = 25
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif in_reply in ['open', 'closed', 'prepared']:
                raise ReservedInput
            elif await self.bot.db.polls.find_one({'server_id': str(self.server.id), 'short': in_reply}) is not None:
                raise DuplicateInput
            elif min_len <= in_reply.__len__() <= max_len and in_reply.split(" ").__len__() == 1:
                return in_reply
            else:
                raise InvalidInput

        try:
            self.short = await get_valid(force)
            return
        except InputError:
            pass

        text = """Great. **Now type a unique one word identifier, a label, for your poll.**
         This label will be used to refer to the poll. Keep it short and significant."""
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.short = await get_valid(reply)
                await self.add_vaild(message, self.short)
                break
            except InvalidInput:
                await self.add_error(message, '**Only one word between 2 and 25 valid characters!**')
            except ReservedInput:
                await self.add_error(message, '**Can\'t use reserved words (open, closed, prepared) as label!**')
            except DuplicateInput:
                await self.add_error(message,
                                     f'**The label `{reply}` is not unique on this server. Choose a different one!**')

    async def set_preparation(self, ctx, force=None):
        """Set the preparation conditions for the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif in_reply == '0':
                return 0

            dt = dateparser.parse(in_reply)
            if not isinstance(dt, datetime.datetime):
                raise InvalidInput

            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                dt = dt.astimezone(pytz.utc)

            now = datetime.datetime.utcnow().astimezone(pytz.utc)

            # print(now, now.tzinfo)
            # print("orig",dt , dt.tzinfo)
            # dt = dt.astimezone(pytz.utc)
            # print("converted", dt, dt.tzinfo)

            if dt < now:
                raise DateOutOfRange(dt)
            return dt

        if str(force) == '-1':
            return

        try:
            dt = await get_valid(force)
            self.activation = dt
            if self.activation != 0:
                self.activation_tz = dt.utcoffset().total_seconds() / 3600
            self.active = False
            return
        except InputError:
            pass

        text = ("This poll will be created inactive. You can either schedule activation at a certain date or activate "
                "it manually. **Type `0` to activate it manually or tell me when you want to activate it** by "
                "typing an absolute or relative date. You can specify a timezone if you want.\n"
                "Examples: `in 2 days`, `next week CET`, `may 3rd 2019`, `9.11.2019 9pm EST` ")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                dt = await get_valid(reply)
                self.activation = dt
                if self.activation == 0:
                    await self.add_vaild(message, 'manually activated')
                else:
                    self.activation_tz = dt.utcoffset().total_seconds() / 3600
                    await self.add_vaild(message, self.activation.strftime('%d-%b-%Y %H:%M %Z'))
                self.active = False
                break
            except InvalidInput:
                await self.add_error(message, '**Specify the activation time in a format i can understand.**')
            except TypeError:
                await self.add_error(message, '**Type Error.**')
            except DateOutOfRange as e:
                await self.add_error(message, f'**{e.date.strftime("%d-%b-%Y %H:%M")} is in the past.**')

    async def set_anonymous(self, ctx, force=None):
        """Determine if poll is anonymous."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            is_true = ['yes', '1']
            is_false = ['no', '0']
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif in_reply.lower() in is_true:
                return True
            elif in_reply.lower() in is_false:
                return False
            else:
                raise InvalidInput

        try:
            self.anonymous = await get_valid(force)
            return
        except InputError:
            pass

        text = ("Next you need to decide: **Do you want your poll to be anonymous?**\n"
                "\n"
                "`0 - No`\n"
                "`1  - Yes`\n"
                "\n"
                "An anonymous poll has the following effects:\n"
                "🔹 You will never see who voted for which option\n"
                "🔹 Once the poll is closed, you will see who participated (but not their choice)")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.anonymous = await get_valid(reply)
                await self.add_vaild(message, f'{"Yes" if self.anonymous else "No"}')
                break
            except InvalidInput:
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')

    async def set_multiple_choice(self, ctx, force=None):
        """Determine if poll is multiple choice."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif not in_reply.isdigit():
                raise ExpectedInteger
            elif int(in_reply) > self.options_reaction.__len__():
                raise OutOfRange
            elif int(in_reply) <= self.options_reaction.__len__() >= 0:
                return int(in_reply)
            else:
                raise InvalidInput

        try:
            self.multiple_choice = await get_valid(force)
            return
        except InputError:
            pass

        text = ("**How many options should the voters be able choose?**\n"
                "\n"
                "`0 - No Limit: Multiple Choice`\n"
                "`1  - Single Choice`\n"
                "`2+  - Specify exactly how many Choices`\n"
                "\n"
                "If the maximum choices are reached for a voter, they have to unvote an option before being able to "
                "vote for a different one.")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.multiple_choice = await get_valid(reply)
                await self.add_vaild(message, f'{self.multiple_choice if self.multiple_choice > 0 else "No Limit"}')
                break
            except InvalidInput:
                await self.add_error(message, '**Invalid Input**')
            except ExpectedInteger:
                await self.add_error(message, '**Enter a positive number**')
            except OutOfRange:
                await self.add_error(message, '**You can\'t have more choices than options.**')

    async def set_options_reaction(self, ctx, force=None):
        """Set the answers / options of the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            preset = ['1','2','3','4']
            split = [r.strip() for r in in_reply.split(",")]

            if split.__len__() == 1:
                if split[0] in preset:
                    return int(split[0])
                else:
                    raise WrongNumberOfArguments
            elif 1 < split.__len__() <= 18:
                split = [self.sanitize_string(o) for o in split]
                if any([len(o) < 1 for o in split]):
                    raise InvalidInput
                else:
                    return split
            else:
                raise WrongNumberOfArguments

        try:
            options = await get_valid(force)
            self.options_reaction_default = False
            if isinstance(options, int):
                self.options_reaction = self.get_preset_options(options)
                if options <= 3:
                    self.options_reaction_default = True
            else:
                self.options_reaction = options
            return
        except InputError:
            pass

        text = ("**Choose the options/answers for your poll.**\n"
                "Either chose a preset of options or type your own options, separated by commas.\n"
                "\n"
                "**1** - :white_check_mark: :negative_squared_cross_mark:\n"
                "**2** - :thumbsup: :zipper_mouth: :thumbsdown:\n"
                "**3** - :heart_eyes: :thumbsup: :zipper_mouth:  :thumbsdown: :nauseated_face:\n"
                "**4** - in favour, against, abstaining\n"
                "\n"
                "Example for custom options:\n"
                "**apple juice, banana ice cream, kiwi slices** ")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                options = await get_valid(reply)
                self.options_reaction_default = False
                if isinstance(options, int):
                    self.options_reaction = self.get_preset_options(options)
                    if options <= 3:
                        self.options_reaction_default = True
                else:
                    self.options_reaction = options
                await self.add_vaild(message, f'{", ".join(self.options_reaction)}')
                break
            except InvalidInput:
                await self.add_error(message,
                                     '**Invalid entry. Type `1`, `2`, `3` or `4` or a comma separated list of '
                                     'up to 18 options.**')
            except WrongNumberOfArguments:
                await self.add_error(message,
                                     '**You need more than 1 and less than 19 options! '
                                     'Type them in a comma separated list.**')

    async def set_survey_flags(self, ctx, force=None):
        """Decide which Options will ask for user input."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            split = [r.strip() for r in in_reply.split(",")]

            if not split or split.__len__() == 1 and split[0] == '0':
                return []

            if not all([r.isdigit() for r in split]):
                raise ExpectedInteger

            if any([1 > int(r) or int(r) > len(self.options_reaction) for r in split]):
                raise OutOfRange

            return [int(r)-1 for r in split]

        if self.options_reaction_default:
            return

        try:
            self.survey_flags = await get_valid(force)
            return
        except InputError:
            pass

        text = ("**Which options should ask the user for a custom answer?**\n"
                "Type `0` to skip survey options.\n"
                "If you want multiple survey options, separate the numbers with a comma.\n"
                "\n"
                "`0 - None (classic poll)`\n"
                )
        for i, option in enumerate(self.options_reaction):
            text += f'`{i + 1} - {option}`\n'
        text += ("\n"
                 "If the user votes for one of these options, the bot will PM them and ask them to provide a text "
                 "input. You can use this to do surveys or to gather feedback for example.\n")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.survey_flags = await get_valid(reply)
                await self.add_vaild(
                    message, f'{"None" if self.survey_flags.__len__() == 0 else ", ".join(str(f + 1) for f in self.survey_flags)}'
                )
                break
            except InvalidInput:
                await self.add_error(message, '**I can\'t read this input.**')
            except ExpectedInteger:
                await self.add_error(message, '**Only type positive numbers separated by a comma.**')
            except OutOfRange:
                await self.add_error(message, '**Only type numbers you can see in the list.**')

    async def set_hide_vote_count(self, ctx, force=None):
        """Determine the live vote count is hidden or shown."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            is_true = ['yes', '1']
            is_false = ['no', '0']
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif in_reply.lower() in is_true:
                return True
            elif in_reply.lower() in is_false:
                return False
            else:
                raise InvalidInput

        try:
            self.hide_count = await get_valid(force)
            return
        except InputError:
            pass

        text = ("**Do you want to hide the live vote count?**\n"
                "\n"
                "`0 - No, show it (Default)`\n"
                "`1  - Yes, hide it`\n"
                "\n"
                "You will still be able to see the vote count once the poll is closed. This settings will just hide "
                "the vote count while the poll is active.")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.hide_count = await get_valid(reply)
                await self.add_vaild(message, f'{"Yes" if self.hide_count else "No"}')
                break
            except InvalidInput:
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')

    async def set_roles(self, ctx, force=None):
        """Set role restrictions for the Poll."""
        async def get_valid(in_reply, roles):
            n_roles = roles.__len__()
            if not in_reply:
                raise InvalidInput

            split = [self.sanitize_string(r.strip()) for r in in_reply.split(",")]
            if split.__len__() == 1 and split[0] in ['0', 'all', 'everyone']:
                return ['@everyone']

            if n_roles <= 20 and not force:
                if not all([r.isdigit() for r in split]):
                    raise ExpectedInteger
                elif any([int(r) > n_roles for r in split]):
                    raise OutOfRange

                role_names = [r.name for r in roles]
                return [role_names[i - 1] for i in [int(r) for r in split]]
            else:
                invalid_roles = []
                for r in split:
                    if not any([r == sr for sr in [x.name for x in roles]]):
                        invalid_roles.append(r)
                if invalid_roles.__len__() > 0:
                    raise InvalidRoles(", ".join(invalid_roles))
                else:
                    return split

        roles = self.server.roles
        n_roles = roles.__len__()
        try:
            self.roles = await get_valid(force, roles)
            return
        except InputError:
            pass

        if n_roles <= 20:
            text = ("**Choose which roles are allowed to vote.**\n"
                    "Type `0`, `all` or `everyone` to have no restrictions.\n"
                    "If you want multiple roles to be able to vote, separate the numbers with a comma.\n")
            text += f'\n`{0} - no restrictions`'

            for i, role in enumerate([r.name for r in self.server.roles]):
                text += f'\n`{i+1} - {role}`'
            text += ("\n"
                     "\n"
                     " Example: `2, 3` \n")
        else:
            text = ("**Choose which roles are allowed to vote.**\n"
                    "Type `0`, `all` or `everyone` to have no restrictions.\n"
                    "Type out the role names, separated by a comma, to restrict voting to specific roles:\n"
                    "`moderators, Editors, vips` (hint: role names are case sensitive!)\n")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                self.roles = await get_valid(reply, roles)
                await self.add_vaild(message, f'{", ".join(self.roles)}')
                break
            except InvalidInput:
                await self.add_error(message, '**I can\'t read this input.**')
            except ExpectedInteger:
                await self.add_error(message, '**Only type positive numbers separated by a comma.**')
            except OutOfRange:
                await self.add_error(message, '**Only type numbers you can see in the list.**')
            except InvalidRoles as e:
                await self.add_error(message, f'**The following roles are invalid: {e.roles}**')

    async def set_weights(self, ctx, force=None):
        """Set role weights for the poll."""
        async def get_valid(in_reply, server_roles):
            if not in_reply:
                raise InvalidInput
            no_weights = ['0', 'none']
            pairs = [self.sanitize_string(p.strip()) for p in in_reply.split(",")]
            if pairs.__len__() == 1 and pairs[0] in no_weights:
                return [[], []]
            if not all([":" in p for p in pairs]):
                raise ExpectedSeparator(":")
            roles = []
            weights = []
            for e in pairs:
                c = [x.strip() for x in e.rsplit(":", 1)]
                if not any([c[0] == sr for sr in [x.name for x in server_roles]]):
                    raise InvalidRoles(c[0])

                c[1] = float(c[1]) # Catch ValueError
                c[1] = int(c[1]) if c[1].is_integer() else c[1]

                roles.append(c[0])
                weights.append(c[1])
                if len(roles) > len(set(roles)):
                    raise WrongNumberOfArguments

            return [roles, weights]

        try:
            w_n = await get_valid(force, self.server.roles)
            self.weights_roles = w_n[0]
            self.weights_numbers = w_n[1]
            return
        except InputError:
            pass

        text = ("Almost done.\n"
                "**Weights allow you to give certain roles more or less effective votes.\n"
                "Type `0` or `none` if you don't need any weights.**\n"
                "A weight for the role `moderator` of `2` for example will automatically count the votes of all the moderators twice.\n"
                "To assign weights type the role, followed by a colon, followed by the weight like this:\n"
                "`moderator: 2, newbie: 0.5`")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                # print(reply)
                w_n = await get_valid(reply, self.server.roles)
                self.weights_roles = w_n[0]
                self.weights_numbers = w_n[1]
                weights = []
                for r, n in zip(self.weights_roles, self.weights_numbers):
                    weights.append(f'{r}: {n}')
                await self.add_vaild(message, ", ".join(weights))
                break
            except InvalidInput:
                await self.add_error(message, '**Can\'t read this input.**')
            except ExpectedSeparator as e:
                await self.add_error(message, f'**Expected roles and weights to be separated by {e.separator}**')
            except InvalidRoles as e:
                await self.add_error(message, f'**Invalid role found: {e.roles}**')
            except ValueError:
                await self.add_error(message, f'**Weights must be numbers.**')
            except WrongNumberOfArguments:
                await self.add_error(message, f'**Not every role has a weight assigned.**')

    async def set_duration(self, ctx, force=None):
        """Set the duration /deadline for the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            in_reply = self.sanitize_string(in_reply)
            if not in_reply:
                raise InvalidInput
            elif in_reply == '0':
                return 0

            dt = dateparser.parse(in_reply)
            if not isinstance(dt, datetime.datetime):
                raise InvalidInput

            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                dt = dt.astimezone(pytz.utc)

            now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
            if dt < now:
                raise DateOutOfRange(dt)
            return dt

        try:
            dt = await get_valid(force)
            self.duration = dt
            if self.duration != 0:
                self.duration_tz = dt.utcoffset().total_seconds() / 3600
            return
        except InputError:
            pass

        text = ("Last step.\n"
                "**When should the poll be closed?**\n"
                "If you want the poll to last indefinitely (until you close it), type `0`."
                "Otherwise tell me when the poll should close in relative or absolute terms. "
                "You can specify a timezone if you want.\n"
                "\n"
                "Examples: `in 6 hours` or `next week CET` or `aug 15th 5:10` or `15.8.2019 11pm EST`")
        message = await self.wizard_says(ctx, text)

        while True:
            try:
                if force:
                    reply = force
                    force = None
                else:
                    reply = await self.get_user_reply(ctx)
                dt = await get_valid(reply)
                self.duration = dt
                if self.duration == 0:
                    await self.add_vaild(message, 'until closed manually')
                else:
                    self.duration_tz = dt.utcoffset().total_seconds() / 3600
                    await self.add_vaild(message, self.duration.strftime('%d-%b-%Y %H:%M %Z'))
                break
            except InvalidInput:
                await self.add_error(message, '**Specify the deadline in a format I can understand.**')
            except TypeError:
                await self.add_error(message, '**Type Error.**')
            except DateOutOfRange as e:
                await self.add_error(message, f'**{e.date.strftime("%d-%b-%Y %H:%M")} is in the past.**')

    def finalize(self):
        self.time_created = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        self.set_emoji_only()
        # no duplicates in emoji only reactions
        if self.options_reaction_emoji_only:
            self.options_reaction = list(dict.fromkeys(self.options_reaction))

    async def clean_up(self, channel):
        if isinstance(channel, discord.TextChannel):
            self.bot.loop.create_task(channel.delete_messages(self.wizard_messages))

    async def ask_for_input_dm(self, user, title, text):
        embed = discord.Embed(title=title, description=text, color=SETTINGS.color)
        embed.set_footer(text='You can answer anywhere.')
        message = await user.send(embed=embed)

        def check(m):
            return m.author == user

        try:
            reply = await self.bot.wait_for('message', timeout=600, check=check)
            if reply and reply.content:
                reply = reply.content
            else:
                return None
        except asyncio.TimeoutError:
            if message.embeds.__len__() > 0:
                embed.description = embed.description + '\n\n:exclamation: Request timed out. Vote was counted, ' \
                                                        'but no custom answer recorded.'
                await message.edit(embed=embed)
            return None

        try:
            reply = self.sanitize_string(reply)
        except InvalidInput:
            embed = discord.Embed(title=title,
                                  description="Invalid Input. To try again, un-vote and re-vote the option.",
                                  color=SETTINGS.color
                                  )
            await user.send(embed=embed)

        if message.embeds.__len__() > 0:
            embed.description = embed.description + '\n\n✅ ' + reply
            await message.edit(embed=embed)

        return reply

    def to_command(self):
        # make new label by increasing a counter at the end
        try:
            new_nr = int(self.short[-1]) + 1
            new_label = self.short[:-1] + str(new_nr)
        except ValueError:
            new_label = self.short + "2"

        cmd = "cmd"

        cmd += " -q \"" + self.name + "\""
        cmd += " -l \"" + new_label + "\""
        if self.anonymous:
            cmd += " -a"

        if self.options_reaction_default:
            for i in range(1, 5):
                if self.get_preset_options(i) == self.options_reaction:
                    cmd += " -o \"" + str(i) + "\""
        else:
            cmd += " -o \"" + ", ".join(self.options_reaction) + "\""

        if self.survey_flags:
            cmd += " -sf \"" + ", ".join([str(x+1) for x in self.survey_flags]) + "\""

        cmd += " -mc \"" + str(self.multiple_choice) + "\""
        if self.hide_count:
            cmd += " -h"
        if self.roles != ["@everyone"]:
            cmd += " -r \"" + ", ".join(self.roles) + "\""
        if not self.active:
            cmd += " -p \"specify activation time\""
        if self.duration == 0:
            cmd += " -d \"0\""
        else:
            cmd += " -d \"specify deadline\""

        return cmd

    async def to_dict(self):
        if self.channel is None:
            cid = 0
        else:
            cid = self.channel.id
        if self.author is None:
            aid = 0
        else:
            aid = self.author.id
        return {
            'server_id': str(self.server.id),
            'channel_id': str(cid),
            'author': str(aid),
            'name': self.name,
            'short': self.short,
            'anonymous': self.anonymous,
            'hide_count': self.hide_count,
            'reaction': self.reaction,
            'multiple_choice': self.multiple_choice,
            'options_reaction': self.options_reaction,
            'reaction_default': self.options_reaction_default,
            #'options_traditional': self.options_traditional,
            'survey_flags': self.survey_flags,
            'roles': self.roles,
            'weights_roles': self.weights_roles,
            'weights_numbers': self.weights_numbers,
            'duration': self.duration,
            'duration_tz': self.duration_tz,
            'time_created': self.time_created,
            'open': self.open,
            'active': self.active,
            'activation': self.activation,
            'activation_tz': self.activation_tz,
            'votes': self.votes
        }

    async def to_export(self):
        """Create report and return string"""
        # load all votes from database
        await self.load_full_votes()
        await self.load_vote_counts()
        await self.load_unique_participants()
        # build string for weights
        weight_str = 'No weights'
        if self.weights_roles.__len__() > 0:
            weights = []
            for r, n in zip(self.weights_roles, self.weights_numbers):
                weights.append(f'{r}: {n}')
            weight_str = ', '.join(weights)

        # Determine the poll winner
        winning_options = []
        winning_votes = 0
        for i, o in enumerate(self.options_reaction):
            votes = self.vote_counts_weighted.get(i, 0)
            if votes > winning_votes:
                winning_options = [o]
                winning_votes = votes
            elif votes == winning_votes:
                winning_options.append(o)
        deadline_str = await self.get_deadline(string=True)
        export = (f'--------------------------------------------\n'
                  f'POLLMASTER DISCORD EXPORT\n'
                  f'--------------------------------------------\n'
                  f'Server name (ID): {self.server.name} ({self.server.id})\n'
                  f'Owner of the poll: {self.author.name}\n'
                  f'Time of creation: {self.time_created.strftime("%d-%b-%Y %H:%M %Z")}\n'
                  f'--------------------------------------------\n'
                  f'POLL SETTINGS\n'
                  f'--------------------------------------------\n'
                  f'Question / Name: {self.name}\n'
                  f'Label: {self.short}\n'
                  f'Anonymous: {"Yes" if self.anonymous else "No"}\n'
                  f'# Choices: {"Multiple" if self.multiple_choice == 0 else self.multiple_choice}\n'
                  f'Answer options: {", ".join(self.options_reaction)}\n'
                  f'Allowed roles: {", ".join(self.roles) if self.roles.__len__() > 0 else "@everyone"}\n'
                  f'Weights for roles: {weight_str}\n'
                  f'Deadline: {deadline_str}\n'
                  f'--------------------------------------------\n'
                  f'POLL RESULTS\n'
                  f'--------------------------------------------\n'
                  f'Number of participants: {len(self.unique_participants)}\n'
                  f'Raw results: {", ".join([str(o)+": "+str(self.vote_counts.get(i, 0)) for i,o in enumerate(self.options_reaction)])}\n'
                  f'Weighted results: {", ".join([str(o)+": "+str(self.vote_counts_weighted.get(i, 0)) for i,o in enumerate(self.options_reaction)])}\n'
                  f'Winning option{"s" if len(winning_options) > 1 else ""}: {", ".join(winning_options)} with {winning_votes} votes\n')

        if not self.anonymous:
            export += '--------------------------------------------\n' \
                      'DETAILED POLL RESULTS\n' \
                      '--------------------------------------------'

            for user_id in self.unique_participants:
                # member = self.server.get_member(int(user_id))
                member = self.bot.get_user(int(user_id))

                if not member:
                    name = "<Deleted User>"
                else:
                    name = member.display_name
                if not name:
                    name = member.name

                export += f'\n{name}: '
                # if self.votes[str(user_id)]['weight'] != 1:
                #     export += f' (weight: {self.votes[str(user_id)]["weight"]})'
                # export += ': ' + ', '.join([self.options_reaction[c] for c in self.votes[str(user_id)]['choices']])
                choice_text_list = []

                for vote in self.full_votes:
                    if vote.user_id != user_id:
                        continue

                    choice_text = self.options_reaction[vote.choice]
                    if vote.choice in self.survey_flags:
                        choice_text += f' ({vote.answer}) '
                    choice_text_list.append(choice_text)

                # for choice in self.votes[str(user_id)]['choices']:
                #     choice_text = self.options_reaction[choice]
                #     if choice in self.survey_flags:
                #         choice_text += " ("\
                #                   + self.votes[str(user_id)]["answers"][self.survey_flags.index(choice)] \
                #                   + ") "
                #     choice_text_list.append(choice_text)

                if choice_text_list:
                    export += ', '.join(choice_text_list)

            export += '\n'
        else:
            export += '--------------------------------------------\n' \
                      'LIST OF PARTICIPANTS\n' \
                      '--------------------------------------------'

            for user_id in self.unique_participants:
                # member = self.server.get_member(int(user_id))
                member = self.bot.get_user(int(user_id))
                if not member:
                    name = "<Deleted User>"
                else:
                    name = member.display_name
                if not name:
                    name = member.name

                export += f'\n{name}'
                # if self.votes[str(user_id)]['weight'] != 1:
                #     export += f' (weight: {self.votes[str(user_id)]["weight"]})'
                # export += ': ' + ', '.join([self.options_reaction[c] for c in self.votes[str(user_id)]['choices']])
            export += '\n'

            if len(self.survey_flags) > 0:
                export += '--------------------------------------------\n' \
                          'CUSTOM ANSWERS (RANDOM ORDER)\n' \
                          '--------------------------------------------'
                for i, o in enumerate(self.options_reaction):
                    if i not in self.survey_flags:
                        continue
                    custom_answers = []

                    for vote in self.full_votes:
                        if vote.choice == i and vote.answer != '':
                            custom_answers.append(f'\n{vote.answer}')

                    # for user_id in self.votes:
                    #     if i in self.votes[str(user_id)]["choices"]:
                    #         custom_answers.append(f'\n{self.votes[str(user_id)]["answers"][self.survey_flags.index(i)]}')

                    export += "\n" + o + ":"
                    if len(custom_answers) > 0:
                        random.shuffle(custom_answers)  # randomize answers per question
                        for answer in custom_answers:
                            export += answer
                            export += '\n'
                    else:
                        export += "\nNo custom answers were submitted."
                        export += '\n'

        export += ('--------------------------------------------\n'
                   'BOT DETAILS\n'
                   '--------------------------------------------\n'
                   'Creator: Newti#0654\n'
                   'Link to invite, vote for or support Pollmaster:\n'
                   'https://discordbots.org/bot/444514223075360800\n'
                   '--------------------------------------------\n'
                   'END OF FILE\n'
                   '--------------------------------------------\n')
        return export

    async def export(self):
        """Create export file and return path"""
        if not self.open:
            clean_label = str(self.short).replace("/", "").replace(".", "")
            fn = 'export/' + str(self.server.id) + '_' + clean_label + '.txt'
            with codecs.open(fn, 'w', 'utf-8') as outfile:
                outfile.write(await self.to_export())
            return fn
        else:
            return None

    def set_emoji_only(self):
        self.options_reaction_emoji_only = True
        for reaction in self.options_reaction:
            if reaction not in self.bot.emoji_dict:
                e_id = re.findall(r':(\d+)>', reaction)
                emoji = None
                if e_id:
                    emoji = self.bot.get_emoji(int(e_id[0]))
                if not emoji or emoji.guild_id != self.server.id:
                    self.options_reaction_emoji_only = False
                    break

    async def from_dict(self, d):
        self.id = ObjectId(str(d['_id']))
        self.server = self.bot.get_guild(int(d['server_id']))
        self.channel = self.bot.get_channel(int(d['channel_id']))
        if self.server != None:
            self.author = self.bot.get_user(int(d['author']))
            # self.author = self.server.get_member(int(d['author']))
        else:
            self.author = None
        self.name = d['name']
        self.short = d['short']
        self.anonymous = d['anonymous']

        # backwards compatibility
        if 'hide_count' in d.keys():
            self.hide_count = d['hide_count']
        else:
            self.hide_count = False

        self.reaction = d['reaction']

        # backwards compatibility for multiple choice
        if isinstance(d['multiple_choice'], bool):
            if d['multiple_choice']:
                self.multiple_choice = 0
            else:
                self.multiple_choice = 1
        else:
            try:
                self.multiple_choice = int(d['multiple_choice'])
            except ValueError:
                logger.exception('Multiple Choice not an int or bool.')
                self.multiple_choice = 0 # default

        self.options_reaction = d['options_reaction']
        self.options_reaction_default = d['reaction_default']

        # check if emoji only
        self.set_emoji_only()

        # self.options_traditional = d['options_traditional']

        # backwards compatibility
        if 'survey_flags' in d.keys():
            self.survey_flags = d['survey_flags']
        else:
            self.survey_flags = []

        self.roles = d['roles']
        self.weights_roles = d['weights_roles']
        self.weights_numbers = d['weights_numbers']
        self.duration = d['duration']
        self.duration_tz = d['duration_tz']
        self.time_created = d['time_created']

        self.activation = d['activation']
        self.activation_tz = d['activation_tz']
        self.active = d['active']
        self.open = d['open']

        self.cursor_pos = 0
        self.votes = d['votes']

        self.open = await self.is_open()
        self.active = await self.is_active()

    async def save_to_db(self):
        await self.bot.db.polls.update_one({'server_id': str(self.server.id), 'short': str(self.short)},
                                           {'$set': await self.to_dict()}, upsert=True)

    @staticmethod
    async def load_from_db(bot, server_id, short, ctx=None, ):
        query = await bot.db.polls.find_one({'server_id': str(server_id), 'short': short})
        if query is not None:
            p = Poll(bot, ctx, load=True)
            await p.from_dict(query)
            return p
        else:
            return None

    async def load_votes_for_user(self, user_id):
        return await Vote.load_votes_for_poll_and_user(self.bot, self.id, user_id)

    async def load_unique_participants(self):
        await self.load_full_votes()
        voters = set()
        for v in self.full_votes:
            voters.add(v.user_id)
        self.unique_participants = voters

    async def load_vote_counts(self):
        if not self.vote_counts:
            self.vote_counts = await Vote.load_vote_counts_for_poll(self.bot, self.id)

        if len(self.weights_numbers) > 0 and not self.vote_counts_weighted:
            # find weighted totals
            await self.load_full_votes()
            for v in self.full_votes:
                self.vote_counts_weighted[v.choice] = self.vote_counts_weighted.get(v.choice, 0) + v.weight
        else:
            self.vote_counts_weighted = self.vote_counts

    async def load_full_votes(self):
        if not self.full_votes:
            self.full_votes = await Vote.load_all_votes_for_poll(self.bot, self.id)



    def add_field_custom(self, name, value, embed):
        """this is used to estimate the width of text and add empty embed fields for a cleaner report
        cursor_pos is used to track if we are at the start of a new line in the report. Each line has max 2 slots for info.
        If the line is short, we can fit a second field, if it is too long, we get an automatic linebreak.
        If it is in between, we create an empty field to prevent the inline from looking ugly"""

        name = str(name)
        value = str(value)

        nwidth = afm.string_width_height(unidecode(name))
        vwidth = afm.string_width_height(unidecode(value))
        w = max(nwidth[0], vwidth[0])

        embed.add_field(name=name, value=value, inline=False if w > 12500 and self.cursor_pos % 2 == 1 else True)
        self.cursor_pos += 1

        # create an empty field if we are at the second slot and the
        # width of the first slot is between the critical values
        if self.cursor_pos % 2 == 1 and 11600 < w < 20000:
            embed.add_field(name='\u200b', value='\u200b', inline=True)
            self.cursor_pos += 1

        return embed

    async def generate_embed(self):
        """Generate Discord Report"""
        self.cursor_pos = 0
        embed = discord.Embed(title='', colour=SETTINGS.color)  # f'Status: {"Open" if self.is_open() else "Closed"}'
        embed.set_author(name=f' >> {self.short} ',
                         icon_url=SETTINGS.author_icon)
        embed.set_thumbnail(url=SETTINGS.report_icon)

        # ## adding fields with custom, length sensitive function
        if not await self.is_active():
            embed = self.add_field_custom(name='**INACTIVE**',
                                                value=f'This poll is inactive until '
                                                      f'{self.get_activation_date(string=True)}.',
                                                embed=embed
                                                )

        embed = self.add_field_custom(name='**Poll Question**', value=self.name, embed=embed)

        if self.roles != ['@everyone']:
            embed = self.add_field_custom(name='**Roles**', value=', '.join(self.roles), embed=embed)
            if len(self.weights_roles) > 0:
                weights = []
                for r, n in zip(self.weights_roles, self.weights_numbers):
                    weights.append(f'{r}: {n}')
                embed = self.add_field_custom(name='**Weights**', value=', '.join(weights), embed=embed)

        embed = self.add_field_custom(name='**Anonymous**', value=self.anonymous, embed=embed)

        if self.duration != 0:
            embed = self.add_field_custom(name='**Deadline**', value=await self.get_poll_status(), embed=embed)

        # embed = self.add_field_custom(name='**Author**', value=self.author.name, embed=embed)
        await self.load_vote_counts()
        if self.options_reaction_default:
            if await self.is_open():
                text = f'**Score** '
                if self.multiple_choice == 0:
                    text += f'(Multiple Choice)'
                elif self.multiple_choice == 1:
                    text += f'(Single Choice)'
                else:
                    text += f'({self.multiple_choice} Choices)'
            else:
                text = f'**Final Score**'

            vote_display = []
            for i, r in enumerate(self.options_reaction):
                if self.hide_count and await self.is_open():
                    vote_display.append(f'{r}')
                else:
                    vote_display.append(f'{r} {self.vote_counts_weighted.get(i, 0)}')
            embed = self.add_field_custom(name=text, value=' '.join(vote_display), embed=embed)
        else:
            # embed.add_field(name='\u200b', value='\u200b', inline=False)
            if await self.is_open():
                head = ""
                if self.multiple_choice == 0:
                    head += 'You can vote for multiple options:'
                elif self.multiple_choice == 1:
                    head += 'You have 1 vote:'
                else:
                    head += f'You can vote for {self.multiple_choice} options:'
            else:
                head = f'Final Results of the Poll '
                if self.multiple_choice == 0:
                    head += '(Multiple Choice):'
                elif self.multiple_choice == 1:
                    head += '(Single Choice):'
                else:
                    head += f'(With up to {self.multiple_choice} choices):'
            # embed = self.add_field_custom(name='**Options**', value=text, embed=embed)
            options_text = '**' + head + '**\n'
            # display options
            for i, r in enumerate(self.options_reaction):
                custom_icon = ''
                if i in self.survey_flags:
                    custom_icon = '🖊'
                if self.options_reaction_emoji_only:
                    options_text += f'{r}{custom_icon}'
                else:
                    options_text += f':regional_indicator_{ascii_lowercase[i]}:{custom_icon} {r}'
                if self.hide_count and self.open:
                    options_text += '\n'
                else:
                    options_text += f' **- {self.vote_counts_weighted.get(i, 0)} Votes**\n'
                # embed = self.add_field_custom(
                #     name=f':regional_indicator_{ascii_lowercase[i]}:{custom_icon} {self.count_votes(i)}',
                #     value=r,
                #     embed=embed
                # )
            embed.add_field(name='\u200b', value=options_text, inline=False)

        custom_text = ""
        if len(self.survey_flags) > 0:
            custom_text = " 🖊 next to an option means you can submit a custom answer."
        embed.set_footer(text='React with ❔ to get info. It is not a vote option.' + custom_text)
        return embed

    async def post_embed(self, destination):
        msg = await destination.send(embed=await self.generate_embed())
        if self.reaction and await self.is_open() and await self.is_active():
            if self.options_reaction_default:
                for r in self.options_reaction:
                    await msg.add_reaction(r)
                await msg.add_reaction('❔')
                return msg
            else:
                for i, r in enumerate(self.options_reaction):
                    if self.options_reaction_emoji_only:
                        await msg.add_reaction(r)
                    else:
                        await msg.add_reaction(AZ_EMOJIS[i])
                await msg.add_reaction('❔')
                return msg
        elif not await self.is_open():
            await msg.add_reaction('❔')
            await msg.add_reaction('📎')
        else:
            return msg

    def get_duration_with_tz(self):
        if self.duration == 0:
            return 0
        elif isinstance(self.duration, datetime.datetime):
            dt = self.duration
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                dt = pytz.utc.localize(dt)
            if isinstance(self.duration_tz, float):
                tz = possible_timezones(self.duration_tz, common_only=True)
                if not tz:
                    tz = pytz.timezone('UTC')
                else:
                    # choose one valid timezone with the offset
                    try:
                        tz = pytz.timezone(tz[0])
                    except UnknownTimeZoneError:
                        tz = pytz.UTC
            else:
                try:
                    tz = pytz.timezone(self.duration_tz)
                except UnknownTimeZoneError:
                    tz = pytz.UTC

            return dt.astimezone(tz)

    def get_activation_with_tz(self):
        if self.activation == 0:
            return 0
        elif isinstance(self.activation, datetime.datetime):
            dt = self.activation
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                dt = pytz.utc.localize(dt)
            if isinstance(self.activation_tz, float):
                tz = possible_timezones(self.activation_tz, common_only=True)
                if not tz:
                    tz = pytz.timezone('UTC')
                else:
                    # choose one valid timezone with the offset
                    tz = pytz.timezone(tz[0])
            else:
                tz = pytz.timezone(self.activation_tz)

            return dt.astimezone(tz)

    async def get_deadline(self, string=False):
        if self.duration == 0:
            if string:
                return 'No deadline'
            else:
                return 0
        else:
            deadline = self.get_duration_with_tz()
            if string:
                return deadline.strftime('%d-%b-%Y %H:%M %Z')
            else:
                return deadline

    def get_activation_date(self, string=False):
        if self.activation == 0:
            if string:
                return 'manually activated'
            else:
                return 0
        else:
            activation_date = self.get_activation_with_tz()
            if string:
                return activation_date.strftime('%d-%b-%Y %H:%M %Z')
            else:
                return activation_date

    async def get_poll_status(self):
        if await self.is_open():
            return await self.get_deadline(string=True)
        else:
            return 'Poll is closed.'

    async def vote(self, user, option, message):
        if not await self.is_open():
            # refresh to show closed poll
            await self.refresh(message, force=True)
            self.bot.loop.create_task(message.clear_reactions())
            self.bot.loop.create_task(message.add_reaction('❔'))
            self.bot.loop.create_task(message.add_reaction('📎'))
            return
        elif not await self.is_active():
            return

        # find index of choice or cancel vote
        choice = 'invalid'
        if self.options_reaction_default:
            if option in self.options_reaction:
                choice = self.options_reaction.index(option)
        else:
            if option in AZ_EMOJIS:
                choice = AZ_EMOJIS.index(option)
            elif self.options_reaction_emoji_only:
                for i, opts in enumerate(self.options_reaction):
                    if option in opts:
                        choice = i

        if choice == 'invalid':
            return

        # get highest weight
        weight = 1
        if len(self.weights_roles) > 0:
            valid_weights = [self.weights_numbers[self.weights_roles.index(r)] for r in
                             list(set([n.name for n in user.roles]).intersection(set(self.weights_roles)))]
            if len(valid_weights) > 0:
                weight = max(valid_weights)

        # unvote for anon and hidden count
        if self.anonymous or self.hide_count and user != None:
            vote = await Vote.load_from_db(self.bot, self.id, user.id, choice)
            if vote:
                await vote.delete_from_db()
                await self.refresh(message)
                return

        # check if already voted for the same choice
        votes = await self.load_votes_for_user(user.id)
        for v in votes:
            if v.choice == choice:
                return  # already voted

        # check if max votes exceeded
        if 0 < self.multiple_choice <= len(votes):
            say_text = f'You have reached the **maximum choices of {self.multiple_choice}** for this poll. ' \
                f'Before you can vote again, you need to unvote one of your choices.\n' \
                f'Your current choices are:\n'
            for v in votes:
                if self.options_reaction_default:
                    say_text += f'{self.options_reaction[v.choice]}\n'
                else:
                    if not self.options_reaction_emoji_only:
                        say_text += f'{AZ_EMOJIS[v.choice]} '
                    say_text += f'{self.options_reaction[v.choice]}\n'
            embed = discord.Embed(title='', description=say_text, colour=SETTINGS.color)
            embed.set_author(name='Pollmaster', icon_url=SETTINGS.author_icon)
            self.bot.loop.create_task(user.send(embed=embed))
            return

        answer = ''
        if choice in self.survey_flags:
            answer = await self.ask_for_input_dm(
                user,
                "Custom Answer",
                "For this vote option you can provide a custom reply. "
                "Note that everyone will be able to see the answer. If you don't want to provide a "
                "custom answer, type \"-\""
            )
            if not answer or answer.lower() == "-":
                answer = "No Answer"

        if self.anonymous and self.hide_count:
            self.bot.loop.create_task(user.send(f'Your vote for **{self.options_reaction[choice]}** has been counted.'))

        # commit
        vote = Vote(self.bot, self.id, user.id, choice, weight, answer)
        await vote.save_to_db()
        if not self.hide_count:
            await self.refresh(message)

    async def unvote(self, user, option, message):
        if not await self.is_open():
            # refresh to show closed poll
            await self.refresh(message, force=True)
            self.bot.loop.create_task(message.clear_reactions())
            return
        elif not await self.is_active():
            return

        # find index of choice or cancel vote
        choice = 'invalid'
        if self.options_reaction_default:
            if option in self.options_reaction:
                choice = self.options_reaction.index(option)
        else:
            if option in AZ_EMOJIS:
                choice = AZ_EMOJIS.index(option)
            elif self.options_reaction_emoji_only:
                for i, opts in enumerate(self.options_reaction):
                    if option in opts:
                        choice = i

        if choice == 'invalid':
            return

        vote = await Vote.load_from_db(self.bot, self.id, user.id, choice)
        if vote:
            await vote.delete_from_db()

        if not self.hide_count:
            await self.refresh(message)
        elif self.anonymous:
            self.bot.loop.create_task(f'Your vote for **{self.options_reaction[choice]}** has been removed.')

    def has_required_role(self, user):
        try:
            return not set([r.name for r in user.roles]).isdisjoint(self.roles)
        except AttributeError:
            return False

    async def refresh(self, message, await_=False, force=False):
        # dont refresh if there was a refresh in the past 5 seconds
        if not force and self.bot.refresh_blocked.get(str(self.id), 0)-time.time() > 0:
            self.bot.refresh_queue[str(self.id)] = message
            return
        self.bot.refresh_blocked[str(self.id)] = time.time() + 5
        if await_:
            await message.edit(embed=await self.generate_embed())
        else:
            self.bot.loop.create_task(message.edit(embed=await self.generate_embed()))
