"""Shared availability helpers — single source for room capacity + overlap logic."""
from datetime import date
from collections import Counter
from django.db.models import Count, Q

from bookings.exceptions import RoomTypeNotFoundError, RoomUnavailableError, RedisUnavailable
from bookings.models import Booking, BookingStatus, Room, RoomStatus, RoomType
from bookings.services.lock import (
    get_locked_count, holder_has_lock, bulk_get_locked_counts, acquire_room_type_lock,
    bulk_acquire
)

def get_room_type_capacities(room_type_ids):
    """Return {id: {name, total, maintenance}} — 1 annotated query."""
    qs = RoomType.objects.filter(id__in=room_type_ids).annotate(
        total=Count('room'),
        maintenance=Count('room', filter=Q(room__status=RoomStatus.MAINTENANCE)),
    )
    return {
        rt.id: {'name': rt.name, 'total': rt.total, 'maintenance': rt.maintenance}
        for rt in qs
    }


def get_overlap_counts(room_specs_by_type, exclude_booking_id=None):
    """Return Counter of (room_type_id, check_in_str, check_out_str) -> overlap count.

    room_specs_by_type: {room_type_id: [{'check_in': ..., 'check_out': ...}, ...]}
    1 query per unique room_type.
    """
    counts = Counter()
    for room_type_id, type_rooms in room_specs_by_type.items():
        date_filter = Q()
        for r in type_rooms:
            date_filter |= Q(
                check_in__lt=r['check_out'],
                check_out__gt=r['check_in'],
            )
        qs = Booking.objects.filter(
            room_type_id=room_type_id,
            status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        ).filter(date_filter)
        if exclude_booking_id is not None:
            qs = qs.exclude(id=exclude_booking_id)
        overlapping = [
            (ci.isoformat(), co.isoformat())
            for ci, co in qs.values_list('check_in', 'check_out')
        ]
        for r in type_rooms:
            check_in = str(r['check_in'])
            check_out = str(r['check_out'])
            count = sum(1 for ci, co in overlapping if ci < check_out and co > check_in)
            counts[(room_type_id, check_in, check_out)] = count
    return counts

def lock_room_types(rooms):
    """Acquire DB row-level locks on RoomType rows to serialise concurrent writes."""
    room_type_ids = {room['room_type'] for room in rooms}
    list(RoomType.objects.select_for_update().filter(id__in=room_type_ids))

def validate_rooms_availability(*, rooms, holder_id=None, exclude_booking_id=None):
    """Assert availability for a list of requested rooms.

    Raises:
        RoomTypeNotFoundError: If any requested room type ID does not exist.
        RoomUnavailableError: If any requested room is fully booked or locked.
    """
    errors = []
    room_type_ids = {room['room_type'] for room in rooms}

    capacities = get_room_type_capacities(room_type_ids)
    missing = room_type_ids - set(capacities)
    if missing:
        raise RoomTypeNotFoundError(f"Room type IDs not found: {list(missing)}")

    rooms_by_type: dict[int, list] = {}
    for room in rooms:
        if room['room_type'] in capacities:
            rooms_by_type.setdefault(room['room_type'], []).append(room)

    booking_counts = get_overlap_counts(rooms_by_type, exclude_booking_id=exclude_booking_id)

    # Normalize holder_ids (can be str, list, or per-room)
    all_holder_ids = set()
    if isinstance(holder_id, (list, tuple, set)):
        all_holder_ids.update(h for h in holder_id if h)
    elif isinstance(holder_id, str) and holder_id:
        all_holder_ids.add(holder_id)

    for room_data in rooms:
        rt_id = room_data['room_type']
        if rt_id not in capacities:
            continue

        cap = capacities[rt_id]
        check_in = str(room_data['check_in'])
        check_out = str(room_data['check_out'])
        key = (rt_id, check_in, check_out)
        booked = booking_counts.get(key, 0)

        db_available = cap['total'] - cap['maintenance'] - booked
        try:
            locked = get_locked_count(rt_id, check_in, check_out)
        except Exception:
            locked = 0

        current_holders = set(all_holder_ids)
        if isinstance(room_data, dict) and room_data.get('holder_id'):
            current_holders.add(room_data['holder_id'])

        is_held = any(
            holder_has_lock(rt_id, check_in, check_out, hid)
            for hid in current_holders
        ) if current_holders else False

        if is_held:
            available = db_available
        else:
            available = db_available - locked

        if available <= 0:
            errors.append(
                f"'{cap['name']}' is fully booked for {check_in} to {check_out}"
            )

    if errors:
        raise RoomUnavailableError(details=errors)


