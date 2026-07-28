import os

import requests

from bookings.models import Booking, BookingStatus, Room, RoomStatus
from transactions.models import (
    ActivitiesAvailed, AmenitiesAvailed, BillingStatus, GuestList, GuestStatus,
)
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    GuestListSerializer,
)

def approve_booking(*, booking, room_id, **extra_fields):
    """Approve a PENDING booking with the given room.

    Raises ValueError if booking is not PENDING, room is not found,
    room is unavailable, or room is already booked for the date range.
    Returns the updated booking (already saved).
    """
    if booking.status != BookingStatus.PENDING:
        raise ValueError(f'Cannot approve booking with status {booking.status}')

    try:
        room = Room.objects.get(pk=room_id)
    except Room.DoesNotExist:
        raise ValueError(f'Room {room_id} not found')

    if room.status != RoomStatus.AVAILABLE:
        raise ValueError(f'Room {room.number} is not available (status: {room.status})')

    if room.type_id != booking.room_type_id:
        raise ValueError(
            f'Room {room.number} is type "{room.type.name}", '
            f'but booking requires "{booking.room_type.name}"'
        )

    overlapping = Booking.objects.filter(
        room=room,
        status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
        check_in__lt=booking.check_out,
        check_out__gt=booking.check_in,
    ).exclude(pk=booking.pk).exists()

    if overlapping:
        raise ValueError(
            f'Room {room.number} is already booked for {booking.check_in} to {booking.check_out}'
        )

    booking.room = room
    booking.status = BookingStatus.APPROVED

    for field, value in extra_fields.items():
        setattr(booking, field, value)

    booking.save()
    return booking


def cancel_booking(booking):
    """Cancel a PENDING or APPROVED booking. Cascades billing cancel if no active bookings remain.

    Raises ValueError if booking cannot be cancelled.
    Returns the updated booking (already saved).
    """
    if booking.status not in [BookingStatus.PENDING, BookingStatus.APPROVED]:
        raise ValueError(f'Cannot cancel booking with status {booking.status}')

    booking.status = BookingStatus.CANCELLED
    booking.save()

    billing = booking.customer_bill
    other_active = Booking.objects.filter(
        customer_bill=billing,
    ).exclude(
        status__in=[BookingStatus.CANCELLED, BookingStatus.REJECTED],
    ).exists()

    if not other_active:
        billing.status = BillingStatus.CANCELLED
        billing.save()

    return booking


# ── Day tour helpers ───────────────────────────────────────

def create_guest_list(*, billing, names):
    """Bulk-create GuestList entries with CHECKED_IN status. Returns serialized data."""
    validated = []
    for name in names:
        serializer = GuestListSerializer(data={
            'customer_bill': billing.id,
            'guest': name,
            'status': GuestStatus.CHECKED_IN,
        })
        serializer.is_valid(raise_exception=True)
        validated.append(serializer.validated_data)

    objs = GuestList.objects.bulk_create([
        GuestList(**v) for v in validated
    ])
    return GuestListSerializer(objs, many=True).data


def create_amenities(*, billing, items):
    """Bulk-create AmenitiesAvailed entries. Returns serialized data."""
    if not items:
        return []

    validated = []
    for item in items:
        serializer = AmenitiesAvailedSerializer(data={
            'amenity': item['id'],
            'customer_bill': billing.id,
            'head_count': item['head_count'],
        })
        serializer.is_valid(raise_exception=True)
        validated.append(serializer.validated_data)

    objs = AmenitiesAvailed.objects.bulk_create([
        AmenitiesAvailed(**v) for v in validated
    ])
    return AmenitiesAvailedSerializer(objs, many=True).data


def create_activities(*, billing, items):
    """Bulk-create ActivitiesAvailed entries. Returns serialized data."""
    if not items:
        return []

    validated = []
    for item in items:
        serializer = ActivitiesAvailedSerializer(data={
            'activity': item['id'],
            'customer_bill': billing.id,
            'hours_availed': item['hours'],
        })
        serializer.is_valid(raise_exception=True)
        validated.append(serializer.validated_data)

    objs = ActivitiesAvailed.objects.bulk_create([
        ActivitiesAvailed(**v) for v in validated
    ])
    return ActivitiesAvailedSerializer(objs, many=True).data


# ── Online booking helpers ─────────────────────────────────

def create_boat_transfer(*, billing, boat_list):
    """Bulk-create boat transfer amenities and guest entries. Returns (boat_ids, guests_data)."""
    if not boat_list:
        return [], []

    amenity_objs = []
    guest_objs = []
    for availed_boat in boat_list:
        availed_boat['customer_bill'] = billing.id
        availed_boat['amenity'] = 1
        serializer = AmenitiesAvailedSerializer(data=availed_boat)
        serializer.is_valid(raise_exception=True)
        amenity_objs.append(AmenitiesAvailed(**serializer.validated_data))

        for tourist in availed_boat['guests']:
            guest_serializer = GuestListSerializer(data={
                'customer_bill': billing.id,
                'guest': tourist,
                'status': GuestStatus.PENDING,
            })
            guest_serializer.is_valid(raise_exception=True)
            guest_objs.append(GuestList(**guest_serializer.validated_data))

    AmenitiesAvailed.objects.bulk_create(amenity_objs)
    boat_ids = list(
        AmenitiesAvailed.objects.filter(customer_bill=billing, amenity=1)
        .values_list('id', flat=True)
    )

    GuestList.objects.bulk_create(guest_objs)
    created_guests = GuestList.objects.filter(customer_bill=billing)
    tourist_added = GuestListSerializer(created_guests, many=True).data

    return boat_ids, tourist_added


def create_payment_link(*, billing, customer, booking_ids, payment_data):
    """Create a down-payment link via external payment API. Returns the API response dict."""
    payload = {
        'billing_id': str(billing.id),
        'payment_for': 'Down Payment',
        'payment_status': 'Down Payment',
        'content_type': 'booking',
        'object_id': ','.join(booking_ids),
        'amount': payment_data['amount'],
        'description': f'Booking for customer {customer.id}',
        'remarks': f'Booking for customer {customer.id}',
    }
    try:
        response = requests.post(
            os.environ.get('PAYMENT_LINK_URL'),
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        detail = str(e)
        if hasattr(e, 'response') and e.response is not None:
            ct = e.response.headers.get('content-type', '')
            detail = e.response.json() if ct.startswith('application/json') else {'body': e.response.text[:500]}
        raise Exception(f'Payment link API failed: {detail}') from e
