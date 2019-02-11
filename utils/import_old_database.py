import datetime
import json
import os

import pytz


async def import_old_database(bot, server):
    """try to import the old database"""
    try:
        clean_server = str(server).replace("/", "")
        while clean_server.startswith("."):
            clean_server = clean_server[1:]
        fn = 'backup/' + clean_server + '.json'
        with open(fn, 'r') as infile:
            polls = json.load(infile)
        for p in polls:
            #print(polls[p]['short'])
            wr = []
            wn = []
            for r, n in polls[p]['weights'].items():
                wr.append(r)
                try:
                    if n.is_integer():
                        n = int(n)
                except:
                    pass
                wn.append(n)
            created = datetime.datetime.strptime(polls[p]['datestarted'], '%d-%m-%Y %H:%M').replace(tzinfo=pytz.utc)
            if polls[p]['duration'] == 0:
                duration = 0
            else:
                duration = created + datetime.timedelta(hours=float(polls[p]['duration']))
            votes = {}
            for u,o in polls[p]['votes'].items():
                # get weight
                user = server.get_member(u)
                weight = 1
                if wr.__len__() > 0:
                    valid_weights = [wn[wr.index(r)] for r in
                                     list(set([n.name for n in user.roles]).intersection(set(wr)))]
                    if valid_weights.__len__() > 0:
                        #print(wr, wn)
                        weight = max(valid_weights)
                choices = []
                if o in polls[p]['options']:
                    choices = [polls[p]['options'].index(o)]
                votes[u] = {'weight': weight, 'choices': choices}

            new_format = {
                'server_id': str(server.id),
                'channel_id': str(polls[p]['channel']),
                'author': str(polls[p]['author']),
                'name': polls[p]['name'],
                'short': polls[p]['short'],
                'anonymous': polls[p]['anonymous'],
                'reaction': True,
                'multiple_choice': False,
                'options_reaction': polls[p]['options'],
                'reaction_default': False,
                'roles': polls[p]['roles'],
                'weights_roles': wr,
                'weights_numbers': wn,
                'duration': duration,
                'duration_tz': 'UTC',
                'time_created': created,
                'open': polls[p]['open'],
                'active': True,
                'activation': 0,
                'activation_tz': 'UTC',
                'votes': votes
            }
            await bot.db.polls.update_one({'server_id': str(server.id), 'short': polls[p]['short']},
                                               {'$set': new_format}, upsert=True)
        #os.remove(fn)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(e)