def get_room_type_available(room_type_id, check_in, check_out,
                            exclude_booking_id=None, holder_id=None):
    """Check single room type + date range. Returns (available: bool, detail: dict).

    detail keys: name, total, maintenance, booked, locked, db_available, available.
    2 queries (1 annotated RoomType + 1 booking count).
    """
    all_capacities = get_room_type_capacities([room_type_id])
    if room_type_id not in all_capacities:
        return False, {'error': f'Room type {room_type_id} not found'}

    room_capacity = all_capacities[room_type_id]
    booked = Booking.objects.filter(
        room_type_id=room_type_id,
        status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        check_in__lt=check_out,
        check_out__gt=check_in,
    )
    if exclude_booking_id is not None:
        booked = booked.exclude(id=exclude_booking_id)
    booked = booked.count()

    db_available = room_capacity['total'] - room_capacity['maintenance'] - booked

    try:
        locked = get_locked_count(room_type_id, str(check_in), str(check_out))
    except Exception:
        locked = 0

    if holder_id and holder_has_lock(room_type_id, str(check_in), str(check_out), holder_id):
        available_count = db_available
    else:
        available_count = db_available - locked

    return available_count > 0, {
        'name': room_capacity['name'],
        'total': room_capacity['total'],
        'maintenance': room_capacity['maintenance'],
        'booked': booked,
        'locked': locked,
        'db_available': db_available,
        'available': available_count,
    }


def find_available_room(room_type, check_in, check_out):
    """Return first available Room of given type for the date range, or None."""
    booked_rooms = Booking.objects.filter(
        room_type=room_type,
        status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).values_list('room', flat=True)

    return Room.objects.filter(
        type=room_type,
        status=RoomStatus.AVAILABLE,
    ).exclude(id__in=booked_rooms).first()

def get_room_type_basic_info():
    return  RoomType.objects.prefetch_related("inclusions").all()

def get_room_types_availability(*, check_in=None, check_out=None, room_type=None):
    queryset = RoomType.objects.all()

    if room_type:
        queryset = queryset.filter(name__icontains=room_type)

    annotations = {
        'total_count': Count('room', distinct=True),
        'maintenance_count': Count('room', distinct=True, filter=Q(room__status=RoomStatus.MAINTENANCE)),
    }

    has_dates = bool(check_in and check_out)
    if has_dates:                                                                                                                            
        try:                                                                                                                                 
            check_in_date = date.fromisoformat(check_in)                                                                                     
            check_out_date = date.fromisoformat(check_out)                                                                                   
            annotations['booked_count'] = Count(                                                                                             
                'bookings',                                                                                                                  
                filter=Q(bookings__check_in__lt=check_out_date)                                                                              
                & Q(bookings__check_out__gt=check_in_date)                                                                                   
                & Q(bookings__status__in=[BookingStatus.APPROVED, BookingStatus.PENDING]),                                                   
                distinct=True,                                                                                                               
            )                                                                                                                                
        except ValueError:                                                                                                                   
            return []                                                                                                                        
    else:                                                                                                                                    
        annotations['booked_count'] = Count('bookings', distinct=True)     

    queryset = queryset.annotate(**annotations)

    locked_counts = {}
    if has_dates:
        try:
            lock_requests = [(rt.id, check_in, check_out) for rt in queryset]
            locked_counts = bulk_get_locked_counts(lock_requests)
        except Exception:
            pass

    results = []

    for rt in queryset:
        locked = locked_counts.get((rt.id, check_in, check_out),0) if has_dates else 0
        available = rt.total_count - rt.booked_count - rt.maintenance_count - locked

        results.append({
            'room_type': rt,
            'total_rooms': rt.total_count,
            'booked_rooms': rt.booked_count,
            'locked_rooms': locked,
            'available_rooms': max(0, available),
            'maintenance_rooms': rt.maintenance_count
        })

    return results


def lock_room_type(*, room_type_id, check_out, check_in, holder_id, ttl=600):
    is_available, detail = get_room_type_available(room_type_id, check_in, check_out)
    if detail.get('error'):
        raise RoomTypeNotFoundError(f"Room type {room_type_id} not found")

    db_available = detail['db_available']
    try:
        held, holder_id = acquire_room_type_lock(
            room_type_id=room_type_id,
            check_in=check_in, 
            check_out=check_out,
            max_available=db_available, 
            holder_id=holder_id,
            ttl=ttl,
        )
    except Exception:
        raise RedisUnavailable("Redis Unavailable")

    message = None if held else f"'{detail['name']}' is fully booked for {check_in} to {check_out}"

    return {
        "held": held,
        "holder_id": holder_id,
        "room_type_name": detail['name'],
        "available": db_available,
        "expires_in": ttl,
        "message": message,
    }    

def bulk_lock_room_type(rooms):
    grouped = Counter()
    for room in rooms:
        key = (room.get('room_type_id'), str(room.get('check_in')), str(room.get('check_out')))
        grouped[key] += 1

    room_requests = []
    errors = []

    for (room_type_id, check_in, check_out), qty in grouped.items():
        _available, detail = get_room_type_available(room_type_id, check_in, check_out)
        if detail.get('error'):
            errors.append({f'room[{room_type_id}]': detail['error']})
            continue

        room_requests.append({
            'room_type_id': room_type_id,
            'check_in': check_in,
            'check_out': check_out,
            'quantity': qty,
            'max_available': detail['db_available'],
        })

    if errors:
        return {
            'error': True,
            'errors': errors
        }

    try:
        all_held, holder_id, failures = bulk_acquire(room_requests, ttl=600)
    except Exception:
        raise RedisUnavailable("Redis Unavailable")

    return {
        'error': False,
        'all_heald': all_held,
        'holder_id': holder_id,
        'failures': failures
    }