import requests
from django.db import transaction
from django.db.models import Q

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import BookingStatus, RoomStatus, RoomType
from bookings.serializers import (
    BookingSerializer,
    DayTourRequestSerializer,
    OnlineBookingRequestSerializer,
    OnsiteBookingRequestSerializer,
)
from bookings.services.lock import (
    acquire_room_type_lock, get_locked_count, holder_has_lock,
    release_room_type_lock,
)
from transactions.models import BillingStatus, GuestStatus
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    BillingSerializerBase, CustomerSerializer, GuestListSerializer,
)

class RoomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 100

class CreateDayTourGuest(APIView):
    def post(self, request):
        serializer = DayTourRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            customer = self._create_customer(data['personalInfo'])
            billing = self._create_billing(customer, billing_status=BillingStatus.PROCESSING)

            tourist_added = []
            for name in data['touristList']:
                guest = GuestListSerializer(data={
                    'customer_bill': billing.id,
                    'guest': name,
                    'status': GuestStatus.PENDING,
                })
                guest.is_valid(raise_exception=True)
                guest.save()
                tourist_added.append(guest.data)

            amenities_added = []
            for item in data['selectedAmenities']:
                amenity = AmenitiesAvailedSerializer(data={
                    'amenity': item['id'],
                    'customer_bill': billing.id,
                    'head_count': item['hours'],
                })
                amenity.is_valid(raise_exception=True)
                amenity.save()
                amenities_added.append(amenity.data)

            activities_added = []
            for item in data['selectedActivities']:
                activity = ActivitiesAvailedSerializer(data={
                    'activity': item['id'],
                    'customer_bill': billing.id,
                    'hours_availed': item['hours'],
                })
                activity.is_valid(raise_exception=True)
                activity.save()
                activities_added.append(activity.data)

        return Response({
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'amenities': amenities_added,
            'activities': activities_added,
        }, status=status.HTTP_201_CREATED)

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


class BookingCreateMixin:
    """
    Shared booking creation logic used by both CreateStayInBooking (onsite)
    and CreateOnlineBooking (online).

    Both flows share availability checking, DB row locking, customer/billing
    creation, booking writes, and Redis lock release. Only two things differ:
      - Onsite: room is assigned at creation time (receptionist picks it).
      - Online: room=None at creation, assigned later on approval.
    """

    def _lock_room_types(self, rooms):
        """Acquire DB row-level locks on RoomType rows to serialise concurrent writes."""
        room_type_ids = {room['room_type'] for room in rooms}
        list(RoomType.objects.select_for_update().filter(id__in=room_type_ids))

    def _check_availability(self, rooms, holder_id=None):
        """Return a 409 Response if any room type is fully booked, else None."""
        errors = []
        for room_data in rooms:
            try:
                room_type = RoomType.objects.get(id=room_data['room_type'])
            except RoomType.DoesNotExist:
                errors.append(f"Room type {room_data['room_type']} not found")
                continue

            check_in = room_data['check_in']
            check_out = room_data['check_out']

            total = room_type.room.count()
            maintenance = room_type.room.filter(status=RoomStatus.MAINTENANCE).count()
            booked = room_type.bookings.filter(
                Q(check_in__lt=check_out)
                & Q(check_out__gt=check_in)
                & Q(status__in=[BookingStatus.APPROVED, BookingStatus.PENDING]),
            ).count()

            db_available = total - maintenance - booked
            try:
                locked = get_locked_count(room_type.id, str(check_in), str(check_out))
            except Exception:
                locked = 0

            if holder_id and holder_has_lock(room_type.id, str(check_in), str(check_out), holder_id):
                available = db_available  # holder already claimed a slot
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

    def _create_bookings(self, billing, rooms, assign_room=False):
        """
        Write Booking rows for each room in the list.

        assign_room=True  — onsite: room FK is set from the incoming data.
        assign_room=False — online: room is left None, assigned later on approval.
        """
        created = []
        for room in rooms:
            room['customer_bill'] = billing.id
            room['status'] = BookingStatus.PENDING
            if not assign_room:
                room['room'] = None
            serializer = BookingSerializer(data=room)
            if not serializer.is_valid():
                raise Exception(serializer.errors)
            serializer.save()
            created.append(serializer.data)
        return created

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


