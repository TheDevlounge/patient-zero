import redis

redis_session = None

def get_redis():
    return redis_session

def init(app, connstr):
    global redis_session

    db, addr = connstr.split("@")
    host, port = addr.split(":")

    redis_session = redis.StrictRedis(db=db, host=host, port=int(port))

