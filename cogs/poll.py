import codecs
import datetime
import logging
import os
import re
from uuid import uuid4
from string import ascii_lowercase, printable

import dateparser
import pytz
from matplotlib import rcParams
from matplotlib.afm import AFM
from unidecode import unidecode

import discord
from essentials.multi_server import get_pre
from essentials.exceptions import *
from essentials.settings import SETTINGS

logger = logging.getLogger('bot')

## Helvetica is the closest font to Whitney (discord uses Whitney) in afm
## This is used to estimate text width and adjust the layout of the embeds
afm_fname = os.path.join(rcParams['datapath'], 'fonts', 'afm', 'phvr8a.afm')
with open(afm_fname, 'rb') as fh:
    afm = AFM(fh)

## A-Z Emojis for Discord
AZ_EMOJIS = [(b'\\U0001f1a'.replace(b'a', bytes(hex(224 + (6 + i))[2:], "utf-8"))).decode("unicode-escape") for i in
             range(26)]
class Poll:

    def __init__(self, bot, ctx=None, server=None, channel=None, load=False):

        self.bot = bot
        self.cursor_pos = 0

        if not load and ctx:
            if server is None:
                server = ctx.message.server

            if channel is None:
                channel = ctx.message.channel

            self.author = ctx.message.author

            self.server = server
            self.channel = channel

            self.name = "Quick Poll"
            self.short = str(uuid4())[0:23]
            self.anonymous = False
            self.reaction = True
            self.multiple_choice = False
            self.options_reaction = ['yes', 'no']
            self.options_reaction_default = False
            # self.options_traditional = []
            # self.options_traditional_default = False
            self.roles = ['@everyone']
            self.weights_roles = []
            self.weights_numbers = []
            self.duration = 0
            self.duration_tz = 'UTC'
            self.time_created = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

            self.open = True
            self.active = True
            self.activation = 0
            self.activation_tz = 'UTC'
            self.votes = {}

    async def is_open(self, update_db=True):
        if open and self.duration != 0 \
                and datetime.datetime.utcnow().replace(tzinfo=pytz.utc) > self.duration.replace(tzinfo=pytz.utc):
            self.open = False
            if update_db:
                await self.save_to_db()
        return self.open

    async def is_active(self, update_db=True):
        if not self.active and self.activation != 0 \
                and datetime.datetime.utcnow().replace(tzinfo=pytz.utc) > self.activation.replace(tzinfo=pytz.utc):
            self.active = True
            if update_db:
                await self.save_to_db()
        return self.active

    async def wizard_says(self, text, footer=True):
        embed = discord.Embed(title="Poll creation Wizard", description=text, color=SETTINGS.color)
        if footer: embed.set_footer(text="Type `stop` to cancel the wizard.")
        return await self.bot.say(embed=embed)

    async def wizard_says_edit(self, message, text, add=False):
        if add and message.embeds.__len__() > 0:
            text = message.embeds[0]['description'] + text
        embed = discord.Embed(title="Poll creation Wizard", description=text, color=SETTINGS.color)
        embed.set_footer(text="Type `stop` to cancel the wizard.")
        return await self.bot.edit_message(message, embed=embed)

    async def add_error(self, message, error):
        text = ''
        if message.embeds.__len__() > 0:
            text = message.embeds[0]['description'] + '\n\n:exclamation: ' + error
        return await self.wizard_says_edit(message, text)

    async def add_vaild(self, message, string):
        text = ''
        if message.embeds.__len__() > 0:
            text = message.embeds[0]['description'] + '\n\n✅ ' + string
        return await self.wizard_says_edit(message, text)

    async def get_user_reply(self):
        """Pre-parse user input for wizard"""
        reply = await self.bot.wait_for_message(author=self.author)
        if reply and reply.content:
            if reply.content.startswith(await get_pre(self.bot, reply)):
                await self.wizard_says(f'You can\'t use bot commands during the Poll Creation Wizard.\n'
                                       f'Stopping the Wizard and then executing the command:\n`{reply.content}`',
                                       footer=False)
                raise StopWizard
            elif reply.content.lower() == 'stop':
                await self.wizard_says('Poll Wizard stopped.', footer=False)
                raise StopWizard

            else:
                return reply.content
        else:
            raise InvalidInput

    def sanitize_string(self, string):
        """Sanitize user input for wizard"""
        # sanitize input
        if string is None:
            raise InvalidInput
        string = re.sub("[^{}]+".format(printable), "", string)
        if set(string).issubset(set(' ')):
            raise InvalidInput
        return string

    async def set_name(self, force=None):
        """Set the Question / Name of the Poll."""
        async def get_valid(in_reply):
            if not in_reply:
                raise InvalidInput
            min_len = 3
            max_len = 200
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                self.name = await get_valid(reply)
                await self.add_vaild(message, self.name)
                break
            except InvalidInput:
                await self.add_error(message, '**Keep the name between 3 and 200 valid characters**')

    async def set_short(self, force=None):
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
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


    async def set_preparation(self, force=None):
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

        try:
            dt = await get_valid(force)
            self.activation = dt
            if self.activation != 0:
                self.activation_tz = dt.tzinfo.tzname(dt)
            self.active = False
            return
        except InputError:
            pass

        text = ("This poll will be created inactive. You can either schedule activation at a certain date or activate "
                "it manually. **Type `0` to activate it manually or tell me when you want to activate it** by "
                "typing an absolute or relative date. You can specify a timezone if you want.\n"
                "Examples: `in 2 days`, `next week CET`, `may 3rd 2019`, `9.11.2019 9pm EST` ")
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                dt = await get_valid(reply)
                self.activation = dt
                if self.activation == 0:
                    await self.add_vaild(message, 'manually activated')
                else:
                    self.activation_tz = dt.tzinfo.tzname(dt)
                    await self.add_vaild(message, self.activation.strftime('%d-%b-%Y %H:%M %Z'))
                self.active = False
                break
            except InvalidInput:
                await self.add_error(message, '**I could not understand that format.**')
            except TypeError:
                await self.add_error(message, '**Type Error.**')
            except DateOutOfRange as e:
                await self.add_error(message, f'**{e.date.strftime("%d-%b-%Y %H:%M")} is in the past.**')

    async def set_anonymous(self, force=None):
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                self.anonymous = await get_valid(reply)
                await self.add_vaild(message, f'{"Yes" if self.anonymous else "No"}')
                break
            except InvalidInput:
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')


    # async def set_reaction(self, force=None):
    #     ''' Currently everything is reaction, this is not needed'''
    #     if force is not None and force in [True, False]:
    #         self.reaction = force
    #         return
    #     if self.stopped: return
    #     text = """**Do you want your users to vote by adding reactions to the poll? Type `yes` or `no`.**
    #     Reaction voting typically has the following properties:
    #     :small_blue_diamond: Voting is quick and painless (no typing required)
    #     :small_blue_diamond: Multiple votes are possible
    #     :small_blue_diamond: Not suited for a large number of options
    #     :small_blue_diamond: Not suited for long running polls"""
    #     message = await self.wizard_says(text)
    #
    #     reply = ''
    #     while reply not in ['yes', 'no']:
    #         if reply != '':
    #             await self.add_error(message, '**You can only answer with `yes` or `no`!**')
    #         reply = await self.get_user_reply()
    #         if self.stopped: break
    #         if isinstance(reply, str): reply = reply.lower()
    #
    #     self.reaction = reply == 'yes'
    #     return self.reaction

    async def set_multiple_choice(self, force=None):
        """Determine if poll is multiple choice."""
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
            self.multiple_choice = await get_valid(force)
            return
        except InputError:
            pass

        text = ("**Should users be able to vote for multiple options?**\n"
                "\n"
                "`0 - No`\n"
                "`1  - Yes`\n"
                "\n"
                "If you type `0` or `no`, a new vote will override the old vote. "
                "Otherwise the users can vote for as many options as they like.")
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                self.multiple_choice = await get_valid(reply)
                await self.add_vaild(message, f'{"Yes" if self.multiple_choice else "No"}')
                break
            except InvalidInput:
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')


    async def set_options_reaction(self, force=None):
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
            elif 1 < split.__len__() <= 26:
                split = [self.sanitize_string(o) for o in split]
                if any([len(o) < 1 for o in split]):
                    raise InvalidInput
                else:
                    return split
            else:
                raise WrongNumberOfArguments

        def get_preset_options(number):
            if number == 1:
                return ['✅', '❎']
            elif number == 2:
                return ['👍', '🤐', '👎']
            elif number == 3:
                return ['😍', '👍', '🤐', '👎', '🤢']
            elif number == 4:
                return ['in favour', 'against', 'abstaining']


        try:
            options = await get_valid(force)
            self.options_reaction_default = False
            if isinstance(options, int):
                self.options_reaction = get_preset_options(options)
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
                "**4** - in favour, against, abstain\n"
                "\n"
                "Example for custom options:\n"
                "**apple juice, banana ice cream, kiwi slices** ")
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                options = await get_valid(reply)
                self.options_reaction_default = False
                if isinstance(options, int):
                    self.options_reaction = get_preset_options(options)
                    if options <= 3:
                        self.options_reaction_default = True
                else:
                    self.options_reaction = options
                await self.add_vaild(message, f'{", ".join(self.options_reaction)}')
                break
            except InvalidInput:
                await self.add_error(message,
                                     '**Invalid entry. Type `1`, `2`, `3` or `4` or a comma separated list of '
                                     'up to 26 options.**')
            except WrongNumberOfArguments:
                await self.add_error(message,
                                     '**You need more than 1 option! Type them in a comma separated list.**')


    async def set_roles(self, force=None):
        """Set role restrictions for the Poll."""
        async def get_valid(in_reply, roles):
            n_roles = roles.__len__()
            if not in_reply:
                raise InvalidInput

            split = [self.sanitize_string(r.strip()) for r in in_reply.split(",")]
            if split.__len__() == 1 and split[0] in ['0', 'all', 'everyone']:
                return ['@everyone']

            if n_roles <= 20:
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
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

    # async def set_options_traditional(self, force=None):
    #     '''Currently not used as everything is reaction based'''
    #     if force is not None:
    #         self.options_traditional = force
    #         return
    #     if self.stopped: return
    #     text = """**Next you chose from the possible set of options/answers for your poll.**
    #     Type the corresponding number or type your own options, separated by commas.
    #
    #     **1** - yes, no
    #     **2** - in favour, against, abstain
    #     **3** - love it, like it, don't care, meh, hate it
    #
    #     If you write your own options they will be listed and can be voted for.
    #     To use your custom options type them like this:
    #     **apple juice, banana ice cream, kiwi slices**"""
    #     message = await self.wizard_says(text)
    #
    #     reply = ''
    #     while reply == '' or (reply.split(",").__len__() < 2 and reply not in ['1', '2', '3']) \
    #             or (reply.split(",").__len__() > 99 and reply not in ['1', '2', '3']):
    #         if reply != '':
    #             await self.add_error(message,
    #                                  '**Invalid entry. Type `1` `2` or `3` or a comma separated list (max. 99 options).**')
    #         reply = await self.get_user_reply()
    #         if self.stopped: break
    #
    #     if reply == '1':
    #         self.options_traditional = ['yes, no']
    #     elif reply == '2':
    #         self.options_traditional = ['in favour', 'against', 'abstain']
    #     elif reply == '3':
    #         self.options_traditional = ['love it', 'like it', 'don\'t care', 'meh', 'hate it']
    #     else:
    #         self.options_traditional = [r.strip() for r in reply.split(",")]
    #     return self.options_traditional

    async def set_weights(self, force=None):
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
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

    async def set_duration(self, force=None):
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
            self.duration = await get_valid(force)
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
        message = await self.wizard_says(text)

        while True:
            try:
                reply = await self.get_user_reply()
                dt = await get_valid(reply)
                self.duration = dt
                if self.duration == 0:
                    await self.add_vaild(message, 'until closed manually')
                else:
                    self.duration_tz = dt.tzinfo.tzname(dt)
                    await self.add_vaild(message, self.duration.strftime('%d-%b-%Y %H:%M %Z'))
                break
            except InvalidInput:
                await self.add_error(message, '**I could not understand that format.**')
            except TypeError:
                await self.add_error(message, '**Type Error.**')
            except DateOutOfRange as e:
                await self.add_error(message, f'**{e.date.strftime("%d-%b-%Y %H:%M")} is in the past.**')

    def finalize(self):
        self.time_created = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)


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
            'reaction': self.reaction,
            'multiple_choice': self.multiple_choice,
            'options_reaction': self.options_reaction,
            'reaction_default': self.options_reaction_default,
            #'options_traditional': self.options_traditional,
            'roles': self.roles,
            'weights_roles': self.weights_roles,
            'weights_numbers': self.weights_numbers,
            'duration': self.duration,
            'duration_tz': self.duration_tz,
            'time_created': self.time_created,
            'open': await self.is_open(update_db=False),
            'active': await self.is_active(update_db=False),
            'activation': self.activation,
            'activation_tz': self.activation_tz,
            'votes': self.votes
        }

    async def to_export(self):
        """Create report and return string"""
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
            votes = self.count_votes(i, weighted=True)
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
                  f'Multiple choice: {"Yes" if self.multiple_choice else "No"}\n'
                  f'Answer options: {", ".join(self.options_reaction)}\n'
                  f'Allowed roles: {", ".join(self.roles) if self.roles.__len__() > 0 else "@everyone"}\n'
                  f'Weights for roles: {weight_str}\n'
                  f'Deadline: {deadline_str}\n'
                  f'--------------------------------------------\n'
                  f'POLL RESULTS\n'
                  f'--------------------------------------------\n'
                  f'Number of participants: {self.votes.__len__()}\n'
                  f'Raw results: {", ".join([str(o)+": "+str(self.count_votes(i, weighted=False)) for i,o in enumerate(self.options_reaction)])}\n'
                  f'Weighted results: {", ".join([str(o)+": "+str(self.count_votes(i, weighted=True)) for i,o in enumerate(self.options_reaction)])}\n'
                  f'Winning option{"s" if winning_options.__len__() > 1 else ""}: {", ".join(winning_options)} with {winning_votes} votes\n')

        if not self.anonymous:
            export += '--------------------------------------------\n' \
                      'DETAILED POLL RESULTS\n' \
                      '--------------------------------------------'

            for user_id in self.votes:
                member = self.server.get_member(user_id)
                if self.votes[user_id]['choices'].__len__() == 0:
                    continue
                export += f'\n{member.name}'
                if self.votes[user_id]['weight'] != 1:
                    export += f' (weight: {self.votes[user_id]["weight"]})'
                export += ': ' + ', '.join([self.options_reaction[c] for c in self.votes[user_id]['choices']])
            export += '\n'
        else:
            export += '--------------------------------------------\n' \
                      'LIST OF PARTICIPANTS\n' \
                      '--------------------------------------------'

            for user_id in self.votes:
                member = self.server.get_member(user_id)
                if self.votes[user_id]['choices'].__len__() == 0:
                    continue
                export += f'\n{member.name}'
                if self.votes[user_id]['weight'] != 1:
                    export += f' (weight: {self.votes[user_id]["weight"]})'
                # export += ': ' + ', '.join([self.options_reaction[c] for c in self.votes[user_id]['choices']])
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
            fn = 'export/' + str(self.server.id) + '_' + str(self.short) + '.txt'
            with codecs.open(fn, 'w', 'utf-8') as outfile:
                outfile.write(await self.to_export())
            return fn
        else:
            return None

    async def from_dict(self, d):
        self.server = self.bot.get_server(str(d['server_id']))
        self.channel = self.bot.get_channel(str(d['channel_id']))
        self.author = await self.bot.get_user_info(str(d['author']))
        self.name = d['name']
        self.short = d['short']
        self.anonymous = d['anonymous']
        self.reaction = d['reaction']
        self.multiple_choice = d['multiple_choice']
        self.options_reaction = d['options_reaction']
        self.options_reaction_default = d['reaction_default']
        # self.options_traditional = d['options_traditional']
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
        query = await bot.db.polls.find_one({'server_id': str(server_id), 'short': str(short)})
        if query is not None:
            p = Poll(bot, ctx, load=True)
            await p.from_dict(query)
            return p
        else:
            return None

    async def add_field_custom(self, name, value, embed):
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

        # create an empty field if we are at the second slot and the width of the first slot is between the critical values
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
            embed = await self.add_field_custom(name='**INACTIVE**',
                                                value=f'This poll is inactive until '
                                                      f'{self.get_activation_date(string=True)}.',
                                                embed=embed
                                                )

        embed = await self.add_field_custom(name='**Poll Question**', value=self.name, embed=embed)

        embed = await self.add_field_custom(name='**Roles**', value=', '.join(self.roles), embed=embed)
        if len(self.weights_roles) > 0:
            weights = []
            for r, n in zip(self.weights_roles, self.weights_numbers):
                weights.append(f'{r}: {n}')
            embed = await self.add_field_custom(name='**Weights**', value=', '.join(weights), embed=embed)

        embed = await self.add_field_custom(name='**Anonymous**', value=self.anonymous, embed=embed)

        # embed = await self.add_field_custom(name='**Multiple Choice**', value=self.multiple_choice, embed=embed)
        embed = await self.add_field_custom(name='**Deadline**', value=await self.get_poll_status(), embed=embed)
        embed = await self.add_field_custom(name='**Author**', value=self.author.name, embed=embed)

        if self.reaction:
            if self.options_reaction_default:
                if await self.is_open():
                    text = f'**Score** '
                    text += '*(Multiple Choice)*' if self.multiple_choice \
                        else '*(Single Choice)*'
                else:
                    text = f'**Final Score**'

                vote_display = []
                for i, r in enumerate(self.options_reaction):
                    vote_display.append(f'{r} {self.count_votes(i)}')
                embed = await self.add_field_custom(name=text, value=' '.join(vote_display), embed=embed)
            else:
                embed.add_field(name='\u200b', value='\u200b', inline=False)
                if await self.is_open():
                    text = f'*Vote by adding reactions to the poll*. '
                    text += '*You can vote for multiple options.*' if self.multiple_choice \
                        else '*You have 1 vote, but can change it.*'
                else:
                    text = f'*Final Results of the {"multiple choice" if self.multiple_choice else "single choice"} Poll.*'
                embed = await self.add_field_custom(name='**Options**', value=text, embed=embed)
                for i, r in enumerate(self.options_reaction):
                    embed = await self.add_field_custom(
                        name=f':regional_indicator_{ascii_lowercase[i]}: {self.count_votes(i)}',
                        value=r,
                        embed=embed
                    )
        # else:
        #     embed = await self.add_field_custom(name='**Options**', value=', '.join(self.get_options()), embed=embed)

        embed.set_footer(text='bot is in development')

        return embed

    async def post_embed(self, destination=None):
        if destination is None:
            msg = await self.bot.say(embed=await self.generate_embed())
        else:
            msg = await self.bot.send_message(destination=destination, embed= await self.generate_embed())
        if self.reaction and await self.is_open() and await self.is_active():
            if self.options_reaction_default:
                for r in self.options_reaction:
                    await self.bot.add_reaction(
                        msg,
                        r
                    )
                return msg
            else:
                for i, r in enumerate(self.options_reaction):
                    await self.bot.add_reaction(
                        msg,
                        AZ_EMOJIS[i]
                    )
                return msg
        elif not await self.is_open():
            await self.bot.add_reaction(msg, '📎')
        else:
            return msg

    # def get_options(self):
    #     if self.reaction:
    #         return self.options_reaction
    #     else:
    #         return self.options_traditional

    async def get_deadline(self, string=False):
        if self.duration == 0:
            if string:
                return 'No deadline'
            else:
                return 0
        else:
            deadline = self.duration
            if deadline.tzinfo is None or deadline.tzinfo.utcoffset(deadline) is None:
                deadline = pytz.utc.localize(deadline)
            tz = pytz.timezone(self.duration_tz)
            deadline = deadline.astimezone(tz)
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
            activation_date = self.activation
            if activation_date.tzinfo is None or activation_date.tzinfo.utcoffset(activation_date) is None:
                activation_date = pytz.utc.localize(activation_date)
            tz = pytz.timezone(self.activation_tz)
            activation_date = activation_date.astimezone(tz)
            if string:
                return activation_date.strftime('%d-%b-%Y %H:%M %Z')
            else:
                return activation_date

    async def get_poll_status(self):
        if await self.is_open():
            return await self.get_deadline(string=True)
        else:
            return 'Poll is closed.'

    def count_votes(self, option, weighted=True):
        '''option: number from 0 to n'''
        if weighted:
            return sum([self.votes[c]['weight'] for c in [u for u in self.votes] if option in self.votes[c]['choices']])
        else:
            return sum([1 for c in [u for u in self.votes] if option in self.votes[c]['choices']])


    async def vote(self, user, option, message):
        if not await self.is_open():
            # refresh to show closed poll
            await self.bot.edit_message(message, embed=await self.generate_embed())
            await self.bot.clear_reactions(message)
            return
        elif not await self.is_active():
            return

        choice = 'invalid'
        already_voted = False

        # get weight
        weight = 1
        if self.weights_roles.__len__() > 0:
            valid_weights = [self.weights_numbers[self.weights_roles.index(r)] for r in
                             list(set([n.name for n in user.roles]).intersection(set(self.weights_roles)))]
            if valid_weights.__len__() > 0:
                weight = max(valid_weights)

        if str(user.id) not in self.votes:
            self.votes[user.id] = {'weight': weight, 'choices': []}
        else:
            self.votes[user.id]['weight'] = weight

        if self.reaction:
            if self.options_reaction_default:
                if option in self.options_reaction:
                    choice = self.options_reaction.index(option)
            else:
                if option in AZ_EMOJIS:
                    choice = AZ_EMOJIS.index(option)

            if choice != 'invalid':
                if self.multiple_choice:
                    if choice in self.votes[user.id]['choices'] and self.anonymous:
                        # anonymous multiple choice -> can't unreact so we toggle with react
                        await self.unvote(user, option, message)
                        return
                    self.votes[user.id]['choices'].append(choice)
                    # if len(self.votes[user.id]['choices']) > len(set(self.votes[user.id]['choices'])):
                    #     already_voted = True
                    self.votes[user.id]['choices'] = list(set(self.votes[user.id]['choices']))
                else:
                    if [choice] == self.votes[user.id]['choices']:
                        already_voted = True
                    else:
                        self.votes[user.id]['choices'] = [choice]
        else:
            pass

        # commit
        await self.save_to_db()

        # refresh
        if not already_voted:
            # edit message if there is a real change
            await self.bot.edit_message(message, embed=await self.generate_embed())
            pass

    async def unvote(self, user, option, message):
        if not await self.is_open():
            # refresh to show closed poll
            await self.bot.edit_message(message, embed=await self.generate_embed())
            await self.bot.clear_reactions(message)
            return
        elif not await self.is_active():
            return

        if str(user.id) not in self.votes: return

        choice = 'invalid'
        if self.reaction:
            if self.options_reaction_default:
                if option in self.options_reaction:
                    choice = self.options_reaction.index(option)
            else:
                if option in AZ_EMOJIS:
                    choice = AZ_EMOJIS.index(option)

            if choice != 'invalid' and choice in self.votes[user.id]['choices']:
                try:
                    self.votes[user.id]['choices'].remove(choice)
                    await self.save_to_db()
                    await self.bot.edit_message(message, embed=await self.generate_embed())
                except ValueError:
                    pass

    async def has_required_role(self, user):
        return not set([r.name for r in user.roles]).isdisjoint(self.roles)
