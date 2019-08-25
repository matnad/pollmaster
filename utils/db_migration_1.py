#  Script to enter votes in a separate table

import asyncio

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from essentials.settings import SETTINGS

mongo = AsyncIOMotorClient(SETTINGS.mongo_db)
db = mongo.pollmaster
print(db)


async def migrate():
    polls = db.polls.find()
    counter = 0
    async for p in polls:
        dict_list = []
        for user in p['votes']:
            weight = p['votes'][user]['weight']
            choices = p['votes'][user]['choices']
            if 'answers' in p['votes'][user].keys():
                answers = p['votes'][user]['answers']
            else:
                answers = None
            for i, c in enumerate(choices):
                d = {
                    'choice': c,
                    'poll_id': ObjectId(p['_id'],),
                    'user_id': user,
                    'weight': weight
                }
                if answers and c in p['survey_flags']:
                    d['answer'] = answers[p['survey_flags'].index(c)]
                else:
                    d['answer'] = ''

                dict_list.append(d)
        if dict_list:
            result = await db.votes.insert_many(dict_list)
            counter += len(result.inserted_ids)

    print(f"Done. Inserted {counter} docs.")

loop = asyncio.get_event_loop()
loop.run_until_complete(migrate())
