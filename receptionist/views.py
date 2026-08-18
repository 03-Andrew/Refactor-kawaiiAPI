from django.http import JsonResponse
from django.views import View
from django.db.models import Q, F
from django.core.mail import send_mail
from django.conf import settings

from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.pagination import PageNumberPagination
from rest_framework import status

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from datetime import datetime
import requests
import logging

# Auth Imports
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

# Models
from django.contrib.contenttypes.models import ContentType
from bookings.models import Booking,Room,BookingStatus
from transactions.models import Amenities, AmenitiesAvailed, Activity,ActivitiesAvailed,Payment, Billing, FoodBill

# Serializers
from transactions.serializers import ActivitiesSerializer, ActivitiesAvailedSerializer, AmenitiesSerializer, AmenitiesAvailedSerializer, BillingSerializerBase
from .serializers import RoomBookingListSerializer,BookingsListSerializer, AmenitiesAvailedListSerializer, ActivitiesAvailedListSerializer, PaymentSerializer
from bookings.serializers import BookingSerializer
# Create your views here.

from kawaiiAPI.permissions import IsAdmin, IsReceptionistOrAdmin, ReceptionistViewOnly

# ── Shared helpers ──────────────────────────────────────────────

MODEL_BY_CONTENT_TYPE = {
    'booking': Booking,
    'amenitiesavailed': AmenitiesAvailed,
    'activitiesavailed': ActivitiesAvailed,
    'foodbill': FoodBill,
}


def prefetch_paid_for(payments):
    """Batch-fetch all GenericForeignKey objects to avoid N+1 in get_paid_for.

    Attaches _cached_paid_for to each Payment instance so
    PaymentSerializer.get_paid_for() can skip the per-row GFK query.
    """
    buckets = {}
    for p in payments:
        if p.content_type_id and p.object_id:
            buckets.setdefault(p.content_type_id, []).append(p.object_id)

    if not buckets:
        return

    content_types = {
        ct.id: ct
        for ct in ContentType.objects.filter(id__in=buckets.keys())
    }

    cache = {}
    for ct_id, object_ids in buckets.items():
        ct = content_types[ct_id]
        model = MODEL_BY_CONTENT_TYPE.get(ct.model)
        if model is None:
            continue
        objects = model.objects.filter(id__in=object_ids)
        cache[(ct_id, ct.model)] = {obj.id: obj for obj in objects}

    for p in payments:
        if p.content_type_id and p.object_id:
            ct = content_types.get(p.content_type_id)
            if ct:
                bucket = cache.get((p.content_type_id, ct.model), {})
                p._cached_paid_for = bucket.get(p.object_id)
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
    queryset = AmenitiesAvailed.objects.select_related(
            'customer_bill__customer',
            'amenity',
        ).prefetch_related(
            'customer_bill__bookings__room_type',
            'customer_bill__payment',
            'customer_bill__food_bill',
            'customer_bill__amenities_availed__amenity',
            'customer_bill__activities_availed__activity',
            'customer_bill__additional_payment',
        )
    customer_name = request.GET.get('customer')

    if customer_name is not None:
        # Filter by customer name
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) | 
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )

    return queryset

def get_activitiesavailedqueryset(request):
    queryset = ActivitiesAvailed.objects.select_related(
        'customer_bill__customer',
        'activity',
    ).prefetch_related(
        'customer_bill__bookings__room_type',
        'customer_bill__payment',
        'customer_bill__food_bill',
        'customer_bill__amenities_availed__amenity',
        'customer_bill__activities_availed__activity',
        'customer_bill__additional_payment',
    )
    customer_name = request.GET.get('customer')

    if customer_name:
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) | 
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )


    return queryset


@extend_schema(tags=['Amenities'])
class AmenitiesList(generics.ListCreateAPIView):
    queryset = Amenities.objects.all()
    serializer_class = AmenitiesSerializer
    permission_classes = [ReceptionistViewOnly]

@extend_schema(tags=['Amenities'])
class AmenitiesListAvailed(generics.ListCreateAPIView):
    queryset = AmenitiesAvailed.objects.all()
    permission_classes = [IsReceptionistOrAdmin]
    
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

@extend_schema(tags=['Amenities'])
class AmenitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AmenitiesAvailedSerializer
    primary_key = 'pk'
    queryset = AmenitiesAvailed.objects.all()

