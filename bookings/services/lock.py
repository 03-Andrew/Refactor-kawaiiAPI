import uuid

from django_redis import get_redis_connection

ACQUIRE_LUA = """
local count_key = KEYS[1]
local holders_key = KEYS[2]
local holder_id = ARGV[1]
local max_available = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

if redis.call('SISMEMBER', holders_key, holder_id) == 1 then
    redis.call('EXPIRE', count_key, ttl)
    redis.call('EXPIRE', holders_key, ttl)
    return 1
end

local current = redis.call('GET', count_key)
current = current and tonumber(current) or 0

if current >= max_available then
    return 0
end

redis.call('INCR', count_key)
redis.call('SADD', holders_key, holder_id)
redis.call('EXPIRE', count_key, ttl)
redis.call('EXPIRE', holders_key, ttl)
return 1
"""

RELEASE_LUA = """
local count_key = KEYS[1]
local holders_key = KEYS[2]
local holder_id = ARGV[1]

if redis.call('SISMEMBER', holders_key, holder_id) == 0 then
    return 0
end

redis.call('SREM', holders_key, holder_id)
local current = redis.call('GET', count_key)
current = current and tonumber(current) or 1

if current <= 1 then
    redis.call('DEL', count_key, holders_key)
else
    redis.call('DECR', count_key)
end
return 1
"""


def _build_keys(room_type_id, check_in, check_out):
    base = f"booking_lock:{room_type_id}:{check_in}:{check_out}"
    return f"{base}:count", f"{base}:holders"


def _get_redis():
    return get_redis_connection("default")


def acquire_room_type_lock(room_type_id, check_in, check_out, max_available,
                      holder_id=None, ttl=600):
    """
    Try to acquire a room-type lock for a given date range.

    Returns (held: bool, holder_id: str).
    If holder_id is not provided, a new UUID is generated.
    Re-entry with same holder_id refreshes TTL and returns True.
    """
    if holder_id is None:
        holder_id = str(uuid.uuid4())

    count_key, holders_key = _build_keys(room_type_id, check_in, check_out)
    r = _get_redis()
    result = r.eval(ACQUIRE_LUA, 2, count_key, holders_key,
                    holder_id, max_available, ttl)
    return bool(result), holder_id


def release_room_type_lock(room_type_id, check_in, check_out, holder_id):
    """Release a previously acquired lock. Returns True if lock was held."""
    count_key, holders_key = _build_keys(room_type_id, check_in, check_out)
    r = _get_redis()
    result = r.eval(RELEASE_LUA, 2, count_key, holders_key, holder_id)
    return bool(result)


def get_locked_count(room_type_id, check_in, check_out):
    """Return current number of locks held for a room-type/date-range."""
    count_key, _ = _build_keys(room_type_id, check_in, check_out)
    r = _get_redis()
    val = r.get(count_key)
    return int(val) if val else 0


def holder_has_lock(room_type_id, check_in, check_out, holder_id):
    """Check whether a specific holder currently holds a lock."""
    _, holders_key = _build_keys(room_type_id, check_in, check_out)
    r = _get_redis()
    return r.sismember(holders_key, holder_id)


def bulk_acquire(room_requests, ttl=600):
    """
    Acquire locks for multiple room-type/date-range combinations.
    room_requests: list of dicts with room_type_id, check_in, check_out, max_available.
    Returns (all_held: bool, holder_id: str, failures: list).
    On partial failure, all previously acquired locks are released.
    """
    holder_id = str(uuid.uuid4())
    acquired = []

    for req in room_requests:
        held, _ = acquire_room_type_lock(
            req['room_type_id'], req['check_in'], req['check_out'],
            req['max_available'], holder_id=holder_id, ttl=ttl,
        )
        if held:
            acquired.append(req)
        else:
            for a in acquired:
                release_room_type_lock(
                    a['room_type_id'], a['check_in'], a['check_out'], holder_id,
                )
            return False, holder_id, [req]
    return True, holder_id, []


def bulk_release(room_requests, holder_id):
    """Release locks for all room-type/date-range combinations."""
    for req in room_requests:
        release_room_type_lock(
            req['room_type_id'], req['check_in'], req['check_out'], holder_id,
        )
