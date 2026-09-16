import os

import requests

from bookings.models import Booking, BookingStatus, Room, RoomStatus, RoomType

from transactions.models import (
    Amenities, ActivitiesAvailed, AmenitiesAvailed, BillingStatus, GuestList, GuestStatus,
    Customer, Billing
)
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    GuestListSerializer,
)
from django.conf import settings
import logging

from transactions.services import (
    create_billing, create_amenity_availed, create_guest_list,
    create_activities_availed_bulk, create_amenities_availed_bulk
)

import requests
from django.db import transaction
from .availability import lock_room_types, validate_rooms_availability
from django.db.models import Count, Exists, OuterRef, Q


@transaction.atomic
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


@transaction.atomic
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

def create_bookings(*, billing, rooms, assign_room=False):
    booking_objs = [
        Booking(
            customer_bill=billing,
            room=room_data.get("room") if assign_room else None,
            room_type_id=room_data["room_type"],
            check_in=room_data["check_in"],
            check_out=room_data["check_out"],
            adult_count=room_data["adult_count"],
            children_count=room_data["children_count"],
            extra_guest=room_data.get("extra_guest"),
            status=BookingStatus.PENDING,
        ) 
        for room_data in rooms
    ]
    return Booking.objects.bulk_create(booking_objs)
    
@transaction.atomic
def create_online_booking(*, customer, rooms, boat_details=None, holder_id):
    lock_room_types(rooms)
    validate_rooms_availability(rooms=rooms, holder_id=holder_id)
    customer = Customer.objects.create(**customer)
    billing = create_billing(customer=customer)
    booking = create_bookings(billing=billing, rooms=rooms)
    boat = create_amenity_availed(
        billing=billing, amenity="Boat Transfer", 
        head_count=boat_details["head_count"],
        time=boat_details["time"]
    ) if boat_details else None
    guests = create_guest_list(
        billing=billing, guests=boat_details["guests"]
    ) if boat_details else []

    return {
        "customer": customer,
        "billing": billing,
        "booking": booking,
        "boat": boat,
        "guests": guests
    }

@transaction.atomic
def create_onsite_booking(*, customer, rooms, holder_id):
    lock_room_types(rooms)
    validate_rooms_availability(rooms=rooms, holder_id=holder_id)
    customer = Customer.objects.create(**customer)
    billing = create_billing(customer=customer)
    booking = create_bookings(billing=billing, rooms=rooms, assign_room=True)

    return {
        "customer": customer,
        "billing": billing,
        "booking": booking
    }

@transaction.atomic
def create_day_tour_guests(*, customer, guests, amenities, activities):    
    customer = Customer.objects.create(**customer)
    billing = create_billing(customer=customer, billing_status=BillingStatus.PROCESSING)
    guests = create_guest_list(billing=billing, guests=guests, status=GuestStatus.CHECKED_IN)
    amenities_availed = create_amenities_availed_bulk(billing=billing, amenities=amenities)
    activities_availed = create_activities_availed_bulk(billing=billing, activities=activities)

    return {
        "customer": customer,
        "billing": billing,
        "amenities_availed": amenities_availed,
        "activities_availed": activities_availed,
        "guests": guests
    }



def update_booking(*, booking, data):
    new_room_type = data.get('room_type', booking.room_type)
    new_check_in = data.get('check_in', booking.check_in)
    new_check_out = data.get('check_out', booking.check_out)
    dates_changed = (
            'check_in' in data
            or 'check_out' in data
            or 'room_type' in data
        )

    if dates_changed:
        rt_id = new_room_type.id if hasattr(new_room_type, 'id') else new_room_type
        validate_rooms_availability(                                                                                                         
            rooms=[{'room_type': rt_id, 'check_in': new_check_in, 'check_out': new_check_out}],                                              
            exclude_booking_id=booking.id,                                                                                                   
        )   

    for field, value in data.items():
        setattr(booking, field, value)

    booking.save()
    booking.refresh_from_db()
    return booking

def lookup_billing(billing_reference: str, email: str):
    """
    Look up a Billing by billing_reference + customer email.
    Both must match — returns None if either is wrong (intentional: avoids
    leaking whether a billing reference exists).

    Returns a Billing instance with bookings, room_type, room, and
    customer_bill__customer fully prefetched (3 queries total).
    """
    from django.db.models import Prefetch

    billing = (
        Billing.objects
        .filter(billing_reference=billing_reference)
        .select_related('customer')
        .prefetch_related(
            Prefetch(
                'bookings',
                queryset=Booking.objects.select_related('room_type', 'room', 'customer_bill__customer'),
            )
        )
        .first()
    )

    if not billing:
        return None

    if billing.customer.email.lower() != email.strip().lower():
        return None

    return billing


def booking_look_up(email: str, reference_id: str):
    """Deprecated: use lookup_billing() instead."""
    return Booking.objects.filter(Q(reference_id=reference_id) & Q(customer_bill__customer__email=email)).select_related(
            'customer_bill__customer', 'room_type', 'room', "room__type"
        ).first()



