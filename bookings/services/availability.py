"""Shared availability helpers — single source for room capacity + overlap logic."""

from collections import Counter
from django.db.models import Count, Q

from bookings.models import Booking, BookingStatus, RoomStatus, RoomType
from bookings.services.lock import get_locked_count, holder_has_lock


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


def get_room_type_available(room_type_id, check_in, check_out,
                            exclude_booking_id=None, holder_id=None):
    """Check single room type + date range. Returns (available: bool, detail: dict).

    detail keys: name, total, maintenance, booked, locked, db_available, available.
    2 queries (1 annotated RoomType + 1 booking count).
    """
    caps = get_room_type_capacities([room_type_id])
    if room_type_id not in caps:
        return False, {'error': f'Room type {room_type_id} not found'}

    cap = caps[room_type_id]
    booked = Booking.objects.filter(
        room_type_id=room_type_id,
        status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        check_in__lt=check_out,
        check_out__gt=check_in,
    )
    if exclude_booking_id is not None:
        booked = booked.exclude(id=exclude_booking_id)
    booked = booked.count()

    db_available = cap['total'] - cap['maintenance'] - booked

    try:
        locked = get_locked_count(room_type_id, str(check_in), str(check_out))
    except Exception:
        locked = 0

    if holder_id and holder_has_lock(room_type_id, str(check_in), str(check_out), holder_id):
        available_count = db_available
    else:
        available_count = db_available - locked

    return available_count > 0, {
        'name': cap['name'],
        'total': cap['total'],
        'maintenance': cap['maintenance'],
        'booked': booked,
        'locked': locked,
        'db_available': db_available,
        'available': available_count,
    }
