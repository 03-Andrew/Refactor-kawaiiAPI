from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from bookings.models import Booking,Room
from transactions.models import Amenities, AmenitiesAvailed, Activity,ActivitiesAvailed,Payment
from .serializers import BookingsSerializer,RoomStatusListSerializer, RoomBookingListSerializer, RoomStatusSerializer,BookingsListSerializer, AmenitiesSerializer,AmenitiesAvailedSerializer, AmenitiesAvailedListSerializer, ActivitiesSerializer,ActivitiesAvailedSerializer, ActivitiesAvailedListSerializer
from rest_framework import generics
from django.db.models import Count, Q, F, Subquery, OuterRef
from datetime import date
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.pagination import PageNumberPagination


# Create your views here.

class BookingPagination(PageNumberPagination):
    page_size = 10  # You can set a default page size
    page_size_query_param = 'page_size'  # Allows dynamic page sizing by passing this in query params


def get_bookingqueryset(request):
    queryset = Booking.objects.all()
    customer_name = request.GET.get('customer')  
    sort_param = request.GET.get('sort')  

    # Filter by customer name
    if customer_name:
        queryset = queryset.filter(
            Q(transaction__customer__first_name__icontains=customer_name) | 
            Q(transaction__customer__last_name__icontains=customer_name)
        )

    # Sort bookings
    # Sorts by checkin date
    if sort_param == "checkin-asc":
        queryset = queryset.order_by('check_in')
    elif sort_param == "checkin-desc":
        queryset = queryset.order_by('-check_in')

    # Sorts by checkout date
    if sort_param == "checkout-asc":
        queryset = queryset.order_by('check_out')
    elif sort_param == "checkout-desc":
        queryset = queryset.order_by('-check_out')

    # Sorts by customer name
    elif sort_param == "name-asc":
        queryset = queryset.order_by('transaction__customer__first_name', 'transaction__customer__last_name')
    elif sort_param == "name-desc":
        queryset = queryset.order_by('-transaction__customer__first_name', '-transaction__customer__last_name')

    # Sorts by id
    if sort_param == "id-asc":
        queryset = queryset.order_by('id')
    elif sort_param == "id-desc":
        queryset = queryset.order_by('-id')

    # Sort by downpayment (STILL BROKEN IDK HOOOW)
    if sort_param == "dp-asc":
        queryset = queryset.annotate(downpayment=F('transaction__payment__payment_amount')).order_by('downpayment')
    elif sort_param == "dp-desc":
        queryset = queryset.annotate(downpayment=F('transaction__payment__payment_amount')).order_by('-downpayment')

    return queryset

def get_roombookingqueryset(request):
    queryset = Room.objects.all()
    customer_name = request.GET.get('customer')
    sort_param = request.GET.get('sort') 

    # Filter by customer name
    if customer_name:
        queryset = queryset.filter(
            Q(booking__transaction__customer__first_name__icontains=customer_name) | 
            Q(booking__transaction__customer__last_name__icontains=customer_name)
        )

    # Sort by customer name 
    if sort_param == "name-asc":
        queryset = queryset.annotate(
            first_name=F('booking__transaction__customer__first_name'),
            last_name=F('booking__transaction__customer__last_name')
        ).order_by('first_name', 'last_name')
    elif sort_param == "name-desc":
        queryset = queryset.annotate(
            first_name=F('booking__transaction__customer__first_name'),
            last_name=F('booking__transaction__customer__last_name')
        ).order_by('-first_name', '-last_name')

    # Sort by room type
    elif sort_param == "type-asc":
        queryset = queryset.order_by('type')
    elif sort_param == "type-desc":
        queryset = queryset.order_by('-type')

    # Sort by room number 
    if sort_param == "number-asc":
        queryset = queryset.order_by('id')
    elif sort_param == "number-desc":
        queryset = queryset.order_by('-id')

    # Sorts by checkin date
    if sort_param == "checkin-asc":
        queryset = queryset.annotate(check_in=F('booking__check_in')).order_by('check_in')
    elif sort_param == "checkin-desc":
        queryset = queryset.annotate(check_in=F('booking__check_in')).order_by('-check_in')

    # Sorts by checkout date
    if sort_param == "checkout-asc":
        queryset = queryset.annotate(check_out=F('booking__check_out')).order_by('check_out')
    elif sort_param == "checkout-desc":
        queryset = queryset.annotate(check_out=F('booking__check_out')).order_by('-check_out')

    return queryset


@api_view(['GET'])
def room_list_status(request):
    rooms = Room.objects.all()
    serializer = RoomStatusListSerializer(rooms, many=True)
    return Response(serializer.data)

class RoomDetailStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomStatusSerializer
    primary_key = 'pk'
    queryset = Room.objects.all()

@api_view(['GET'])
def room_booking_list(request):
    queryset = get_roombookingqueryset(request)
    pagination = LimitOffsetPagination()
    paginated_queryset = pagination.paginate_queryset(queryset, request)
    serializer = RoomBookingListSerializer(paginated_queryset, many=True)
    return pagination.get_paginated_response(serializer.data)




@api_view(['GET'])
def booking_list_pending(request):
    queryset = get_bookingqueryset(request).filter(status='1')  # Filters booking (pending only)
    pagination = LimitOffsetPagination()
    paginated_queryset = pagination.paginate_queryset(queryset, request)
    serializer = BookingsListSerializer(paginated_queryset, many=True)
    return pagination.get_paginated_response(serializer.data)

@api_view(['GET'])
def booking_list_approved(request):
    queryset = get_bookingqueryset(request).filter(status='2')  # Filters booking (approved only)
    pagination = LimitOffsetPagination()
    paginated_queryset = pagination.paginate_queryset(queryset, request)
    serializer = BookingsListSerializer(paginated_queryset, many=True)
    return pagination.get_paginated_response(serializer.data)

class BookingDetailPending(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookingsSerializer
    primary_key = 'pk'
    queryset = Booking.objects.filter(status='1')  # Filters booking (pending only)

    def get_object(self):
        return generics.get_object_or_404(self.queryset, **{self.primary_key: self.kwargs['pk']})

@api_view(['GET'])
def amenities_list(request):
    amenities = Amenities.objects.all()
    serializer = AmenitiesSerializer(amenities, many=True)
    return Response(serializer.data)

class AmenitiesListAvailed(generics.ListCreateAPIView):
    queryset = AmenitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AmenitiesAvailedSerializer
        return AmenitiesAvailedListSerializer

class AmenitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AmenitiesAvailedSerializer
    primary_key = 'pk'
    queryset = AmenitiesAvailed.objects.all()


@api_view(['GET'])
def activities_list(request):
    amenities = Activity.objects.all()
    serializer = ActivitiesSerializer(amenities, many=True)
    return Response(serializer.data)

class ActivitiesListAvailed(generics.ListCreateAPIView):
    queryset = ActivitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitiesAvailedSerializer
        return ActivitiesAvailedListSerializer

class ActivitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ActivitiesAvailedSerializer
    primary_key = 'pk'
    queryset = ActivitiesAvailed.objects.all()
    
    

    