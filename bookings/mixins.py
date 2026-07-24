from django.db.models import Count, Q

from rest_framework import status
from rest_framework.response import Response

from bookings.models import Booking, BookingStatus, RoomStatus, RoomType
from bookings.serializers import (
    BookingSerializer,

)
from bookings.services.lock import (
    acquire_room_type_lock, get_locked_count, holder_has_lock,
    release_room_type_lock,
)
from transactions.models import BillingStatus
from transactions.serializers import (
    BillingSerializerBase, CustomerSerializer
)



class BillingCreationMixin:
    def _create_customer(self, data):
        serializer = CustomerSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def _create_billing(self, customer, billing_status=None):
        serializer = BillingSerializerBase(data={
            'customer': customer.id,
            'status': billing_status or BillingStatus.PENDING,
        })
        serializer.is_valid(raise_exception=True)
        return serializer.save()


class BookingCreateMixin(BillingCreationMixin):
    def _lock_room_types(self, rooms):
        """Acquire DB row-level locks on RoomType rows to serialise concurrent writes."""
        room_type_ids = {room['room_type'] for room in rooms}
        list(RoomType.objects.select_for_update().filter(id__in=room_type_ids))

    def _check_availability(self, rooms, holder_id=None):
        """Return a 409 Response if any room type is fully booked, else None."""
        from collections import Counter

        errors = []
        room_type_ids = {room['room_type'] for room in rooms}

        # Single query: all RoomTypes with total/maintenance counts
        room_types = RoomType.objects.filter(id__in=room_type_ids).annotate(
            total_rooms=Count('room'),
            maintenance_rooms=Count(
                'room', filter=Q(room__status=RoomStatus.MAINTENANCE),
            ),
        )
        room_type_map = {rt.id: rt for rt in room_types}

        for room_data in rooms:
            if room_data['room_type'] not in room_type_map:
                errors.append(f"Room type {room_data['room_type']} not found")

        if errors:
            return Response(
                {'error': 'No availability', 'details': errors},
                status=status.HTTP_409_CONFLICT,
            )

        # Batch booking-overlap counts: 1 query per unique room_type
        rooms_by_type: dict[int, list] = {}
        for room in rooms:
            if room['room_type'] in room_type_map:
                rooms_by_type.setdefault(room['room_type'], []).append(room)

        booking_counts: dict[tuple, int] = Counter()
        for room_type_id, type_rooms in rooms_by_type.items():
            date_filter = Q()
            for r in type_rooms:
                date_filter |= Q(
                    check_in__lt=r['check_out'],
                    check_out__gt=r['check_in'],
                )
            overlapping = [
                (ci.isoformat(), co.isoformat())
                for ci, co in Booking.objects.filter(
                    room_type_id=room_type_id,
                    status__in=[BookingStatus.APPROVED, BookingStatus.PENDING],
                )
                .filter(date_filter)
                .values_list('check_in', 'check_out')
            ]

            for r in type_rooms:
                check_in = str(r['check_in'])
                check_out = str(r['check_out'])
                count = sum(
                    1 for ci, co in overlapping
                    if ci < check_out and co > check_in
                )
                booking_counts[(room_type_id, str(check_in), str(check_out))] = count

        # Check each room's availability
        for room_data in rooms:
            rt_id = room_data['room_type']
            if rt_id not in room_type_map:
                continue

            room_type = room_type_map[rt_id]
            check_in = room_data['check_in']
            check_out = room_data['check_out']

            total = room_type.total_rooms
            maintenance = room_type.maintenance_rooms
            key = (rt_id, str(check_in), str(check_out))
            booked = booking_counts.get(key, 0)

            db_available = total - maintenance - booked
            try:
                locked = get_locked_count(rt_id, str(check_in), str(check_out))
            except Exception:
                locked = 0

            if holder_id and holder_has_lock(rt_id, str(check_in), str(check_out), holder_id):
                available = db_available
            else:
                available = db_available - locked

            if available <= 0:
                errors.append(
                    f"'{room_type.name}' is fully booked for {check_in} to {check_out}"
                )

        if errors:
            return Response(
                {'error': 'No availability', 'details': errors},
                status=status.HTTP_409_CONFLICT,
            )
        return None


    def _create_bookings(self, billing, rooms, assign_room=False):
        """
        Write Booking rows for each room in the list.

        assign_room=True  — onsite: room FK is set from the incoming data.
        assign_room=False — online: room is left None, assigned later on approval.
        """
        booking_objs = []
        for room in rooms:
            room['customer_bill'] = billing.id
            room['status'] = BookingStatus.PENDING
            if not assign_room:
                room['room'] = None
            serializer = BookingSerializer(data=room)
            if not serializer.is_valid():
                raise Exception(serializer.errors)
            booking_objs.append(Booking(**serializer.validated_data))

        Booking.objects.bulk_create(booking_objs)

        created = Booking.objects.filter(customer_bill=billing).select_related(
            'customer_bill__customer', 'room_type',
        )
        return BookingSerializer(created, many=True).data

    def _release_holder_locks(self, rooms, holder_id):
        """Release all Redis locks held by holder_id for the given rooms."""
        if not holder_id:
            return
        for room in rooms:
            try:
                release_room_type_lock(
                    room['room_type'], str(room['check_in']),
                    str(room['check_out']), holder_id,
                )
            except Exception:
                pass