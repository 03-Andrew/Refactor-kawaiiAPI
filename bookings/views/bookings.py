import logging

from django.db import transaction
from dotenv import load_dotenv

from drf_spectacular.utils import OpenApiExample, extend_schema, OpenApiParameter
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny


from bookings.models import Booking
from bookings.serializers import (
    BookingSerializer,
    DayTourRequestSerializer,
    OnlineBookingRequestSerializer,
    OnsiteBookingRequestSerializer,
)
from bookings.services.availability import get_room_type_available
from bookings.services.booking import (
    approve_booking, cancel_booking,
    create_amenities, create_activities, create_boat_transfer, create_guest_list,
)
from bookings.services.lock import (
    acquire_room_type_lock, bulk_acquire, release_room_type_lock,
)
from bookings.turnstile import validate_turnstile
from transactions.models import BillingStatus
from transactions.serializers import (
    BillingSerializerBase, CustomerSerializer,
)
from ..mixins import BillingCreationMixin, BookingCreateMixin

logger = logging.getLogger(__name__)
from django.conf import settings

from ..tasks import send_email
load_dotenv()


class CreateDayTourGuest(BillingCreationMixin, APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Create a day tour booking with customer info, guest list, selected amenities, and selected activities.',
        request=DayTourRequestSerializer
    )
    def post(self, request):
        serializer = DayTourRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            customer = self._create_customer(data['customer'])
            billing = self._create_billing(customer, billing_status=BillingStatus.PROCESSING)
            guests = create_guest_list(billing=billing, names=data.get('guest_list', []))
            amenities_added = create_amenities(billing=billing, items=data.get('selected_amenities', []))
            activities_added = create_activities(billing=billing, items=data.get('selected_activities', []))

        return Response({
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'amenities': amenities_added,
            'activities': activities_added,
            'guests': guests,
        }, status=status.HTTP_201_CREATED)


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
                'check_in': room['check_in'],
                'check_out': room['check_out'],
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

        except serializers.ValidationError as e:
            self._release_holder_locks(booking_data, holder_id)
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            self._release_holder_locks(booking_data, holder_id)
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
    authentication_classes = []
    permission_classes = [AllowAny]
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
        turnstile_token = request.data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )        

        try:
            with transaction.atomic():
                self._lock_room_types(data['rooms'])
                availability_error = self._check_availability(data['rooms'], holder_id)
                if availability_error:
                    return availability_error

                customer = self._create_customer(data['customer'])
                billing = self._create_billing(customer)
                created_bookings = self._create_bookings(billing, data['rooms'])
                boat_ids, tourist_added = create_boat_transfer(billing=billing, boat_list=data.get('boat', []))

        except serializers.ValidationError as e:
            self._release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            self._release_holder_locks(data['rooms'], holder_id)
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


        subject = "Online Booking Confirmation"
        message = f"Booking Successful for {data['customer']['first_name']} {data['customer']['last_name']}"
        if settings.DEBUG:
            try:
                send_email.delay(subject, message, [data['customer']['email']])
            except Exception as exc:
                logger.warning('Failed to queue email for billing %s: %s', billing.id, exc)

        return Response(response_data, status=status.HTTP_201_CREATED)

class BookingPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 100


class ListBookings(generics.ListAPIView):
    serializer_class = BookingSerializer
    pagination_class = BookingPagination

    @extend_schema(
        tags=['Bookings'],
        description='List all bookings with optional filters.',
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'customer_bill__customer', 'room_type', 'room',
        ).all()

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        room_type = self.request.query_params.get('room_type')
        if room_type:
            qs = qs.filter(room_type_id=room_type)

        room = self.request.query_params.get('room')
        if room:
            qs = qs.filter(room_id=room)

        check_in_from = self.request.query_params.get('check_in_from')
        if check_in_from:
            qs = qs.filter(check_in__gte=check_in_from)

        check_in_to = self.request.query_params.get('check_in_to')
        if check_in_to:
            qs = qs.filter(check_in__lte=check_in_to)

        check_out_from = self.request.query_params.get('check_out_from')
        if check_out_from:
            qs = qs.filter(check_out__gte=check_out_from)

        check_out_to = self.request.query_params.get('check_out_to')
        if check_out_to:
            qs = qs.filter(check_out__lte=check_out_to)

        billing = self.request.query_params.get('customer_bill')
        if billing:
            qs = qs.filter(customer_bill_id=billing)

        return qs.order_by('-created_at')


