from datetime import date, datetime

import requests
from django.db import transaction
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking, BookingStatus, RoomStatus, RoomType
from bookings.serializers import (
    BookingSerializer, BookingSerializer3, CurrentRoomBookings,
    OnlineBookingRequestSerializer,
)
from transactions.models import BillingStatus, GuestStatus
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    BillingSerializerBase, CustomerSerializer, GuestListSerializer,
)

ONLINE_BOOKING_EXAMPLE = {
    "customer": {
        "first_name": "Juan",
        "last_name": "Dela Cruz",
        "contact_number": "09123456789",
        "email": "juan@example.com",
    },
    "rooms": [
        {
            "room_type": 1,
            "check_in": "2026-08-01",
            "check_out": "2026-08-03",
            "adult_count": 2,
            "children_count": 1,
            "extra_guest": 0,
            "price": 5000.00,
            "number_of_guests": 3,
        },
    ],
    "boat": [
        {
            "head_count": 3,
            "time": "10:00",
            "guests": ["Juan Dela Cruz", "Maria Dela Cruz", "Baby Dela Cruz"],
        },
    ],
    "payment": {
        "amount": 2500.00,
    },
}


class RoomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 100


class BookingListCreate(generics.ListCreateAPIView):
    serializer_class = BookingSerializer

    def get_queryset(self):
        queryset = Booking.objects.annotate(
            total_guests=ExpressionWrapper(
                F('adult_count') + F('children_count'),
                output_field=IntegerField(),
            ),
        )
        customer = self.request.GET.get('customer')
        sort = self.request.GET.get('sort')
        status_filter = self.request.GET.get('status')

        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer)
                | Q(customer_bill__customer__last_name__icontains=customer),
            )

        if status_filter == 'a':
            queryset = queryset.filter(status__exact=2)
        elif status_filter == 'p':
            queryset = queryset.filter(status__exact=1)

        sort_map = {
            'asc': 'check_in',
            'desc': '-check_in',
            'asccheckout': 'check_out',
            'desccheckout': '-check_out',
            'ascroom': 'room',
            'descroom': '-room',
            'ascguest': 'total_guests',
            'descguest': '-total_guests',
            'asccost': 'total_cost',
            'desccost': '-total_cost',
        }
        if sort in sort_map:
            queryset = queryset.order_by(sort_map[sort])

        return queryset


class GetBookedRoomsNow(generics.ListAPIView):
    serializer_class = BookingSerializer

    def get_queryset(self):
        customer = self.request.GET.get('customer')
        sort = self.request.GET.get('sort')
        today = datetime.now().date()

        queryset = Booking.objects.filter(
            Q(status=2) & Q(check_in__lte=today) & Q(check_out__gte=today),
        )

        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer)
                | Q(customer_bill__customer__last_name__icontains=customer),
            )

        if sort == 'asccheckin':
            queryset = queryset.order_by('check_in')
        elif sort == 'desccheckin':
            queryset = queryset.order_by('-check_in')
        elif sort == 'asccheckout':
            queryset = queryset.order_by('check_out')
        elif sort == 'desccheckout':
            queryset = queryset.order_by('-check_out')

        return queryset


class CreateDayTourGuest(APIView):
    def post(self, request):
        customer_data = request.data.get('personalInfo')
        tourists_data = request.data.get('touristList')
        amenities_data = request.data.get('selectedAmenities')
        activities_data = request.data.get('selectedActivities')

        with transaction.atomic():
            customer_serializer = CustomerSerializer(data=customer_data)
            customer_serializer.is_valid(raise_exception=True)
            customer = customer_serializer.save()

            billing_serializer = BillingSerializerBase(
                data={'customer': customer.id, 'status': 1},
            )
            billing_serializer.is_valid(raise_exception=True)
            billing = billing_serializer.save()

            tourist_added = []
            for tourist in tourists_data:
                tourist_serializer = GuestListSerializer(data={
                    'customer_bill': billing.id,
                    'guest': tourist,
                    'status': 2,
                })
                tourist_serializer.is_valid(raise_exception=True)
                tourist_serializer.save()
                tourist_added.append(tourist_serializer.data)

            amenities_added = []
            for item in amenities_data:
                amenity_serializer = AmenitiesAvailedSerializer(data={
                    'amenity': item['id'],
                    'customer_bill': billing.id,
                    'head_count': item['hours'],
                })
                amenity_serializer.is_valid(raise_exception=True)
                amenity_serializer.save()
                amenities_added.append(amenity_serializer.data)

            activities_added = []
            for item in activities_data:
                activity_serializer = ActivitiesAvailedSerializer(data={
                    'activity': item['id'],
                    'customer_bill': billing.id,
                    'hours_availed': item['hours'],
                })
                activity_serializer.is_valid(raise_exception=True)
                activity_serializer.save()
                activities_added.append(activity_serializer.data)

        return Response({
            'customer': customer_serializer.data,
            'billing': billing_serializer.data,
            'amenities': amenities_added,
            'activities': activities_added,
        }, status=status.HTTP_201_CREATED)


