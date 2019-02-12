async def embed_list_paginated(bot, pre, items, item_fct, base_embed, footer_prefix='', msg=None, start=0, per_page=10):
    embed = base_embed

    # generate list
    embed.title = f'{items.__len__()} entries'
    text = '\n'
    for item in items[start:start+per_page]:
        text += item_fct(item) + '\n'
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
        await bot.edit_message(msg, embed=embed)
        await bot.clear_reactions(msg)
    else:
        msg = await bot.say(embed=embed)

    # add reactions
    if start > 0:
        await bot.add_reaction(msg, '⏪')
    if items.__len__() > start+per_page:
        await bot.add_reaction(msg, '⏩')

    # wait for reactions (2 minutes)
    def check(reaction, user):
        return reaction.emoji if user != bot.user else False
    res = await bot.wait_for_reaction(emoji=['⏪', '⏩'], message=msg, timeout=120, check=check)

    # redirect on reaction
    if res is None:
        return
    elif res.reaction.emoji == '⏪' and start > 0:
        await embed_list_paginated(bot, pre, items, item_fct, base_embed, footer_prefix=footer_prefix, msg=msg, start=start-per_page, per_page=per_page)
    elif res.reaction.emoji == '⏩' and items.__len__() > start+per_page:
        await embed_list_paginated(bot, pre, items, item_fct, base_embed, footer_prefix=footer_prefix, msg=msg, start=start+per_page, per_page=per_page)