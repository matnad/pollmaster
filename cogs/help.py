import asyncio
import logging

import discord
from discord.ext import commands

from essentials.multi_server import get_server_pre, ask_for_server
from essentials.settings import SETTINGS


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.pages = ['🏠', '🆕', '🔍', '🕹', '🛠', '💖']

    async def embed_list_reaction_handler(self, ctx, page, pre, msg=None):
        embed = self.get_help_embed(page, pre)

        if msg is None:
            msg = await ctx.send(embed=embed)
            # add reactions
            for emoji in self.pages:
                await msg.add_reaction(emoji)
        else:
            await msg.edit(embed=embed)

        # wait for reactions (3 minutes)
        def check(rct, usr):
            return True if usr != self.bot.user and str(rct.emoji) in self.pages and rct.message.id == msg.id else False

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=180, check=check)
        except asyncio.TimeoutError:
            await msg.delete()
            return None
        else:
            if isinstance(reaction.message.channel, discord.TextChannel):
                await reaction.message.remove_reaction(reaction.emoji, user)
            return reaction



    def get_help_embed(self, page, pre):

        title = f' Pollmaster Help - React with an emoji to learn more about a topic!'
        embed = discord.Embed(title='', description='', colour=SETTINGS.color)
        embed.set_author(name=title, icon_url=SETTINGS.author_icon)
        embed.set_footer(text='Use reactions to navigate the help. This message will self-destruct in 3 minutes.')

        if page == '🏠':
            ## POLL CREATION SHORT
            embed.add_field(name='🆕 Making New Polls',
                            value=f'`{pre}quick` | `{pre}new` | `{pre}advanced` | `{pre}prepare` | `{pre}cmd <args>`', inline=False)
            # embed.add_field(name='Commands', value=f'`{pre}quick` | `{pre}new` | `{pre}prepared`', inline=False)
            # embed.add_field(name='Arguments', value=f'Arguments: `<poll question>` (optional)', inline=False)
            # embed.add_field(name='Examples', value=f'Examples: `{pre}new` | `{pre}quick What is the greenest color?`',
            #                 inline=False)

            ## POLL CONTROLS
            embed.add_field(name='🔍 Show Polls',
                            value=f'`{pre}show (label)`', inline=False)
            # embed.add_field(name='Command', value=f'`{pre}show (label)`', inline=False)
            # embed.add_field(name='Arguments', value=f'Arguments: `open` (default) | `closed` | `prepared` | '
            #                                         f'`<poll_label>` (optional)', inline=False)
            # embed.add_field(name='Examples', value=f'Examples: `{pre}show` | `{pre}show closed` | `{pre}show mascot`',
            #                 inline=False)

            ## POLL CONTROLS
            embed.add_field(name='🕹 Poll Controls',
                            value=f'`{pre}close` | `{pre}export` | `{pre}delete` | `{pre}activate` ', inline=False)
            # embed.add_field(name='Commands', value=f'`{pre}close` | `{pre}export` | `{pre}delete` | `{pre}activate` ',
            #                 inline=False)
            # embed.add_field(name='Arguments', value=f'Arguments: <poll_label> (required)', inline=False)
            # embed.add_field(name='Examples', value=f'Examples: `{pre}close mascot` | `{pre}export proposal`',
            #                 inline=False)

            ## POLL CONTROLS
            embed.add_field(name='🛠 Configuration',
                            value=f'`{pre}userrole (role)` | `{pre}adminrole (role)` | `{pre}prefix <new_prefix>` ',
                            inline=False
                            )
            # embed.add_field(name='Commands',
            #                 value=f'`{pre}userrole <role>` | `{pre}adminrole <role>` | `{pre}prefix <new_prefix>` ',
            #                 inline=False)

            ## ABOUT
            embed.add_field(name='💖 About Pollmaster',
                            value='More infos about Pollmaster, the developer, where to go for further help and how you can support us.',
                            inline=False)

        elif page == '🆕':
            embed.add_field(name='🆕 Making New Polls',
                            value='There are three ways to create a new poll. For all three commands you can either just '
                                  'type the command or type the command followed by the question to skip that first step.'
                                  'Your Members need the <admin> or <user> role to use these commands. More in 🛠 Configuration.',
                            inline=False)
            embed.add_field(name=f'🔹 **Quick Poll:** `{pre}quick <poll question>` (optional)',
                            value='If you just need a quick poll, this is the way to go. All you have to specify is the '
                                  'question and your answers; the rest will be set to default values.',
                            inline=False)
            embed.add_field(name=f'🔹 **All Features:** `{pre}new <poll question>` (optional)',
                            value='This command gives you full control over your poll. A step by step wizard will guide '
                                  'you through the process and you can specify options such as Multiple Choice, '
                                  'Anonymous Voting, Role Restriction, Role Weights and Deadline.',
                            inline=False)
            embed.add_field(name=f'🔹 **Prepare and Schedule:** `{pre}prepare <poll question>` (optional)',
                            value=f'Similar to `{pre}new`, this gives you all the options. But additionally, the poll will '
                                  'be set to \'inactive\'. You can specify if the poll should activate at a certain time '
                                  f'and/or if you would like to manually `{pre}activate` it. '
                                  'Perfect if you are preparing for a team meeting!',
                            inline=False)
            embed.add_field(name=f'🔹 **-Advanced- Commandline:** `{pre}cmd <args>`',
                            value=f'For the full syntax type `{pre}cmd help`\n'
                                  f'Similar to version 1 of the bot, with this command you can create a poll in one message. '
                                  f'Pass all the options you need via command line arguments, the rest will be set to '
                                  f'default values. The wizard will step in for invalid arguments.\n'
                                  f'Example: `{pre}cmd -q "Which colors?" -l colors -o "green, blue, red" -mc -a`',
                            inline=False)

        elif page == '🔍':
            embed.add_field(name='🔍 Show Polls',
                            value='All users can display and list polls, with the exception of prepared polls. '
                                  'Voting is done simply by using the reactions below the poll.',
                            inline=False)
            embed.add_field(name=f'🔹 **Show a Poll:** `{pre}show <poll_label>`',
                            value='This command will refresh and display a poll. The votes in the message will always '
                                  'be up to date and accurate. The number of reactions can be different for a number '
                                  'of reasons and you can safely disregard them.',
                            inline=False)
            embed.add_field(name=f'🔹 **List Polls:** `{pre}show <> | open | closed | prepared`',
                            value=f'If you just type `{pre}show` without an argument it will default to `{pre}show open`.'
                                  'These commands will print a list of open, closed or prepared polls that exist on '
                                  'the server. The first word in bold is the label of the poll and after the colon, '
                                  'you can read the question. These lists are paginated and you can use the arrow '
                                  'reactions to navigate larger lists.',
                            inline=False)
        elif page == '🕹':
            embed.add_field(name='🕹 Poll Controls',
                            value='All these commands can only be used by an <admin> or by the author of the poll. '
                                  'Go to 🛠 Configuration for more info on the permissions.',
                            inline=False)
            embed.add_field(name=f'🔹 **Close** `{pre}close <poll_label>`',
                            value='Polls will close automatically when their deadline is reached. But you can always '
                                  'close them manually by using this command. A closed poll will lock in the votes so '
                                  'users can no longer change, add or remove votes. Once closed, you can export a poll.',
                            inline=False)
            embed.add_field(name=f'🔹 **Delete** `{pre}delete <poll_label>`',
                            value='This will *permanently and irreversibly* delete a poll from the database. '
                                  'Once done, the label is freed up and can be assigned again.',
                            inline=False)
            embed.add_field(name=f'🔹 **Export** `{pre}export <poll_label>`',
                            value='You can use this command or react with 📎 to a closed poll to generate a report. '
                                  'The report will then be sent to you in discord via the bot. This utf8-textfile '
                                  '(make sure to open it in an utf8-ready editor) will contain all the infos about the '
                                  'poll, including a detailed list of participants and their votes (just a list of names '
                                  'for anonymous polls).',
                            inline=False)
            embed.add_field(name=f'🔹 **Activate** `{pre}activate <poll_label>`',
                            value=f'To see how you can prepare inactive polls read the `{pre}prepare` command under Making '
                                  'New Polls. This command is used to manually activate a prepared poll.',
                            inline=False)

        elif page == '🛠':
            embed.add_field(name='🛠 Configuration',
                            value='To run any of these commands you need the **\"Manage Server\"** permisson.',
                            inline=False)
            embed.add_field(name=f'🔹 **Poll Admins** `{pre}adminrole <role name> (optional)`',
                            value='This gives the rights to create polls and to control ALL polls on the server. '
                                  f'To see the current role for poll admin, run the command without an argument: `{pre}adminrole`\n'
                                  'If you want to change the admin role to any other role, use the name of the new role '
                                  f'as the argument: `{pre}adminrole moderators`',
                            inline=False)
            embed.add_field(name=f'🔹 **Poll Users** `{pre}userrole <role name> (optional)`',
                            value='Everything here is identical to the admin role, except that Poll Users can only '
                                  'control the polls which were created by themselves.',
                            inline=False)
            embed.add_field(name=f'🔹 **Change Prefix** `{pre}prefix <new_prefix>`',
                            value='This will change the bot prefix for your server. If you want to use a trailing '
                                  'whitespace, use "\w" instead of " " (discord deletes trailing whitespaces).',
                            inline=False)

        elif page == '💖':
            embed.add_field(name='💖 Pollmaster 💖',
                            value='If you enjoy the bot, you can show your appreciation by giving him an upvote on Discordbots.',
                            inline=False)
            embed.add_field(name='🔹 **Developer**',
                            value='Pollmaster is developed by Newti#0654',
                            inline=False)
            embed.add_field(name='🔹 **Support**',
                            value='You can support Pollmaster by sending an upvote his way or by clicking the donate link '
                                  'on the discordbots page:\n https://discordbots.org/bot/444514223075360800',
                            inline=False)
            embed.add_field(name='🔹 **Support Server**',
                            value='If you need help with pollmaster, want to try him out or would like to give feedback '
                                  'to the developer, feel free to join the support server: https://discord.gg/Vgk8Nve',
                            inline=False)
            embed.add_field(name='🔹 **Github**',
                            value='The full python source code is on my Github: https://github.com/matnad/pollmaster',
                            inline=False)
            embed.add_field(name='**Thanks for using Pollmaster!** 💗', value='Newti', inline=False)
        else:
            return None

        return embed

    @commands.command()
    async def help(self, ctx, *, topic=None):
        server = await ask_for_server(self.bot, ctx.message)
        pre = await get_server_pre(self.bot, server)
        rct = 1
        while rct is not None:
            if rct == 1:
                page = '🏠'
                msg = None
            else:
                page = rct.emoji
                msg = rct.message
            rct = await self.embed_list_reaction_handler(ctx, page, pre, msg)
            # print(res.user, res.reaction, res.reaction.emoji)
        # cleanup
        await ctx.message.delete()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.content.startswith("@mention "):
            channel = message.channel
            if not isinstance(channel, discord.TextChannel):
                await channel.send("@mention can only be used in a server text channel.")
                return

            guild = message.guild
            if not guild:
                await channel.send("Could not determine your server.")
                return

            tag = message.content.split()[1].lower()
            if tag == "prefix":
                pre = await get_server_pre(self.bot, guild)
                # await channel.send(f'The prefix for this server/channel is: \n {pre} \n To change it type: \n'
                #                    f'{pre}prefix <new_prefix>')
                await channel.send(pre)

        elif message.content == "@debug":
            channel = message.channel
            if not isinstance(channel, discord.TextChannel):
                await channel.send("@debug can only be used in a server text channel.")
                return

            guild = message.guild
            if not guild:
                await channel.send("Could not determine your server.")
                return

            status_msg = ''

            permissions = channel.permissions_for(guild.me)
            if not permissions.send_messages:
                await message.author.send(f'I don\'t have permission to send text messages in channel {channel} '
                                          f'on server {guild}')
                return

            status_msg += f' ✅ Sending messages\n'

            await channel.send(status_msg)

def setup(bot):
    global logger
    logger = logging.getLogger('bot')
    bot.add_cog(Help(bot))
