import codecs
import datetime
import os
import time
from math import ceil
from uuid import uuid4
from string import ascii_lowercase

from matplotlib import rcParams
from matplotlib.afm import AFM
from unidecode import unidecode

import discord
from cogs.utils import get_pre
from utils.poll_name_generator import generate_word

## Helvetica is the closest font to Whitney (discord uses Whitney) in afm
## This is used to estimate text width and adjust the layout of the embeds'''
afm_fname = os.path.join(rcParams['datapath'], 'fonts', 'afm', 'phvr8a.afm')
with open(afm_fname, 'rb') as fh:
    afm = AFM(fh)

## A-Z Emojis for Discord
AZ_EMOJIS = [(b'\\U0001f1a'.replace(b'a', bytes(hex(224 + (6 + i))[2:], "utf-8"))).decode("unicode-escape") for i in
             range(26)]


class Poll:

    def __init__(self, bot, ctx=None, server=None, channel=None, load=False):

        self.bot = bot
        self.color = discord.Colour(int('7289da', 16))
        self.cursor_pos = 0

        if not load and ctx:
            if server is None:
                server = ctx.message.server

            if channel is None:
                channel = ctx.message.channel

            self.author = ctx.message.author
            self.stopped = False

            self.server = server
            self.channel = channel

            self.name = "Quick Poll"
            self.short = str(uuid4())
            self.anonymous = False
            self.reaction = True
            self.multiple_choice = False
            self.options_reaction = ['yes', 'no']
            self.options_reaction_default = False
            self.options_traditional = []
            # self.options_traditional_default = False
            self.roles = ['@everyone']
            self.weights_roles = []
            self.weights_numbers = []
            self.duration = 0
            self.time_created = time.time()

            self.open = True
            self.inactive = False
            self.votes = {}

    def is_open(self):
        if open and self.duration > 0 and self.time_created + self.duration * 60 < time.time():
            self.open = False
        return self.open

    async def wizard_says(self, text, footer=True):
        embed = discord.Embed(title="Poll creation Wizard", description=text,
                              color=self.color)
        if footer: embed.set_footer(text="Type `stop` to cancel the wizard.")
        return await self.bot.say(embed=embed)

    async def wizard_says_edit(self, message, text, add=False):
        if add and message.embeds.__len__() > 0:
            text = message.embeds[0]['description'] + text
        embed = discord.Embed(title="Poll creation Wizard", description=text,
                              color=self.color)
        embed.set_footer(text="Type `stop` to cancel the wizard.")
        return await self.bot.edit_message(message, embed=embed)

    async def add_error(self, message, error):
        text = ''
        if message.embeds.__len__() > 0:
            text = message.embeds[0]['description'] + '\n\n:exclamation: ' + error
        return await self.wizard_says_edit(message, text)

    def check_reply(self, msg):
        if msg and msg.content:
            if msg.content.lower() == 'stop':
                self.stopped = True
                return msg
            elif msg.content.__len__() > 0:
                return msg
        else:
            return None

    async def get_user_reply(self):
        reply = await self.bot.wait_for_message(author=self.author, check=self.check_reply)
        if self.stopped:
            await self.wizard_says('Poll Wizard stopped.', footer=False)
        if reply.content.startswith(await get_pre(self.bot, reply)):
            await self.wizard_says(f'You can\'t use bot commands during the Poll Creation Wizard.\n'
                                   f'Stopping the Wizard and then executing the command:\n`{reply.content}`',
                                   footer=False)
            self.stopped = True
            return 'stop'
        return reply.content

    async def set_name(self, force=None):
        if self.stopped: return
        if force is not None:
            self.name = force
            return
        text = """I will guide you step by step through the creation of your new poll.
        We can do this in a text channel or you can PM me to keep the server clean.
        **How would you like your poll to be called?**
        Try to be descriptive without writing more than one sentence."""
        message = await self.wizard_says(text)

        reply = ''
        while reply.__len__() < 2 or reply.__len__() > 200:
            if reply != '':
                await self.add_error(message, '**Keep the name between 3 and 200 letters**')
            reply = await self.get_user_reply()
            if self.stopped: break
        self.name = reply
        return self.name

    async def set_short(self, force=None):
        if self.stopped: return
        if force is not None:
            self.short = force
            return
        text = """Great. **Now type a unique one word identifier, a label, for your poll.**
         This label will be used to refer to the poll. Keep it short and significant."""
        message = await self.wizard_says(text)

        reply = ''
        while reply.__len__() < 3 or reply.__len__() > 20 or reply.split(" ").__len__() != 1:
            if reply != '':
                await self.add_error(message, '**Only one word between 3 and 20 letters!**')
            reply = await self.get_user_reply()
            if self.stopped: break
            if await self.bot.db.polls.find_one({'server_id': str(self.server.id), 'short': reply}) is not None:
                await self.add_error(message,
                                     f'**The label `{reply}` is not unique on this server. Choose a different one!**')
                reply = ''
            if reply in ['open', 'closed', 'prepared']:
                await self.add_error(message, '**Can\'t use reserved words (open, closed, prepared) as label!**')
                reply = ''

        self.short = reply
        return self.short

    async def set_anonymous(self, force=None):
        if self.stopped: return
        if force is not None:
            self.anonymous = force
            return
        text = """Next you need to decide: **Do you want your poll to be anonymous?**
        
        `0 - No`
        `1  - Yes`
        
        An anonymous poll has the following effects:
        :small_blue_diamond: You will never see who voted for which option
        :small_blue_diamond: Once the poll is closed, you will see who participated (but not their choice)"""
        message = await self.wizard_says(text)

        reply = ''
        while reply not in ['yes', 'no', '1', '0']:
            if reply != '':
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')
            reply = await self.get_user_reply()
            if self.stopped: break
            if isinstance(reply, str):
                reply = reply.lower()

        self.anonymous = reply in ['yes', '1']
        return self.anonymous

    async def set_reaction(self, force=None):
        ''' Currently everything is reaction, this is not needed'''
        if force is not None:
            self.reaction = force
            return
        if self.stopped: return
        text = """**Do you want your users to vote by adding reactions to the poll? Type `yes` or `no`.**
        Reaction voting typically has the following properties:
        :small_blue_diamond: Voting is quick and painless (no typing required)
        :small_blue_diamond: Multiple votes are possible
        :small_blue_diamond: Not suited for a large number of options
        :small_blue_diamond: Not suited for long running polls"""
        message = await self.wizard_says(text)

        reply = ''
        while reply not in ['yes', 'no']:
            if reply != '':
                await self.add_error(message, '**You can only answer with `yes` or `no`!**')
            reply = await self.get_user_reply()
            if self.stopped: break
            if isinstance(reply, str): reply = reply.lower()

        self.reaction = reply == 'yes'
        return self.reaction

    async def set_multiple_choice(self, force=None):
        if self.stopped: return
        if force is not None:
            self.multiple_choice = force
            return
        text = """**Should users be able to vote for multiple options?**
        
        `0 - No`
        `1  - Yes`
        
        If you type `0` or `no`, a new vote will override the old vote. Otherwise the users can vote for as many options as they like."""
        message = await self.wizard_says(text)

        reply = ''
        while reply not in ['yes', 'no', '1', '0']:
            if reply != '':
                await self.add_error(message, '**You can only answer with `yes` | `1` or `no` | `0`!**')
            reply = await self.get_user_reply()
            if self.stopped: break
            if isinstance(reply, str):
                reply = reply.lower()

        self.multiple_choice = reply in ['yes', '1']
        return self.multiple_choice

    async def set_options_reaction(self, force=None):
        if self.stopped: return
        if force is not None:
            self.options_reaction = force
            return
        text = """**Choose the options/answers for your poll.**
        Either type the corresponding number to a predefined option set,
        or type your own options, separated by commas.

        **1** - :white_check_mark: :negative_squared_cross_mark:
        **2** - :thumbsup: :zipper_mouth: :thumbsdown:
        **3** - :heart_eyes: :thumbsup: :zipper_mouth:  :thumbsdown: :nauseated_face:

        Example for custom options:
        **apple juice, banana ice cream, kiwi slices** """
        message = await self.wizard_says(text)

        reply = ''
        while reply == '' or (reply.split(",").__len__() < 2 and reply not in ['1', '2', '3']) \
                or (reply.split(",").__len__() > 26 and reply not in ['1', '2', '3']):
            if reply != '':
                await self.add_error(message,
                                     '**Invalid entry. Type `1`, `2` or `3` or a comma separated list (max. 26 options).**')
            reply = await self.get_user_reply()
            if self.stopped: break

        if reply == '1':
            self.options_reaction = ['✅', '❎']
            self.options_reaction_default = True
        elif reply == '2':
            self.options_reaction = ['👍', '🤐', '👎']
            self.options_reaction_default = True
        elif reply == '3':
            self.options_reaction = ['😍', '👍', '🤐', '👎', '🤢']
            self.options_reaction_default = True
        else:
            self.options_reaction = [r.strip() for r in reply.split(",")]
            self.options_reaction_default = False
        return self.options_reaction

    async def set_options_traditional(self, force=None):
        '''Currently not used as everything is reaction based'''
        if force is not None:
            self.options_traditional = force
            return
        if self.stopped: return
        text = """**Next you chose from the possible set of options/answers for your poll.**
        Type the corresponding number or type your own options, separated by commas.

        **1** - yes, no
        **2** - in favour, against, abstain
        **3** - love it, like it, don't care, meh, hate it

        If you write your own options they will be listed and can be voted for.
        To use your custom options type them like this:
        **apple juice, banana ice cream, kiwi slices**"""
        message = await self.wizard_says(text)

        reply = ''
        while reply == '' or (reply.split(",").__len__() < 2 and reply not in ['1', '2', '3']) \
                or (reply.split(",").__len__() > 99 and reply not in ['1', '2', '3']):
            if reply != '':
                await self.add_error(message,
                                     '**Invalid entry. Type `1` `2` or `3` or a comma separated list (max. 99 options).**')
            reply = await self.get_user_reply()
            if self.stopped: break

        if reply == '1':
            self.options_traditional = ['yes, no']
        elif reply == '2':
            self.options_traditional = ['in favour', 'against', 'abstain']
        elif reply == '3':
            self.options_traditional = ['love it', 'like it', 'don\'t care', 'meh', 'hate it']
        else:
            self.options_traditional = [r.strip() for r in reply.split(",")]
        return self.options_traditional

    async def set_roles(self, force=None):
        if self.stopped: return
        if force is not None:
            self.roles = force
            return
        n_roles = self.server.roles.__len__()
        if n_roles == 0:
            text = "No roles found on this server, skipping to the next step."
            self.roles = ['@everyone']
        elif n_roles <= 15:
            text = """**Choose which roles are allowed to vote.**
            Type `0`, `all` or `everyone` to have no restrictions.
            If you want multiple roles to be able to vote, separate the numbers with a comma.
            """
            text += f'\n`{0} - no restrictions`'
            i = 1
            for role in [r.name for r in self.server.roles]:
                text += f'\n`{i} - {role}`'
                i += 1
            text += """

            Example: `2, 3` 
            """
            message = await self.wizard_says(text)

            reply = ''
            while reply == '' or reply == 'error' or reply == 'toolarge':
                if reply == 'error':
                    await self.add_error(message, f'**Only positive numbers separated by commas are allowed!**')
                elif reply == 'toolarge':
                    await self.add_error(message, f'**Only use valid numbers......**')

                reply = await self.get_user_reply()
                if self.stopped: break

                if reply in ['0', 'all', 'everyone']:
                    break
                if not all([r.strip().isdigit() for r in reply.split(",")]):
                    reply = 'error'
                    continue
                elif any([int(r.strip()) > n_roles for r in reply.split(",")]):
                    reply = 'toolarge'
                    continue
            if reply in ['0', 'all', 'everyone', 'stop']:
                self.roles = ['@everyone']
            else:
                role_names = [r.name for r in self.server.roles]
                self.roles = [role_names[i - 1] for i in [int(r.strip()) for r in reply.split(",")]]

        else:
            text = """**Choose which roles are allowed to vote.**
            Type `0`, `all` or `everyone` to have no restrictions.
            Type out the role names, separated by a comma, to restrict voting to specific roles:
            `moderators, Editors, vips` (hint: role names are case sensitive!)
            """
            message = await self.wizard_says(text)

            reply = ''
            reply_roles = []
            while reply == '':
                reply = await self.get_user_reply()
                if self.stopped: break
                if reply in ['0', 'all', 'everyone']:
                    break
                reply_roles = [r.strip() for r in reply.split(",")]
                invalid_roles = []
                for r in reply_roles:
                    if not any([r == sr for sr in [x.name for x in self.server.roles]]):
                        invalid_roles.append(r)
                if invalid_roles.__len__() > 0:
                    await self.add_error(message,
                                         f'**Invalid roles found: {", ".join(invalid_roles)}. Roles are case-sensitive!**')
                    reply = ''
                    continue

            if reply in ['0', 'all', 'everyone']:
                self.roles = ['@everyone']
            else:
                self.roles = reply_roles
        return self.roles

    async def set_weights(self, force=None):
        if self.stopped: return
        if force is not None and len(force) == 2:
            self.weights_roles = force[0]
            self.weights_numbers = force[1]
            return
        text = """Almost done.
        **Weights allow you to give certain roles more or less effective votes.
        Type `0` or `none` if you don't need any weights.**
        A weight for the role `moderator` of `2` for example will automatically count the votes of all the moderators twice.
        To assign weights type the role, followed by a colon, followed by the weight like this:
        `moderator: 2, newbie: 0.5`"""
        message = await self.wizard_says(text)

        status = 'start'
        roles = []
        weights = []
        while status != 'ok':
            if status != 'start':
                await self.add_error(message, status)
            status = 'ok'
            reply = await self.get_user_reply()
            if self.stopped: break
            roles = []
            weights = []
            if reply.lower() in ['0', 'none']:
                break
            for e in [r.strip() for r in reply.split(",")]:
                if ':' in e:
                    c = [x.strip() for x in e.rsplit(":", 1)]
                    if not any([c[0] == sr for sr in [x.name for x in self.server.roles]]):
                        status = f'**Role `{c[0]}` not found.**'
                        break
                    else:
                        try:
                            c[1] = float(c[1])
                        except ValueError:
                            status = f'**Weight `{c[1]}` for `{c[0]}` is not a number.**'
                            break
                        c[1] = int(c[1]) if c[1].is_integer() else c[1]
                    roles.append(c[0])
                    weights.append(c[1])
                    if len(roles) > len(set(roles)):
                        status = f'**Only assign a weight to a role once. `{c[0]}` is assigned twice.**'
                else:
                    status = f'**No colon found in `{e}`. Use `:` to separate role and weight.**'
                    break

        self.weights_roles = roles
        self.weights_numbers = weights
        return [self.weights_roles, self.weights_numbers]

    async def set_duration(self, force=None):
        if self.stopped: return
        if force is not None and isinstance(force, float):
            self.duration = force
            return
        text = """Last step.
        **How long should your poll be active?**
        Type a number followed by `m`inutes, `h`ours or `d`ays.
        If you want the poll to last indefinitely (until you close it), type `0`.
        You can also type a UTC closing date in this format: dd.mm.yyyy hh:mm
        
        Examples: `5m` or `1 h` or `7d` or `15.8.2019 12:15`"""
        message = await self.wizard_says(text)

        status = 'start'
        duration = 0.0
        while status != 'ok':
            if status != 'start':
                await self.add_error(message, status)
            status = 'ok'
            reply = await self.get_user_reply()
            if self.stopped: break
            if reply == '0': break

            date = self.convert_user_date(reply)
            if isinstance(date, float):
                date = float(ceil(date))
                if date < 0:
                    status = f'**The entered date is in the past. Use a date in the future.**'
                else:
                    print(date)
                    duration = date
            else:
                unit = reply[-1].lower()
                if unit not in ['m', 'h', 'd']:
                    status = f'**{reply} is not a valid format.**'

                duration = reply[:-1].strip()
                try:
                    duration = float(duration)
                except ValueError:
                    status = f'**{reply} is not a valid format.**'

                if unit == 'h':
                    duration *= 60
                elif unit == 'd':
                    duration *= 60 * 24

        self.duration = duration
        return self.duration

    def convert_user_date(self, date):
        try:
            dt = datetime.datetime.strptime(date, '%d.%m.%Y %H:%M')
        except ValueError:
            return False

        print(dt)
        print(datetime.datetime.utcnow())
        return float((dt - datetime.datetime.utcnow()).total_seconds() / 60.0)

    def finalize(self):
        self.time_created = time.time()

    # def __str__(self):
    #     poll_string = f'Poll by user {self.author}\n'
    #     poll_string += f'Name of the poll: {self.name}\n'
    #     poll_string += f'Short of the poll: {self.short}\n'
    #     poll_string += f'Short of the poll: {str(self.anonymous)}\n'
    #     poll_string += f'Options reaction: {",".join(self.options_reaction)}\n'
    #     poll_string += f'Options traditional: {",".join(self.options_traditional)}\n'
    #     poll_string += f'Roles: {",".join(self.roles)}\n'
    #     poll_string += f'WR: {",".join(self.weights_roles)}\n'
    #     poll_string += f'WN: {",".join([str(x) for x in self.weights_numbers])}\n'
    #     poll_string += f'duration: {self.duration} minutes\n'
    #     return poll_string

    def to_dict(self):
        return {
            'server_id': str(self.server.id),
            'channel_id': str(self.channel.id),
            'author': str(self.author.id),
            'name': self.name,
            'short': self.short,
            'anonymous': self.anonymous,
            'reaction': self.reaction,
            'multiple_choice': self.multiple_choice,
            'options_reaction': self.options_reaction,
            'reaction_default': self.options_reaction_default,
            'options_traditional': self.options_traditional,
            'roles': self.roles,
            'weights_roles': self.weights_roles,
            'weights_numbers': self.weights_numbers,
            'duration': self.duration,
            'time_created': self.time_created,
            'open': self.open,
            'votes': self.votes
        }

    def to_export(self):
        # export to txt file

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

        export = (f'--------------------------------------------\n'
                  f'POLLMASTER DISCORD EXPORT\n'
                  f'--------------------------------------------\n'
                  f'Server name (ID): {self.server.name} ({self.server.id})\n'
                  f'Owner of the poll: {self.author.name}\n'
                  f'Time of creation: {datetime.datetime.utcfromtimestamp(self.time_created).strftime("%d-%b-%Y %H:%M") + " UTC"}\n'
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
                  f'Deadline: {self.get_deadline(string=True)}\n'
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

    def export(self):
        if not self.open:
            fn = 'export/' + str(self.server.id) + '_' + str(self.short) + '.txt'
            with codecs.open(fn, 'w', 'utf-8') as outfile:
                outfile.write(self.to_export())
            return fn
        else:
            return None

    async def from_dict(self, d):
        self.server = self.bot.get_server(d['server_id'])
        self.channel = self.bot.get_channel(d['channel_id'])
        self.author = await self.bot.get_user_info(d['author'])
        self.name = d['name']
        self.short = d['short']
        self.anonymous = d['anonymous']
        self.reaction = d['reaction']
        self.multiple_choice = d['multiple_choice']
        self.options_reaction = d['options_reaction']
        self.options_reaction_default = d['reaction_default']
        self.options_traditional = d['options_traditional']
        self.roles = d['roles']
        self.weights_roles = d['weights_roles']
        self.weights_numbers = d['weights_numbers']
        self.duration = d['duration']
        self.time_created = d['time_created']
        self.open = d['open']
        self.open = self.is_open()  # ckeck for deadline since last call
        self.cursor_pos = 0
        self.votes = d['votes']

    async def save_to_db(self):
        await self.bot.db.polls.update_one({'server_id': str(self.server.id), 'short': str(self.short)},
                                           {'$set': self.to_dict()}, upsert=True)

    @staticmethod
    async def load_from_db(bot, server_id, short, ctx=None, ):
        # query = await bot.db.polls.find_one({'server_id': str(server_id), 'short': str(short)})
        query = await bot.db.polls.find_one({'server_id': str(server_id), 'short': str(short)})
        if query is not None:
            p = Poll(bot, ctx, load=True)
            await p.from_dict(query)
            return p
        else:
            return None

    async def add_field_custom(self, name, value, embed):
        ## this is used to estimate the width of text and add empty embed fields for a cleaner report
        ## cursor_pos is used to track if we are at the start of a new line in the report. Each line has max 2 slots for info.
        ## If the line is short, we can fit a second field, if it is too long, we get an automatic linebreak.
        ## If it is in between, we create an empty field to prevent the inline from looking ugly

        name = str(name)
        value = str(value)

        nwidth = afm.string_width_height(unidecode(name))
        vwidth = afm.string_width_height(unidecode(value))
        w = max(nwidth[0], vwidth[0])

        embed.add_field(name=name, value=value, inline=False if w > 12500 and self.cursor_pos % 2 == 1 else True)
        self.cursor_pos += 1

        ## create an empty field if we are at the second slot and the width of the first slot is between the critical values
        if self.cursor_pos % 2 == 1 and w > 11600 and w < 20000:
            embed.add_field(name='\u200b', value='\u200b', inline=True)
            self.cursor_pos += 1

        return embed

    async def generate_embed(self):
        self.cursor_pos = 0
        embed = discord.Embed(title='', colour=self.color)  # f'Status: {"Open" if self.is_open() else "Closed"}'
        embed.set_author(name=f' >> {self.short} ',
                         icon_url="http://mnadler.ch/img/donat-chart-32.png")
        embed.set_thumbnail(url="http://mnadler.ch/img/poll-topic-64.png")

        # ## adding fields with custom, length sensitive function
        embed = await self.add_field_custom(name='**Poll Question**', value=self.name, embed=embed)

        embed = await self.add_field_custom(name='**Roles**', value=', '.join(self.roles), embed=embed)
        if len(self.weights_roles) > 0:
            weights = []
            for r, n in zip(self.weights_roles, self.weights_numbers):
                weights.append(f'{r}: {n}')
            embed = await self.add_field_custom(name='**Weights**', value=', '.join(weights), embed=embed)

        embed = await self.add_field_custom(name='**Anonymous**', value=self.anonymous, embed=embed)

        # embed = await self.add_field_custom(name='**Multiple Choice**', value=self.multiple_choice, embed=embed)
        embed = await self.add_field_custom(name='**Deadline**', value=self.get_poll_status(), embed=embed)
        embed = await self.add_field_custom(name='**Author**', value=self.author.name, embed=embed)

        if self.reaction:
            if self.options_reaction_default:
                if self.is_open():
                    text = f'*Vote by adding reactions to the poll*. '
                    text += '*You can vote for multiple options.*' if self.multiple_choice \
                        else '*You have 1 vote, but can change it.*'
                else:
                    text = f'*Final Results of the {"multiple choice" if self.multiple_choice else "single choice"} Poll.*'

                vote_display = []
                for i, r in enumerate(self.options_reaction):
                    vote_display.append(f'{r} {self.count_votes(i)}')
                embed = await self.add_field_custom(name='**Score**', value='   '.join(vote_display), embed=embed)
            else:
                embed.add_field(name='\u200b', value='\u200b', inline=False)
                if self.is_open():
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
        else:
            embed = await self.add_field_custom(name='**Options**', value=', '.join(self.get_options()), embed=embed)

        embed.set_footer(text='bot is in development')

        return embed

    async def post_embed(self, ctx):
        msg = await self.bot.say(embed=await self.generate_embed())
        if self.reaction and self.is_open():
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
        else:
            return msg

    def get_options(self):
        if self.reaction:
            return self.options_reaction
        else:
            return self.options_traditional

    def get_deadline(self, string=False):
        deadline = float(self.time_created) + float(self.duration) * 60
        if string:
            if self.duration == 0:
                return 'No deadline'
            else:
                return datetime.datetime.utcfromtimestamp(deadline).strftime('%d-%b-%Y %H:%M') + ' UTC'
        else:
            return deadline

    def get_poll_status(self):
        if self.is_open():
            return self.get_deadline(string=True)
        else:
            return 'Poll is closed.'

    def count_votes(self, option, weighted=True):
        '''option: number from 0 to n'''
        if weighted:
            return sum([self.votes[c]['weight'] for c in [u for u in self.votes] if option in self.votes[c]['choices']])
        else:
            return sum([1 for c in [u for u in self.votes] if option in self.votes[c]['choices']])

    # async def has_voted(self, user_id):
    #     query = await self.bot.db.polls.find_one({'server_id': str(self.server.id), 'short': self.short})
    #     if query is None:
    #         return False
    #     else:
    #         votes = query['votes']
    #         if user_id in votes:
    #             return votes[user_id]
    #         else:
    #             return False

    async def vote(self, user, option, message):
        if not self.is_open():
            # refresh to show closed poll
            await self.bot.edit_message(message, embed=await self.generate_embed())
            await self.bot.clear_reactions(message)
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
        if not self.is_open():
            # refresh to show closed poll
            await self.bot.edit_message(message, embed=await self.generate_embed())
            await self.bot.clear_reactions(message)
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
