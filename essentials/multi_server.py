import asyncio

import discord

from essentials.settings import SETTINGS


async def get_pre(bot, message):
    '''Gets the prefix for a message.'''
    if isinstance(message.channel, discord.abc.PrivateChannel):
        shared_server_list = await get_servers(bot, message)
        if shared_server_list.__len__() == 0:
            return 'pm!'
        elif shared_server_list.__len__() == 1:
            return await get_server_pre(bot, shared_server_list[0])
        else:
            # return a tuple of all prefixes.. this will check them all!
            return tuple([await get_server_pre(bot, s) for s in shared_server_list])
    else:
        return await get_server_pre(bot, message.guild)


async def get_server_pre(bot, server):
    """Gets the prefix for a server."""
    try:
        # result = await bot.db.config.find_one({'_id': str(server.id)})
        result = bot.pre.get(str(server.id), 'pm!')
    except AttributeError:
        return 'pm!'
    if not result:
        return 'pm!'
    return result


async def get_servers(bot, message, short=None):
    """Get best guess of relevant shared servers"""
    if message.guild is None:
        list_of_shared_servers = []
        for s in bot.guilds:
            if message.author.id in [m.id for m in s.members]:
                list_of_shared_servers.append(s)
        if short is not None:
            query = bot.db.polls.find({'short': short})
            if query is not None:
                server_ids_with_short = [poll['server_id'] async for poll in query]
                servers_with_short = [bot.get_guild(x) for x in server_ids_with_short]
                shared_servers_with_short = list(set(servers_with_short).intersection(set(list_of_shared_servers)))
                if shared_servers_with_short.__len__() >= 1:
                    return shared_servers_with_short

        # do this if no shared server with short is found
        if list_of_shared_servers.__len__() == 0:
            return []
        else:
            return list_of_shared_servers
    else:
        return [message.guild]


async def ask_for_server(bot, message, short=None):
    server_list = await get_servers(bot, message, short)
    if server_list.__len__() == 0:
        if short == None:
            await bot.say(
                'I could not find a common server where we can see eachother. If you think this is an error, '
                'please contact the developer.')
        else:
            await bot.say(f'I could not find a server where the poll {short} exists that we both can see.')
        return None
    elif server_list.__len__() == 1:
        return server_list[0]
    else:
        text = 'I\'m not sure which server you are referring to. Please tell me by typing the corresponding number.\n'
        i = 1
        for name in [s.name for s in server_list]:
            text += f'\n**{i}** - {name}'
            i += 1
        embed = discord.Embed(title="Select your server", description=text, color=SETTINGS.color)
        server_msg = await message.channel.send(embed=embed)

        valid_reply = False
        nr = 1
        while valid_reply == False:
            def check(m):
                return message.author == m.author
            try:
                reply = await bot.wait_for('message', timeout=120, check=check)
            except asyncio.TimeoutError:
                pass
            else:
                if reply and reply.content:
                    if reply.content.startswith(await get_pre(bot, message)):
                        # await bot.say('You can\'t use bot commands while I am waiting for an answer.'
                        #               '\n I\'ll stop waiting and execute your command.')
                        return False
                    if str(reply.content).isdigit():
                        nr = int(reply.content)
                        if 0 < nr <= server_list.__len__():
                            valid_reply = True

        return server_list[nr - 1]


async def ask_for_channel(ctx, bot, server, message):
    # if performed from a channel, return that channel
    if not isinstance(message.channel, discord.abc.PrivateChannel):
        return message.channel

    # build channel list that the user is allowed to send messages to
    user = message.author
    member = server.get_member(user.id)
    channel_list = [c for c in server.channels if isinstance(c, discord.TextChannel) and c.permissions_for(member).send_messages]

    # if exactly 1 channel, return it
    if channel_list.__len__() == 1:
        return channel_list[0]

    # if no channels, display error
    if channel_list.__len__() == 0:
        embed = discord.Embed(title="Select a channel", description='No text channels found on this server. Make sure '
                                                                    'I can see them.', color=SETTINGS.color)
        await ctx.send(embed=embed)
        return False

    # otherwise ask for a channel
    i = 1
    text = 'Polls are bound to a specific channel on a server. Please select the channel for this poll by typing the ' \
           'corresponding number.\n '
    for name in [c.name for c in channel_list]:
        to_add = f'\n**{i}** - {name}'

        # check if length doesn't exceed allowed maximum or split it into multiple messages
        if text.__len__() + to_add.__len__() > 2048:
            embed = discord.Embed(title="Select a channel", description=text, color=SETTINGS.color)
            await ctx.send(embed=embed)
            text = 'Polls are bound to a specific channel on a server. Please select the channel for this poll by ' \
                   'typing the corresponding number.\n '
        else:
            text += to_add
            i += 1

    embed = discord.Embed(title="Select a channel", description=text, color=SETTINGS.color)
    await ctx.send(embed=embed)

    valid_reply = False
    nr = 1
    while not valid_reply:
        def check(m):
            return message.author.id == m.author.id
        try:
            reply = await bot.wait_for('message', timeout=120, check=check)
        except asyncio.TimeoutError:
            pass
        else:
            if reply and reply.content:
                if reply.content.startswith(await get_pre(bot, message)):
                    # await bot.say('You can\'t use bot commands while I am waiting for an answer.'
                    #               '\n I\'ll stop waiting and execute your command.')
                    return False
                if str(reply.content).isdigit():
                    nr = int(reply.content)
                    if 0 < nr <= channel_list.__len__():
                        valid_reply = True
    return channel_list[nr - 1]
