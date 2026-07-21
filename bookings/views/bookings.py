from datetime import datetime

import requests
from django.db import transaction
from django.db.models import ExpressionWrapper, F, IntegerField, Q

from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from bookings.serializers import BookingSerializer, BookingSerializer3, CurrentRoomBookings
from transactions.serializers import (
    ActivitiesAvailedSerializer, AmenitiesAvailedSerializer,
    BillingSerializerBase, CustomerSerializer, GuestListSerializer,
)


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
        rBooking['status'] = 2
        rBooking['room'] = int(rBooking['roomNumber'])
        rBooking['room_type'] = int(rBooking['room_type'])
        rBooking['children_count'] = int(rBooking['children_count'])
        rBooking['adult_count'] = int(rBooking['adult_count'])


class CreateOnlineBooking(APIView):
    def post(self, request):
        customer_data = request.data.get('customer')
        bookings = request.data.get('rooms')
        boat = request.data.get('boat')
        payment_data = request.data.get('payment')

        with transaction.atomic():
            customer_serializer = CustomerSerializer(data=customer_data)
            if not customer_serializer.is_valid():
                return Response(customer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            customer = customer_serializer.save()

            billing_serializer = BillingSerializerBase(data={
                'customer': customer.id,
                'status': 3,
            })
            if not billing_serializer.is_valid():
                return Response(billing_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            billing = billing_serializer.save()

            created_bookings = []
            booking_ids = []
            for booking in bookings:
                booking['customer_bill'] = billing.id
                booking['room'] = ""
                booking['status'] = 1
                booking['total_cost'] = booking['price']
                booking_serializer = BookingSerializer3(data=booking)
                if booking_serializer.is_valid():
                    b = booking_serializer.save()
                    created_bookings.append(booking_serializer.data)
                    booking_ids.append(str(b.id))
                else:
                    raise Exception(booking_serializer.errors)

            tourist_added = []
            boat_ids = []
            if boat:
                for availed_boat in boat:
                    availed_boat['customer_bill'] = billing.id
                    availed_boat['amenity'] = 1
                    amenities_serializer = AmenitiesAvailedSerializer(data=availed_boat)
                    if not amenities_serializer.is_valid():
                        return Response(amenities_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                    saved = amenities_serializer.save()
                    boat_ids.append(saved.id)

                    for tourist in availed_boat['guests']:
                        tourist_serializer = GuestListSerializer(data={
                            'customer_bill': billing.id,
                            'guest': tourist,
                            'status': 2,
                        })
                        tourist_serializer.is_valid(raise_exception=True)
                        tourist_serializer.save()
                        tourist_added.append(tourist_serializer.data)

            payment_link_data = {
                'billing_id': str(billing.id),
                'payment_for': 'Down Payment',
                'payment_status': 'Down Payment',
                'content_type': 'booking',
                'object_id': ','.join(booking_ids),
                'amount': payment_data.get('amount', 0),
                'description': f"Booking for customer {customer.id}",
                'remarks': f"Booking for customer {customer.id}",
            }

            try:
                response = requests.post(
                    'https://seal-app-nvafi.ondigitalocean.app/api/payment-link/',
                    json=payment_link_data,
                )
                if response.status_code != 200:
                    return Response(
                        {"error": "Payment link creation failed", "details": response.json()},
                        status=response.status_code,
                    )
                payment_info = response.json()
            except requests.RequestException as e:
                return Response(
                    {"error": "Failed to send request to payment API", "details": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        data = {
            'customer': customer_serializer.data,
            'billing': billing_serializer.data,
            'bookings': created_bookings,
            'payment': payment_info,
        }
        if boat_ids:
            data['boat'] = boat_ids
            data['guests'] = tourist_added

        return Response(data, status=status.HTTP_201_CREATED)
