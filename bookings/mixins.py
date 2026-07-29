import logging

from rest_framework import status
from rest_framework.response import Response

from bookings.models import Booking, BookingStatus, RoomType
from bookings.serializers import (
    BookingSerializer,

)
from bookings.services.availability import (
    get_overlap_counts, get_room_type_capacities,
)
from bookings.services.lock import (
    get_locked_count, holder_has_lock, release_room_type_lock,
)
from transactions.models import BillingStatus
from transactions.serializers import (
    BillingSerializerBase, CustomerSerializer
)

logger = logging.getLogger(__name__)



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

    def _check_availability(self, rooms, holder_id=None, exclude_booking_id=None):
        """Return a 409 Response if any room type is fully booked, else None."""
        errors = []
        room_type_ids = {room['room_type'] for room in rooms}

        capacities = get_room_type_capacities(room_type_ids)
        missing = room_type_ids - set(capacities)
        for rt_id in missing:
            errors.append(f"Room type {rt_id} not found")
        if errors:
            return Response(
                {'error': 'No availability', 'details': errors},
                status=status.HTTP_409_CONFLICT,
            )

        rooms_by_type: dict[int, list] = {}
        for room in rooms:
            if room['room_type'] in capacities:
                rooms_by_type.setdefault(room['room_type'], []).append(room)

        booking_counts = get_overlap_counts(rooms_by_type, exclude_booking_id)

        for room_data in rooms:
            rt_id = room_data['room_type']
            if rt_id not in capacities:
                continue

            cap = capacities[rt_id]
            check_in = room_data['check_in']
            check_out = room_data['check_out']
            key = (rt_id, str(check_in), str(check_out))
            booked = booking_counts.get(key, 0)

            db_available = cap['total'] - cap['maintenance'] - booked
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
                    f"'{cap['name']}' is fully booked for {check_in} to {check_out}"
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
            serializer.is_valid(raise_exception=True)
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
            except Exception as exc:
                logger.warning(
                    'Failed to release lock for room_type=%s dates=%s->%s holder=%s: %s',
                    room['room_type'], room['check_in'], room['check_out'],
                    holder_id, exc,
                )