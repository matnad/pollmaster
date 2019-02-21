import asyncio


class UniqueQueue(asyncio.Queue):

    async def put_unique_id(self, item):
        if not item.get('id'):
            return

        if item.get('id') not in [v.get('id') for v in self._queue]:
            await self.put(item)