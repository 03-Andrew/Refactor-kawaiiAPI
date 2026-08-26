import uuid
from datetime import date, timedelta

from django_redis import get_redis_connection
from bookings.exceptions import RedisUnavailable, RoomTypeNotFoundError
import logging

logger = logging.getLogger(__name__)

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
local quantity = tonumber(ARGV[5]) or 1

-- KEYS layout: first num_dates are count keys, next num_dates are holders keys

-- Check if Holder locks exists and holds the exact key
local existing_qty = redis.call('HGET', KEYS[num_dates + 1], holder_id)
if existing_qty and tonumber(existing_qty) == quantity then
    for i = 1, num_dates * 2 do
        redis.call('EXPIRE', KEYS[i], ttl)
    end
    return 1
end

-- Check Capacity (current locked + requested quantity <= max_available)
for i = 1, num_dates do
    local current = redis.call('GET', KEYS[i])
    current = current and tonumber(current) or 0
    if (current + quantity) > max_available then
        return 0
    end
end

-- Acquire locks with quantity
for i = 1, num_dates do
    redis.call('INCRBY', KEYS[i], quantity)
    redis.call('HSET', KEYS[num_dates + i], holder_id, quantity)
    redis.call('EXPIRE', KEYS[i], ttl)
    redis.call('EXPIRE', KEYS[num_dates + i], ttl)
end
return 1
"""


RELEASE_LUA = """
local num_dates = tonumber(ARGV[1])
local holder_id = ARGV[2]

local qty = redis.call('HGET', KEYS[num_dates + 1], holder_id)
if not qty then
    return 0
end

qty = tonumber(qty)

-- Release all dates
for i = 1, num_dates do
    redis.call('HDEL', KEYS[num_dates + i], holder_id)
    local remaining_holders = redis.call('HLEN', KEYS[num_dates + i])
    
    if remaining_holders == 0 then
        redis.call('DEL', KEYS[i], KEYS[num_dates + i])
    local current = redis.call('GET', KEYS[i])
    else
        current = current and tonumber(current) or 0
        if current <= qty then
            redis.call('DEL', KEYS[i])
        else
            redis.call('DECRBY', KEYS[i], qty)
        end
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
    if redis.call('HEXISTS', KEYS[num_dates + i], holder_id) == 1 then
        return 1
    end
end
return 0
"""


def _get_redis():
    return get_redis_connection("default")


def acquire_room_type_lock(room_type_id, check_in, check_out, max_available, quantity,
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
                    num_dates, holder_id, max_available, ttl, quantity)
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


def bulk_get_locked_counts(room_requests):
    """Pipeline GET_LOCKED_COUNT_LUA calls. 1 Redis round-trip.

    room_requests: list of (room_type_id, check_in, check_out)
    Returns dict mapping (room_type_id, check_in, check_out) -> max_locked_count.
    """
    if not room_requests:
        return {}
    r = _get_redis()
    pipe = r.pipeline()
    for room_type_id, check_in, check_out in room_requests:
        count_keys, _ = _build_date_keys(room_type_id, check_in, check_out)
        pipe.eval(GET_LOCKED_COUNT_LUA, len(count_keys), *count_keys, len(count_keys))
    results = pipe.execute()
    return {
        req: (int(r) if r else 0)
        for req, r in zip(room_requests, results)
    }


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
            quantity=req.get('quantity',1)
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


def release_holder_locks(rooms, holder_id):
    """Release all Redis locks held by holder_id(s) for the given rooms."""
    if not holder_id or not rooms:
        return True
    
    seen = set()
    for room in rooms:
        rt_id = room.get('room_type_id') or room.get('room_type')
        check_in = str(room.get('check_in'))
        check_out = str(room.get('check_out'))

        if not rt_id or not check_in or not check_out:
            continue

        key = (rt_id, check_in, check_out)
        if key in seen:
            continue
        seen.add(key)

        try:
            release_room_type_lock(
                room_type_id=room['room_type_id'],
                check_in=room['check_in'],
                check_out=room['check_out'],
                holder_id=holder_id
            )
        except Exception as exc:
            logger.warning(f"Failed to release lock room_type={rt_id}, dates={check_in, check_out}, holder={holder_id}")

    return True