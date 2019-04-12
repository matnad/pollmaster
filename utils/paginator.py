import asyncio

import discord


async def embed_list_paginated(ctx, bot, pre, items, item_fct, base_embed, footer_prefix='', msg=None, start=0, per_page=10):
    embed = base_embed

    # generate list
    embed.title = f'{items.__len__()} entries'
    text = '\n'
    for i,item in enumerate(items[start:start+per_page]):
        j = i+start
        text += item_fct(j,item) + '\n'
    embed.description = text

    # footer text
    #footer_text = f'Type {pre}show <label> to show a poll. '
    footer_text = footer_prefix
    if start > 0:
        footer_text += f'React with ⏪ to show the last {per_page} entries. '
    if items.__len__() > start+per_page:
        footer_text += f'React with ⏩ to show the next {per_page} entries. '
    if footer_text.__len__() > 0:
        embed.set_footer(text=footer_text)

    # post / edit message
    if msg is not None:
        await msg.edit(embed=embed)
        if not isinstance(msg.channel, discord.abc.PrivateChannel):
            await msg.clear_reactions()
    else:
        msg = await ctx.send(embed=embed)

    # add reactions
    if start > 0:
        await msg.add_reaction('⏪')
    if items.__len__() > start+per_page:
        await msg.add_reaction('⏩')

    # wait for reactions (2 minutes)
    def check(reaction, user):
        return True if user != bot.user and str(reaction.emoji) in ['⏪', '⏩'] and reaction.message.id == msg.id else False
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=120, check=check)
    except asyncio.TimeoutError:
        pass
    else:
        # redirect on reaction
        if reaction is None:
            return
        elif reaction.emoji == '⏪' and start > 0:
            await embed_list_paginated(ctx, bot, pre, items, item_fct, base_embed, footer_prefix=footer_prefix, msg=msg, start=start-per_page, per_page=per_page)
        elif reaction.emoji == '⏩' and items.__len__() > start+per_page:
            await embed_list_paginated(ctx, bot, pre, items, item_fct, base_embed, footer_prefix=footer_prefix, msg=msg, start=start+per_page, per_page=per_page)