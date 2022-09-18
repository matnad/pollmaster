import logging
from collections import defaultdict

import discord

logger = logging.getLogger('discord')


class MemberCache:
    def __init__(self):
        self._cache_dict = defaultdict(dict)

    async def add(self, guild: discord.Guild, member_id: int) -> discord.Member:
        try:
            member = await guild.fetch_member(member_id)
            self._cache_dict[guild.id][member_id] = member
            if len(self._cache_dict[guild.id]) % 1 == 0:
                logger.info("member cache size: " + str(len(self._cache_dict[guild.id])))
            return member
        except:
            pass

    async def get(self, guild: discord.Guild, member_id: int) -> discord.Member:
        member = self._cache_dict[guild.id].get(member_id, None)
        if not member:
            member = await self.add(guild, member_id)
        return member

    def clear(self):
        self._cache_dict = defaultdict(dict)