class CreateStayInBooking(APIView):
    def post(self, request):
        customer_data = request.data.get('customer')
        billing_data = request.data.get('billing')
        booking_data = request.data.get('booking')

        with transaction.atomic():
            customer_serializer = CustomerSerializer(data=customer_data)
            if not customer_serializer.is_valid():
                return Response(customer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            customer = customer_serializer.save()

            billing_data['customer'] = customer.id
            billing_serializer = BillingSerializerBase(data=billing_data)
            if not billing_serializer.is_valid():
                return Response(billing_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            billing = billing_serializer.save()

            created_bookings = []
            for rBooking in booking_data:
                self._prepare_booking_data(rBooking, billing.id)
                booking_serializer = BookingSerializer(data=rBooking)
                if booking_serializer.is_valid():
                    booking_serializer.save()
                    created_bookings.append(booking_serializer.data)
                else:
                    raise Exception(booking_serializer.errors)

        return Response({
            'customer': customer_serializer.data,
            'billing': billing_serializer.data,
            'bookings': created_bookings,
        }, status=status.HTTP_201_CREATED)

    def _prepare_booking_data(self, rBooking, billing_id):
        rBooking['customer_bill'] = billing_id
        rBooking['check_in'], rBooking['check_out'] = [
            datetime.fromisoformat(d.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            for d in rBooking['dateRange']
        ]
        rBooking['status'] = GuestStatus.PENDING
        rBooking['room'] = int(rBooking['roomNumber'])
        rBooking['room_type'] = int(rBooking['room_type'])
        rBooking['children_count'] = int(rBooking['children_count'])
        rBooking['adult_count'] = int(rBooking['adult_count'])


class CreateOnlineBooking(APIView):
    @extend_schema(
        tags=['Bookings'],
        description='Create an online booking with customer info, room bookings, optional boat transfers, and a down-payment link.',
        request=OnlineBookingRequestSerializer,
        examples=[
            OpenApiExample(
                'Example booking',
                value=ONLINE_BOOKING_EXAMPLE,
                request_only=True,
            ),
        ],
        responses={
            201: {
                'description': 'Booking created. Returns customer, billing, bookings, and payment link.',
                'example': {
                    'customer': {'id': 1, 'first_name': 'Juan', 'last_name': 'Dela Cruz', 'contact_number': '09123456789', 'email': 'juan@example.com'},
                    'billing': {'id': 1, 'customer': 1, 'status': 'Pending'},
                    'bookings': [{'id': 1, 'room_type': 1, 'check_in': '2026-08-01', 'check_out': '2026-08-03'}],
                    'payment': {'payment_url': 'https://pay.example.com/link/abc123'},
                },
            },
        },
    )
    def post(self, request):
        serializer = OnlineBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        availability_error = self._check_availability(data['rooms'])
        if availability_error:
            return availability_error

        try:
            with transaction.atomic():
                customer = self._create_customer(data['customer'])
                billing = self._create_billing(customer)
                created_bookings = self._create_bookings(billing, data['rooms'])
                boat_ids, tourist_added = self._create_boat(billing, data.get('boat', []))
        except Exception as e:
            return Response(
                {'error': 'Online booking failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = {
            'customer': CustomerSerializer(customer).data,
            'billing': BillingSerializerBase(billing).data,
            'bookings': created_bookings,
        }
        if boat_ids:
            response_data['boat'] = boat_ids
            response_data['guests'] = tourist_added

        return Response(response_data, status=status.HTTP_201_CREATED)

    # ── helpers ────────────────────────────────────────────────

    def _create_customer(self, data):
        serializer = CustomerSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def _create_billing(self, customer):
        serializer = BillingSerializerBase(data={
            'customer': customer.id,
            'status': BillingStatus.PENDING,
        })
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def _create_bookings(self, billing, rooms):
        created = []
        for room in rooms:
            room['customer_bill'] = billing.id
            room['room'] = ''
            room['status'] = BookingStatus.PENDING
            room['total_cost'] = room['price']
            serializer = BookingSerializer3(data=room)
            if not serializer.is_valid():
                raise Exception(serializer.errors)
            serializer.save()
            created.append(serializer.data)
        return created

    def _check_availability(self, rooms):
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

            available = total - maintenance - booked
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
