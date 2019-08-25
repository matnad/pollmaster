import logging
import discord

logger = logging.getLogger('discord')


class MessageCache:
    def __init__(self, _bot):
        self._bot = _bot
        self._cache_dict = {}

    def put(self, key, value: discord.Message):
        self._cache_dict[key] = value
        if self._cache_dict.__len__() % 5 == 0:
            logger.info("cache size: " + str(self._cache_dict.__len__()))

    def get(self, key):
        # Try to find it in this cache, then see if it is cached in the bots own message cache
        message = self._cache_dict.get(key, None)
        if message == None:
            for m in self._bot._connection._messages:
                if m.id == key:
                    return m
        return message

    def clear(self):
        self._cache_dict = {}