class CreateStayInBooking(BookingCreateMixin, APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Create a walk-in / reception desk booking. Rooms are assigned immediately.',
        request=OnsiteBookingRequestSerializer,
        responses={
            201: OpenApiExample(
                'Onsite booking created',
                value={
                    'customer': {'id': 1, 'first_name': 'Juan', 'last_name': 'Dela Cruz',
                                 'contact_number': '09123456789', 'email': 'juan@example.com',
                                 'created_at': '2026-08-01T10:00:00+08:00'},
                    'billing': {'id': 1, 'created_at': '2026-08-01T10:00:00+08:00',
                                'status': 'Processing', 'customer': 1},
                    'bookings': [{
                        'id': 1, 'customer_bill': 1, 'customer_name': 'Juan Dela Cruz',
                        'room': 2, 'room_type': 1, 'check_in': '2026-08-01',
                        'check_out': '2026-08-03', 'adult_count': 2, 'children_count': 1,
                        'extra_guest': 0, 'number_of_guests': 3, 'status': 'PENDING',
                        'created_at': '2026-08-01T10:00:00+08:00',
                        'number_of_nights': 2, 'total_cost': 5000.00,
                    }],
                },
                response_only=True,
            ),
        },
    )
    def post(self, request):
        serializer = OnsiteBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        holder_id = request.data.get('holder_id')

        booking_data = []
        for room in data['booking']:
            booking_data.append({
                'check_in': room['check_in'].isoformat(),
                'check_out': room['check_out'].isoformat(),
                'room_type': room['room_type'],
                'room': room['room_number'],
                'adult_count': room['adult_count'],
                'children_count': room.get('children_count', 0),
                'extra_guest': room.get('extra_guest', 0),
            })

        try:
            with transaction.atomic():
                self._lock_room_types(booking_data)
                availability_error = self._check_availability(booking_data, holder_id)
                if availability_error:
                    return availability_error

                customer = self._create_customer(data['customer'])
                billing = self._create_billing(
                    customer, billing_status=BillingStatus.PROCESSING,
                )
                created_bookings = self._create_bookings(billing, booking_data, assign_room=True)

        except Exception as e:
            return Response(
                {'error': 'Booking failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self._release_holder_locks(booking_data, holder_id)

        return Response({
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'bookings': created_bookings,
        }, status=status.HTTP_201_CREATED)


class CreateOnlineBooking(BookingCreateMixin, APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Create an online booking with customer info, room bookings, optional boat transfers, and a down-payment link.',
        request=OnlineBookingRequestSerializer,
        responses={
            201: OpenApiExample(
                'Online booking created',
                value={
                    'customer': {'id': 1, 'first_name': 'Juan', 'last_name': 'Dela Cruz',
                                 'contact_number': '09123456789', 'email': 'juan@example.com',
                                 'created_at': '2026-08-01T10:00:00+08:00'},
                    'billing': {'id': 1, 'created_at': '2026-08-01T10:00:00+08:00',
                                'status': 'Pending', 'customer': 1},
                    'bookings': [{
                        'id': 1, 'customer_bill': 1, 'customer_name': 'Juan Dela Cruz',
                        'room': None, 'room_type': 1, 'check_in': '2026-08-01',
                        'check_out': '2026-08-03', 'adult_count': 2, 'children_count': 1,
                        'extra_guest': 0, 'number_of_guests': 3, 'status': 'PENDING',
                        'created_at': '2026-08-01T10:00:00+08:00',
                        'number_of_nights': 2, 'total_cost': 5000.00,
                    }],
                    'boat': [1],
                    'guests': [{'id': 1, 'guest': 'Juan Dela Cruz', 'status': 'Pending'}],
                },
                response_only=True,
            ),
            409: OpenApiExample(
                'No availability',
                value={'error': 'No availability',
                       'details': ["'Standard Room' is fully booked for 2026-08-01 to 2026-08-03"]},
                response_only=True,
            ),
        },
    )
    def post(self, request):
        serializer = OnlineBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        holder_id = request.data.get('holder_id')

        try:
            with transaction.atomic():
                self._lock_room_types(data['rooms'])
                availability_error = self._check_availability(data['rooms'], holder_id)
                if availability_error:
                    return availability_error

                customer = self._create_customer(data['customer'])
                billing = self._create_billing(customer)
                created_bookings = self._create_bookings(billing, data['rooms'])
                boat_ids, tourist_added = self._create_boat(billing, data.get('boat', []))
        except Exception as e:
            return Response(
                {'error': 'Online booking failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self._release_holder_locks(data['rooms'], holder_id)

        response_data = {
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'bookings': created_bookings,
        }
        if boat_ids:
            response_data['boat'] = boat_ids
            response_data['guests'] = tourist_added

        return Response(response_data, status=status.HTTP_201_CREATED)

    # ── helpers (boat + payment are online-only) ───────────────

    def _create_boat(self, billing, boat_list):
        tourist_added = []
        boat_ids = []
        for availed_boat in boat_list:
            availed_boat['customer_bill'] = billing.id
            availed_boat['amenity'] = 1
            serializer = AmenitiesAvailedSerializer(data=availed_boat)
            serializer.is_valid(raise_exception=True)
            saved = serializer.save()
            boat_ids.append(saved.id)

            for tourist in availed_boat['guests']:
                guest_serializer = GuestListSerializer(data={
                    'customer_bill': billing.id,
                    'guest': tourist,
                    'status': GuestStatus.PENDING,
                })
                guest_serializer.is_valid(raise_exception=True)
                guest_serializer.save()
                tourist_added.append(guest_serializer.data)
        return boat_ids, tourist_added

    def _create_payment_link(self, billing, customer, booking_ids, payment_data):
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
                'https://seal-app-nvafi.ondigitalocean.app/api/payment-link/',
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            detail = str(e)
            if hasattr(e, 'response') and e.response is not None:
                detail = e.response.json() if e.response.headers.get('content-type', '').startswith('application/json') else {'body': e.response.text[:500]}
            raise Exception(f'Payment link API failed: {detail}') from e


class LockRoomType(APIView):
    """Acquire a 10-minute lock on a room-type count for a date range.

    Called when user selects a room type on the booking form.
    Lock expires after 10 minutes if not consumed by CreateOnlineBooking."""

    def post(self, request):
        room_type_id = request.data.get('room_type')
        check_in = request.data.get('check_in')
        check_out = request.data.get('check_out')

        errors = {}
        if not room_type_id:
            errors['room_type'] = 'This field is required.'
        if not check_in:
            errors['check_in'] = 'This field is required.'
        if not check_out:
            errors['check_out'] = 'This field is required.'
        if errors:
            return Response({'error': errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room_type = RoomType.objects.get(id=room_type_id)
        except RoomType.DoesNotExist:
            return Response(
                {'error': f"Room type {room_type_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        total = room_type.room.count()
        maintenance = room_type.room.filter(status=RoomStatus.MAINTENANCE).count()
        booked = room_type.bookings.filter(
            Q(check_in__lt=check_out)
            & Q(check_out__gt=check_in)
            & Q(status__in=[BookingStatus.APPROVED, BookingStatus.PENDING]),
        ).count()
        db_available = total - maintenance - booked

        try:
            held, holder_id = acquire_room_type_lock(
                room_type_id, check_in, check_out,
                max_available=db_available, ttl=600,
            )
        except Exception:
            return Response(
                {'error': 'Lock service unavailable'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not held:
            return Response({
                'held': False,
                'available': db_available,
                'message': f"'{room_type.name}' is fully booked for {check_in} to {check_out}",
            })

        return Response({
            'held': True,
            'holder_id': holder_id,
            'expires_in': 600,
            'room_type': room_type.name,
            'check_in': check_in,
            'check_out': check_out,
        })


class ReleaseRoomType(APIView):
    """Explicitly release a room-type lock.

    Called when user navigates away from booking form or closes tab."""

    def post(self, request):
        room_type_id = request.data.get('room_type')
        check_in = request.data.get('check_in')
        check_out = request.data.get('check_out')
        holder_id = request.data.get('holder_id')

        if not all([room_type_id, check_in, check_out, holder_id]):
            return Response(
                {'error': 'room_type, check_in, check_out, and holder_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            released = release_room_type_lock(
                room_type_id, check_in, check_out, holder_id,
            )
        except Exception:
            released = False

        return Response({'released': released})
