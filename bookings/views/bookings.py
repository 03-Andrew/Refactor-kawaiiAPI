import requests
from django.db import transaction
import os
from dotenv import load_dotenv

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from bookings.serializers import (
    BookingSerializer,
    DayTourRequestSerializer,
    OnlineBookingRequestSerializer,
    OnsiteBookingRequestSerializer,
)
from bookings.services.availability import get_room_type_available
from bookings.services.lock import (
    acquire_room_type_lock, release_room_type_lock,
)
from transactions.models import BillingStatus, GuestStatus, ActivitiesAvailed, AmenitiesAvailed, GuestList
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    BillingSerializerBase, CustomerSerializer, GuestListSerializer,
)
from ..mixins import BillingCreationMixin, BookingCreateMixin
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
            guests = self._create_guest_list(billing, data.get('guest_list', []))
            amenities_added = self._create_amenities(billing, data.get('selected_amenities', []))
            activities_added = self._create_activities(billing, data.get('selected_activities', []))

        return Response({
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'amenities': amenities_added,
            'activities': activities_added,
            'guests': guests,
        }, status=status.HTTP_201_CREATED)


    def _create_guest_list(self, billing, guest_list):
        validated = []
        for name in guest_list:
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

    def _create_amenities(self, billing, amenities):
        if not amenities:
            return []

        validated = []
        for item in amenities:
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
        
    def _create_activities(self, billing, activities):
        if not activities:
            return []

        validated = []
        for item in activities:
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
        except serializers.ValidationError as e:
            self._release_holder_locks(data['rooms'], holder_id)
            return Response(
                {'error': 'Validation failed', 'details': e.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
                os.environ.get('PAYMENT_LINK_URL'),
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
    def get(self, request, pk):
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


class LockRoomType(APIView):
    """Acquire a 10-minute lock on a room-type count for a date range.

    Called when user selects a room type on the booking form.
    Lock expires after 10 minutes if not consumed by CreateOnlineBooking."""

    @extend_schema(
        tags=['Bookings'],
        description='Acquire a 10-minute lock on a room-type for a date range.',
    )
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

        available, detail = get_room_type_available(room_type_id, check_in, check_out)
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

class ReleaseRoomType(APIView):
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