@extend_schema(tags=['Activities'])
class ActivitiesList(generics.ListCreateAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitiesSerializer
    permission_classes = [ReceptionistViewOnly]

@extend_schema(tags=['Activities'])
class ActivitiesListAvailed(generics.ListCreateAPIView):
    queryset = ActivitiesAvailed.objects.all()
    permission_classes = [IsReceptionistOrAdmin]
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitiesAvailedSerializer
        return ActivitiesAvailedListSerializer
        
    def create(self, request, *args, **kwargs):
        # Check if the request is coming from the built-in API form
        if isinstance(request.data, dict):  # Single amenity
            activities_data = [request.data]
        elif isinstance(request.data, list):  # Multiple amenities
            activities_data = request.data
        else:
            return Response({'error': 'Expected a list of amenities.'}, status=status.HTTP_400_BAD_REQUEST)

        created_amenities = []
        
        # Wrap in a transaction to ensure all-or-nothing behavior
        with transaction.atomic():
            for amenity_data in activities_data:
                serializer = self.get_serializer(data=amenity_data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                created_amenities.append(serializer.data)

        return Response(created_amenities, status=status.HTTP_201_CREATED)


    def get_queryset(self):
        return get_activitiesavailedqueryset(self.request)

@extend_schema(tags=['Activities'])
class ActivitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ActivitiesAvailedSerializer
    primary_key = 'pk'
    queryset = ActivitiesAvailed.objects.all()
    permission_classes = [IsReceptionistOrAdmin]

@extend_schema(tags=['Amenities & Activities'])
class AddAmenitiesAndActivitiesAvailed(APIView):
    permission_classes = [IsReceptionistOrAdmin]
     
    def post(self, request, format=None):
        amenities_data = request.data.get('amenities', [])
        activities_data = request.data.get('activities', [])
        
        created_amenities = []
        created_activities = []

        # Wrap in a transaction to ensure all-or-nothing behavior
        with transaction.atomic():
            # Handle amenities if provided
            if amenities_data:
                if isinstance(amenities_data, dict):
                    amenities_data = [amenities_data]  # Single amenity
            
                for amenity_data in amenities_data:
                    amenity_serializer = AmenitiesAvailedSerializer(data=amenity_data)
                    amenity_serializer.is_valid(raise_exception=True)
                    amenity_serializer.save()
                    created_amenities.append(amenity_serializer.data)

            # Handle activities if provided
            if activities_data:
                if isinstance(activities_data, dict):
                    activities_data = [activities_data]  # Single activity
                
                for activity_data in activities_data:
                    activity_serializer = ActivitiesAvailedSerializer(data=activity_data)
                    activity_serializer.is_valid(raise_exception=True)
                    activity_serializer.save()
                    created_activities.append(activity_serializer.data)

        # Return combined response
        return Response({
            'created_amenities': created_amenities,
            'created_activities': created_activities
        }, status=status.HTTP_201_CREATED)

@extend_schema(tags=['Payments'])
class GetPayments(generics.ListCreateAPIView):
    permission_classes = [IsReceptionistOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        queryset = Payment.objects.select_related(
            'mop', 'status', 'customer_bill__customer'
        )
        mop = self.request.GET.get('mop')
        customer = self.request.GET.get('customer')
        sort = self.request.GET.get('sort')

        if mop:
            mop_list = mop.split(',')
            queryset = queryset.filter(mop__mode__in=[mode.strip() for mode in mop_list])

        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer) |
                Q(customer_bill__customer__last_name__icontains=customer)
            )

        if sort:
            if sort == 'ascdate':
                queryset = queryset.order_by('date')
            elif sort == 'descdate':
                queryset = queryset.order_by('-date')

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        payments = list(page) if page is not None else list(queryset)

        prefetch_paid_for(payments)

        serializer = self.get_serializer(payments, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
    
@extend_schema(tags=['WebSocket'], exclude=True)
class WebSocketTestView(View):
    def get(self, request, *args, **kwargs):
        # Get the channel layer
        channel_layer = get_channel_layer()

        # Send a test message to the 'receptionist' WebSocket group
        async_to_sync(channel_layer.group_send)(
            "receptionist",  # This is the group name
            {
                "type": "booking_paid",  # Custom message type defined in the consumer
                "message": "A customer has booked a stay",  # The actual message content
            }
        )

        return JsonResponse({"status": "Message sent to WebSocket group 'receptionist'"})