class EditBooking(APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Get a single booking by ID.',
    )
    def get(self, _request, pk):
        try:
            booking = Booking.objects.select_related(
                'customer_bill__customer', 'room_type', 'room',
            ).get(pk=pk)
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(BookingSerializer(booking).data)

    @extend_schema(
        tags=['Bookings'],
        description='Edit a booking. Re-checks availability when dates or room type change.',
        request=BookingSerializer,
    )
    def patch(self, request, pk):
        try:
            booking = Booking.objects.select_related(
                'customer_bill__customer', 'room_type',
            ).get(pk=pk)
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = BookingSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

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
            availability_error = self._check_edit_availability(
                rt_id, new_check_in, new_check_out, booking.id,
            )
            if availability_error:
                return availability_error

        for field, value in data.items():
            setattr(booking, field, value)
        booking.save()

        booking.refresh_from_db()
        return Response(
            BookingSerializer(booking).data,
            status=status.HTTP_200_OK,
        )

    def _check_edit_availability(self, room_type_id, check_in, check_out, exclude_id):
        available, detail = get_room_type_available(
            room_type_id, check_in, check_out, exclude_booking_id=exclude_id,
        )
        if detail.get('error'):
            return Response(
                {'error': detail['error']},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not available:
            return Response({
                'error': 'No availability',
                'details': [
                    f"'{detail['name']}' is fully booked for {check_in} to {check_out}"
                ],
            }, status=status.HTTP_409_CONFLICT)
        return None


class ApproveBooking(APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Approve a PENDING booking with a specific room.',
        parameters=[OpenApiParameter('room', type=int, description='Room id')],
    )
    def post(self, request, pk):
        booking = _get_booking(pk)
        if isinstance(booking, Response):
            return booking

        room_id = request.data.get('room')
        if not room_id:
            return Response(
                {'error': 'room is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            booking = approve_booking(booking=booking, room_id=room_id)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)


class CancelBooking(APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Cancel a PENDING or APPROVED booking.',
    )
    def post(self, _request, pk):
        booking = _get_booking(pk)
        if isinstance(booking, Response):
            return booking

        try:
            booking = cancel_booking(booking)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)


def _get_booking(pk):
    try:
        return Booking.objects.select_related(
            'customer_bill__customer', 'room_type',
        ).get(pk=pk)
    except Booking.DoesNotExist:
        return Response(
            {'error': 'Booking not found'},
            status=status.HTTP_404_NOT_FOUND,
        )


class LockRoomType(APIView):
    """Acquire a 10-minute lock on a room-type count for a date range.

    Called when user selects a room type on the booking form.
    Lock expires after 10 minutes if not consumed by CreateOnlineBooking."""
    authentication_classes = []
    permission_classes = [AllowAny]
    @extend_schema(
        tags=['Bookings'],
        description='Acquire a 10-minute lock on a room-type for a date range.',
    )
    def post(self, request):
        room_type_id = request.data.get('room_type')
        check_in = request.data.get('check_in')
        check_out = request.data.get('check_out')
        turnstile_token = request.data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )

        errors = {}
        if not room_type_id:
            errors['room_type'] = 'This field is required.'
        if not check_in:
            errors['check_in'] = 'This field is required.'
        if not check_out:
            errors['check_out'] = 'This field is required.'
        if errors:
            return Response({'error': errors}, status=status.HTTP_400_BAD_REQUEST)

        _available, detail = get_room_type_available(room_type_id, check_in, check_out)
        if detail.get('error'):
            return Response(
                {'error': detail['error']},
                status=status.HTTP_404_NOT_FOUND,
            )

        db_available = detail['db_available']

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
                'message': f"'{detail['name']}' is fully booked for {check_in} to {check_out}",
            })

        return Response({
            'held': True,
            'holder_id': holder_id,
            'expires_in': 600,
            'room_type': detail['name'],
            'check_in': check_in,
            'check_out': check_out,
        })

class BulkLockRoomType(APIView):
    """Acquire locks on multiple room-type/date-range combos atomically.

    All-or-nothing: if any combo is at capacity, no locks are held.
    Returns a single holder_id for all locked combos."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Bookings'],
        description='Acquire locks on multiple room-type/date-range combos atomically.',
    )
    def post(self, request):
        rooms = request.data.get('rooms', [])
        turnstile_token = request.data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not rooms or not isinstance(rooms, list):
            return Response(
                {'error': {'rooms': 'A non-empty list of room objects is required.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room_requests = []
        errors = []
        for i, room in enumerate(rooms):
            room_type_id = room.get('room_type')
            check_in = room.get('check_in')
            check_out = room.get('check_out')
            entry_errors = {}
            if not room_type_id:
                entry_errors['room_type'] = 'This field is required.'
            if not check_in:
                entry_errors['check_in'] = 'This field is required.'
            if not check_out:
                entry_errors['check_out'] = 'This field is required.'
            if entry_errors:
                errors.append({f'room[{i}]': entry_errors})
                continue

            _available, detail = get_room_type_available(room_type_id, check_in, check_out)
            if detail.get('error'):
                errors.append({f'room[{i}]': detail['error']})
                continue

            room_requests.append({
                'room_type_id': room_type_id,
                'check_in': check_in,
                'check_out': check_out,
                'max_available': detail['db_available'],
            })

        if errors:
            return Response({'error': errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            all_held, holder_id, failures = bulk_acquire(room_requests, ttl=600)
        except Exception:
            return Response(
                {'error': 'Lock service unavailable'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not all_held:
            return Response({
                'held': False,
                'failures': failures,
                'message': 'Some room types are fully booked for the requested dates.',
            })

        return Response({
            'held': True,
            'holder_id': holder_id,
            'expires_in': 600,
            'rooms': rooms,
        })

class ReleaseRoomType(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    """Explicitly release a room-type lock.

    Called when user navigates away from booking form or closes tab."""

    @extend_schema(
        tags=['Bookings'],
        description='Release a previously acquired room-type lock.',
    )
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
