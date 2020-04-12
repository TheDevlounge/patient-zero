import json
from collections import namedtuple
from types import SimpleNamespace

from db.ctx import get_redis


HKEY = 'PZ:Users'


def set_user(user):
    r = get_redis()
    r.hset(HKEY, str(user.uid), json.dumps(vars(user)))


def get_user(user_id, uname=None):
    ''' Get player object or create one '''
    r = get_redis()
    json_string = r.hget(HKEY, str(user_id))

    if json_string is None:
        # create new user on the spot
        user = SimpleNamespace(
            uid = user_id,
            name = uname,
            xp = 0,
            lvl = 0,
            elo = 1200,
            division = 1,
            infected_me = 0,
            infected = 0,
        )
        set_user(user)
    else:
        user = SimpleNamespace(**json.loads(json_string))

        if user.name != uname:
            user.name = uname
            set_user(user)


    return user
