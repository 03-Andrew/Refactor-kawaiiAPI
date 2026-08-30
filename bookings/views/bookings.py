import logging

from django.db import transaction
from dotenv import load_dotenv

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from kawaiiAPI.permissions import IsReceptionistOrAdmin
from django.utils.decorators import method_decorator
from idempotency_key.decorators import idempotency_key

from bookings.models import Booking
from bookings.serializers import (
    BookingSerializer,
    DayTourRequestSerializer,
    OnlineBookingRequestSerializer,
    OnsiteBookingRequestSerializer,
    BulkLockRoomTypeSerializer,
    SingleLockRoomTypeSerializer
)

from bookings.exceptions import RoomTypeNotFoundError, RoomUnavailableError, RedisUnavailable
from bookings.services.availability import (
    get_room_type_available, lock_room_type, bulk_lock_room_type
)
from bookings.services.booking import (
    approve_booking, cancel_booking,
    create_online_booking, create_day_tour_guests,
    create_onsite_booking, update_booking
)
from bookings.services.lock import (
    acquire_room_type_lock, bulk_acquire, release_room_type_lock, release_holder_locks
)
from bookings.turnstile import validate_turnstile
from transactions.models import BillingStatus
from transactions.serializers import (
    BillingSerializerBase, CustomerSerializer, GuestListSerializer,
    AmenitiesAvailedSerializer, ActivitiesAvailedSerializer
)

logger = logging.getLogger(__name__)
from django.conf import settings

from transactions.services import create_guest_list
from transactions.models import GuestStatus

load_dotenv()


class BookingPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 100


class CreateDayTourGuest(APIView):
    permission_classes = [IsReceptionistOrAdmin]

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
            day_tour_guests = create_day_tour_guests(
                customer=data['customer'],
                guests=data.get('guest_list', []),
                amenities=data.get('selected_amenities', []),
                activities=data.get('selected_activities', [])
            )
        return Response({
            'customer': CustomerSerializer(day_tour_guests['customer']).data,
            'billing': BillingSerializerBase(day_tour_guests['billing']).data,
            'amenities': AmenitiesAvailedSerializer(day_tour_guests['amenities_availed'], many=True).data,
            'activities': ActivitiesAvailedSerializer(day_tour_guests['activities_availed'], many=True).data,
            'guests': GuestListSerializer(day_tour_guests['guests'], many=True).data,
        }, status=status.HTTP_201_CREATED)


class CreateStayInBooking(APIView):
    permission_classes = [IsReceptionistOrAdmin]

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
        holder_id = request.data.get('holder_id') or request.data.get('holder_ids')

        try:
            booking = create_onsite_booking(
                customer=data['customer'],
                rooms=data['booking'],
                holder_id=holder_id
            )

        except RoomUnavailableError as e:
            release_holder_locks(data['booking'], holder_id)
            return Response(
                {'error': 'No availability', 'details': e.details},
                status=status.HTTP_409_CONFLICT,
            )
        except RoomTypeNotFoundError as e:
            release_holder_locks(data['booking'], holder_id)
            return Response(
                {'error': 'Not found', 'details': str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except serializers.ValidationError as e:
            release_holder_locks(data['booking'], holder_id)
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            release_holder_locks(data['booking'], holder_id)
            return Response(
                {'error': 'Booking failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        release_holder_locks(data['booking'], holder_id)

        return Response({
            'customer': CustomerSerializer(booking['customer']).data,
            'billing': BillingSerializerBase(booking['billing']).data,
            'bookings': BookingSerializer(booking['booking'], many=True).data,
        }, status=status.HTTP_201_CREATED)

@method_decorator(idempotency_key(optional=False), name='dispatch')
class CreateOnlineBooking(APIView):
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
                    'guests': [{'id': 1, 'guest': 'Juan Dela Cruz', 'status': 'Pending'}],
                },
                response_only=True,
            ),
        },
    )
    def post(self, request):
        serializer = OnlineBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        holder_id = request.data.get('holder_id') or request.data.get('holder_ids')
        turnstile_token = request.data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )        

        try:
            online_booking = create_online_booking(
                customer=data.get('customer'),
                rooms=data.get('rooms'),
                boat_details=data.get('boat'),
                holder_id=holder_id
            )

        except RoomUnavailableError as e:
            release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'No availability', 'details': e.details},
                status=status.HTTP_409_CONFLICT,
            )
        except RoomTypeNotFoundError as e:
            release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'Not found', 'details': str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except serializers.ValidationError as e:
            release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
            
        except Exception as e:
            release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'Online booking failedddd', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        

        release_holder_locks(data['rooms'], holder_id)

        response_data = {
            'customer': CustomerSerializer(online_booking['customer']).data,
            'billing': BillingSerializerBase(online_booking['billing']).data,
            'bookings': BookingSerializer(online_booking['booking'], many=True).data,
        }

        if online_booking['boat']:
            response_data['guests'] = GuestListSerializer(online_booking['guests'], many=True).data
            response_data['boat_cost'] = float(online_booking['boat'].total_cost)

        return Response(response_data, status=status.HTTP_201_CREATED)


