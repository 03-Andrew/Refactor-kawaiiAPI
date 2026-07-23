import uuid
from datetime import date, timedelta

from django_redis import get_redis_connection


def _date_range(check_in, check_out):
    """Generate list of ISO date strings from check_in (inclusive) to check_out (exclusive)."""
    if isinstance(check_in, str):
        check_in = date.fromisoformat(check_in)
    if isinstance(check_out, str):
        check_out = date.fromisoformat(check_out)
    dates = []
    current = check_in
    while current < check_out:
        dates.append(current.isoformat())
        current = current + timedelta(days=1)
    return dates


def _build_date_keys(room_type_id, check_in, check_out):
    """Build per-date count and holders keys for the date range."""
    dates = _date_range(check_in, check_out)
    count_keys = [f"booking_lock:{room_type_id}:{d}:count" for d in dates]
    holders_keys = [f"booking_lock:{room_type_id}:{d}:holders" for d in dates]
    return count_keys, holders_keys


ACQUIRE_LUA = """
local num_dates = tonumber(ARGV[1])
local holder_id = ARGV[2]
local max_available = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

-- KEYS layout: first num_dates are count keys, next num_dates are holders keys

-- Re-entry: holder already owns these dates, refresh TTL
if redis.call('SISMEMBER', KEYS[num_dates + 1], holder_id) == 1 then
    for i = 1, num_dates * 2 do
        redis.call('EXPIRE', KEYS[i], ttl)
    end
    return 1
end

-- Check capacity: if any date in range is at max, fail
for i = 1, num_dates do
    local current = redis.call('GET', KEYS[i])
    current = current and tonumber(current) or 0
    if current >= max_available then
        return 0
    end
end

-- Acquire all dates
for i = 1, num_dates do
    redis.call('INCR', KEYS[i])
    redis.call('SADD', KEYS[num_dates + i], holder_id)
    redis.call('EXPIRE', KEYS[i], ttl)
    redis.call('EXPIRE', KEYS[num_dates + i], ttl)
end
return 1
"""


RELEASE_LUA = """
local num_dates = tonumber(ARGV[1])
local holder_id = ARGV[2]

-- KEYS layout: first num_dates are count keys, next num_dates are holders keys

if redis.call('SISMEMBER', KEYS[num_dates + 1], holder_id) == 0 then
    return 0
end

-- Release all dates
for i = 1, num_dates do
    redis.call('SREM', KEYS[num_dates + i], holder_id)
    local current = redis.call('GET', KEYS[i])
    current = current and tonumber(current) or 1
    if current <= 1 then
        redis.call('DEL', KEYS[i], KEYS[num_dates + i])
    else
        redis.call('DECR', KEYS[i])
    end
end
return 1
"""


GET_LOCKED_COUNT_LUA = """
local num_dates = tonumber(ARGV[1])
local max_count = 0
for i = 1, num_dates do
    local val = redis.call('GET', KEYS[i])
    if val then
        local n = tonumber(val)
        if n and n > max_count then
            max_count = n
        end
    end
end
return max_count
"""


HOLDER_HAS_LOCK_LUA = """
local num_dates = tonumber(ARGV[1])
local holder_id = ARGV[2]
-- KEYS layout: first num_dates are count keys, next num_dates are holders keys
for i = 1, num_dates do
    if redis.call('SISMEMBER', KEYS[num_dates + i], holder_id) == 1 then
        return 1
    end
end
return 0
"""


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

    count_keys, holders_keys = _build_date_keys(room_type_id, check_in, check_out)
    num_dates = len(count_keys)
    all_keys = count_keys + holders_keys
    r = _get_redis()
    result = r.eval(ACQUIRE_LUA, len(all_keys), *all_keys,
                    num_dates, holder_id, max_available, ttl)
    return bool(result), holder_id


def release_room_type_lock(room_type_id, check_in, check_out, holder_id):
    """Release a previously acquired lock. Returns True if lock was held."""
    count_keys, holders_keys = _build_date_keys(room_type_id, check_in, check_out)
    num_dates = len(count_keys)
    all_keys = count_keys + holders_keys
    r = _get_redis()
    result = r.eval(RELEASE_LUA, len(all_keys), *all_keys,
                    num_dates, holder_id)
    return bool(result)


def get_locked_count(room_type_id, check_in, check_out):
    """Return maximum locked count across all dates in the range."""
    count_keys, _ = _build_date_keys(room_type_id, check_in, check_out)
    num_dates = len(count_keys)
    r = _get_redis()
    result = r.eval(GET_LOCKED_COUNT_LUA, num_dates, *count_keys, num_dates)
    return int(result) if result else 0


def holder_has_lock(room_type_id, check_in, check_out, holder_id):
    """Check whether a specific holder currently holds a lock for any date in the range."""
    count_keys, holders_keys = _build_date_keys(room_type_id, check_in, check_out)
    num_dates = len(count_keys)
    all_keys = count_keys + holders_keys
    r = _get_redis()
    result = r.eval(HOLDER_HAS_LOCK_LUA, len(all_keys), *all_keys,
                    num_dates, holder_id)
    return bool(result)


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
