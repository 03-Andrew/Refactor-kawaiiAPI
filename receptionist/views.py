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

from django.db import transaction

from rest_framework import status


from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator


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
            Q(billing__customer__first_name__icontains=customer_name) | 
            Q(billing__customer__last_name__icontains=customer_name)
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
        queryset = queryset.order_by('billing__customer__first_name', 'billing__customer__last_name')
    elif sort_param == "name-desc":
        queryset = queryset.order_by('-billing__customer__first_name', '-billing__customer__last_name')

    # Sorts by id
    if sort_param == "id-asc":
        queryset = queryset.order_by('id')
    elif sort_param == "id-desc":
        queryset = queryset.order_by('-id')

    # Sort by downpayment (STILL BROKEN IDK HOOOW)
    if sort_param == "dp-asc":
        queryset = queryset.annotate(downpayment=F('billing__payment__payment_amount')).order_by('downpayment')
    elif sort_param == "dp-desc":
        queryset = queryset.annotate(downpayment=F('billing__payment__payment_amount')).order_by('-downpayment')

    return queryset

def get_roombookingqueryset(request):
    queryset = Room.objects.all()
    customer_name = request.GET.get('customer')
    sort_param = request.GET.get('sort') 

    # Filter by customer name
    if customer_name:
        queryset = queryset.filter(
            Q(booking__billing__customer__first_name__icontains=customer_name) | 
            Q(booking__billing__customer__last_name__icontains=customer_name)
        )

    # Sort by customer name 
    if sort_param == "name-asc":
        queryset = queryset.annotate(
            first_name=F('booking__billing__customer__first_name'),
            last_name=F('booking__billing__customer__last_name')
        ).order_by('first_name', 'last_name')
    elif sort_param == "name-desc":
        queryset = queryset.annotate(
            first_name=F('booking__billing__customer__first_name'),
            last_name=F('booking__billing__customer__last_name')
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

def get_amenitiesavailedqueryset(request):
    queryset = AmenitiesAvailed.objects.all()
    customer_name = request.GET.get('customer')

    if customer_name is not None:
        # Filter by customer name
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) | 
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )
    else:
        queryset = AmenitiesAvailed.objects.all()

    return queryset

def get_activitiesavailedqueryset(request):
    queryset = ActivitiesAvailed.objects.all()
    customer_name = request.GET.get('customer')

    # Filter by customer name
    if customer_name is not None:
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) | 
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )

    else:
        queryset = ActivitiesAvailed.objects.all()

    return queryset

class RoomListStatus(generics.ListAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomStatusListSerializer

class RoomDetailStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomStatusSerializer
    primary_key = 'pk'
    queryset = Room.objects.all()

class RoomBookingList(generics.ListAPIView):
    pagination_class = LimitOffsetPagination
    serializer_class = RoomBookingListSerializer
    def get_queryset(self):
        return get_roombookingqueryset(self.request)

class BookingListPending(generics.ListAPIView):
    pagination_class = LimitOffsetPagination
    serializer_class = BookingsListSerializer

    def get_queryset(self):
        return get_bookingqueryset(self.request).filter(status='1')  # Filters booking (pending only)


class BookingListApproved(generics.ListAPIView):
    pagination_class = LimitOffsetPagination
    serializer_class = BookingsListSerializer

    def get_queryset(self):
        return get_bookingqueryset(self.request).filter(status='2')  # Filters booking (approved only)

class BookingDetailPending(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookingsSerializer
    primary_key = 'pk'
    queryset = Booking.objects.filter(status='1')  # Filters booking (pending only)

    def get_object(self):
        return generics.get_object_or_404(self.queryset, **{self.primary_key: self.kwargs['pk']})

class AmenitiesList(generics.ListCreateAPIView):
    queryset = Amenities.objects.all()
    serializer_class = AmenitiesSerializer

class AmenitiesListAvailed(generics.ListCreateAPIView):
    queryset = AmenitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AmenitiesAvailedSerializer
        return AmenitiesAvailedListSerializer
    
    # @method_decorator(csrf_protect)
    def create(self, request, *args, **kwargs):
        # Check if the request is coming from the built-in API form
        if isinstance(request.data, dict):  # Single amenity
            amenities_data = [request.data]
        elif isinstance(request.data, list):  # Multiple amenities
            amenities_data = request.data
        else:
            return Response({'error': 'Expected a list of amenities.'}, status=status.HTTP_400_BAD_REQUEST)

        created_amenities = []
        
        # Wrap in a transaction to ensure all-or-nothing behavior
        with transaction.atomic():
            for amenity_data in amenities_data:
                serializer = self.get_serializer(data=amenity_data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                created_amenities.append(serializer.data)

        return Response(created_amenities, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return get_amenitiesavailedqueryset(self.request)

class AmenitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AmenitiesAvailedSerializer
    primary_key = 'pk'
    queryset = AmenitiesAvailed.objects.all()

class ActivitiesList(generics.ListAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitiesSerializer

class ActivitiesListAvailed(generics.ListCreateAPIView):
    queryset = ActivitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitiesAvailedSerializer
        return ActivitiesAvailedListSerializer

    def get_queryset(self):
        return get_activitiesavailedqueryset(self.request)

class ActivitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ActivitiesAvailedSerializer
    primary_key = 'pk'
    queryset = ActivitiesAvailed.objects.all()
    
    

    