class ListBookings(generics.ListAPIView):
    serializer_class = BookingSerializer
    pagination_class = BookingPagination
    permission_classes = [IsReceptionistOrAdmin]

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


class BookingDetail(APIView):
    permission_classes = [IsReceptionistOrAdmin]

    def _get_booking(self, pk):
        return  get_object_or_404(
            Booking.objects.select_related('customer_bill__customer', 'room_type', 'room'),
            pk=pk
        )

    @extend_schema(
        tags=['Bookings'],
        description='Get a single booking by ID.',
    )
    def get(self, _request, pk):
        booking = self._get_booking(pk)
        return Response(BookingSerializer(booking).data)

    @extend_schema(
        tags=['Bookings'],
        description='Edit a booking. Re-checks availability when dates or room type change.',
        request=BookingSerializer,
    )
    def patch(self, request, pk):
        booking = self._get_booking(pk)
        serializer = BookingSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            booking = update_booking(booking=booking, data=serializer.validated_data)
        except RoomTypeNotFoundError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except RoomUnavailableError as exc:
            return Response({'error': 'No availability', 'details': exc.details}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(
            BookingSerializer(booking).data,
            status=status.HTTP_200_OK,
        )


class ApproveBooking(APIView):
    permission_classes = [IsReceptionistOrAdmin]

    @extend_schema(
        tags=['Bookings'],
        description='Approve a PENDING booking with a specific room.',
    )
    def post(self, request, pk):
        booking = get_object_or_404(
            Booking.objects.select_related('customer_bill__customer', 'room_type'),
            pk=pk
        )

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
    permission_classes = [IsReceptionistOrAdmin]

    @extend_schema(
        tags=['Bookings'],
        description='Cancel a PENDING or APPROVED booking.',
    )
    def post(self, _request, pk):
        booking = get_object_or_404(
            Booking.objects.select_related('customer_bill__customer', 'room_type'),
            pk=pk
        )

        try:
            booking = cancel_booking(booking)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)


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
        serializer = SingleLockRoomTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data

        turnstile_token = data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )

        try: 
            lock = lock_room_type(
                room_type_id=data['room_type_id'],
                check_in=data['check_in'],
                check_out=data['check_out'],
                holder_id=request.data.get('holder_id'),

            )
        except RoomTypeNotFoundError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except RedisUnavailable:
            return Response({'error': "Lock Service Unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not lock.held:
            return Response({
                'held': False,
                'available': lock.available,
                'message': lock.message
            })
        return Response({
            'held': True,
            'holder_id': lock.holder_id,
            'expires_in': lock.expires_in,
            'room_type': lock.room_type_name,
            'check_in': data['check_in'],
            'check_out': data['check_out'],
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
        request=BulkLockRoomTypeSerializer
    )
    def post(self, request):
        serializer = BulkLockRoomTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        turnstile_token = data.get('turnstile_token')
        remoteip = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        validation_result = validate_turnstile(turnstile_token, remoteip)
        if not validation_result.get('success'):
            return Response(
                {'error': 'validation failed', 'details': validation_result.get('error-codes', [])},
                status=status.HTTP_403_FORBIDDEN,
            )
        rooms = data['rooms']

        try:
            bulk_lock = bulk_lock_room_type(rooms)
        except RoomTypeNotFoundError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except RedisUnavailable:
            return Response({'error': "Lock Service Unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


        if not bulk_lock.get('all_held'):
            return Response({
                'held': False,
                'failures': bulk_lock.get('failures'),
                'message': 'Some room types are fully booked for the requested dates.',
            })

        return Response({
            'held': True,
            'holder_id': bulk_lock.get('holder_id'),
            'expires_in': 600,
            'rooms': rooms,
        })

class BulkReleaseRoomType(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Bookings'],
        description='Release room type locks in bulk',
        request=BulkLockRoomTypeSerializer  
    )
    def post(self, request):
        serializers = BulkLockRoomTypeSerializer(data=request.data)
        serializers.is_valid(raise_exception=True)
        data = serializers.validated_data

        rooms = data.get('rooms', [])
        holder_id = data.get('holder_id')

        if rooms and holder_id:
            print("YEAH")
            release_holder_locks(rooms=rooms, holder_id=holder_id)

        return Response({'released': True}, status=status.HTTP_200_OK)


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
        serializer = SingleLockRoomTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            released = release_room_type_lock(
                room_type_id=data['room_type_id'], check_in=data['check_in'],
                check_out=data['check_out'], holder_id=data['holder_id']
            )
        except Exception:
            released = False

        return Response({'released': released})
