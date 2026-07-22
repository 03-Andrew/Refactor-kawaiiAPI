from django.http import JsonResponse
from django.views import View
from django.db.models import Q, F
from django.core.mail import send_mail
from django.conf import settings

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
from bookings.models import Booking,Room,BookingStatus
from transactions.models import Amenities, AmenitiesAvailed, Activity,ActivitiesAvailed,Payment, Billing

# Serializers
from transactions.serializers import ActivitiesSerializer, ActivitiesAvailedSerializer, AmenitiesSerializer, AmenitiesAvailedSerializer, BillingSerializerBase
from .serializers import RoomStatusListSerializer, RoomBookingListSerializer,BookingsListSerializer, AmenitiesAvailedListSerializer, ActivitiesAvailedListSerializer, PaymentSerializer
from bookings.serializers import BookingsAllSerializer
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
    serializer_class = BookingsAllSerializer
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

class ActivitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ActivitiesAvailedSerializer
    primary_key = 'pk'
    queryset = ActivitiesAvailed.objects.all()

class AddAmenitiesAndActivitiesAvailed(APIView):
     def get(self, request, format=None):
        return Response({"message": "Use POST to submit amenities and activities."}, status=200)
    
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
        
class UpdatePendingBookings(APIView):
    def patch(self, request, *args, **kwargs):
        updated_rooms = request.data.get('booking', [])
        updated_billing = request.data.get('billing', None)
        print(updated_rooms)
        print(updated_billing['status'])

        # Check if billing status is cancelled
        if updated_billing:
            billing = self.get_billing(updated_billing['id'])
            print(billing)
            if isinstance(billing, Response):
                return billing

            if updated_billing['status'] == Billing.BillingStatus.CANCELLED:
                print("cancelled")
                self.cancel_bookings_and_billing(billing, updated_rooms)
                return Response({"detail": "Billing and bookings have been cancelled."}, status=status.HTTP_200_OK)

        response_data = self.update_bookings(updated_rooms)
        if isinstance(response_data, Response):
            return response_data

        billing_response = self.update_billing(updated_billing)
        if isinstance(billing_response, Response):
            return billing_response

        billing_id = billing_response.instance.id
        self.send_email(billing_id, response_data[-1]['id'])

        return Response({"updated_rooms": response_data, 'billing': billing_response.data}, status=status.HTTP_200_OK)

    def update_bookings(self, updated_rooms):
        response_data = []
        for data in updated_rooms:
            booking_id = data.get('id')

            booking = self.get_booking(booking_id)
            if isinstance(booking, Response):
                return booking

            serializer = BookingsAllSerializer(booking, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                response_data.append(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return response_data

    def update_billing(self, updated_billing):
        if updated_billing:
            billing = self.get_billing(updated_billing['id'])
            if isinstance(billing, Response):
                return billing

            billing_serializer = BillingSerializerBase(billing, data=updated_billing, partial=True)
            if billing_serializer.is_valid():
                billing_serializer.save()
                return billing_serializer
            else:
                return Response(billing_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return None

    def get_booking(self, booking_id):
        try:
            return Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({"detail": f"Booking {booking_id} does not exist."}, status=status.HTTP_404_NOT_FOUND)

    def get_billing(self, billing_id):
        try:
            return Billing.objects.get(id=billing_id)
        except Billing.DoesNotExist:
            return Response({"detail": "Billing does not exist"}, status=status.HTTP_404_NOT_FOUND)

    def cancel_bookings_and_billing(self, billing_instance, bookings_data):
        # Update billing status to cancelled
        billing_instance.status = Billing.BillingStatus.CANCELLED
        billing_instance.save()

        # Update each booking status to cancelled
        for booking_data in bookings_data:
            booking = self.get_booking(booking_data['id'])
            if isinstance(booking, Booking):
                booking.status = BookingStatus.objects.get(status='cancelled')
                # print(1, booking)
                booking.save()

    def send_email(self, billing_id, booking_id):
        subject = f'Kawaii Resort: Booking Confirmed #{billing_id}'
        message = ''

        try:
            response = requests.get(f'https://seal-app-nvafi.ondigitalocean.app/api/billing-details/{billing_id}/')
            response.raise_for_status()
            booking_data = response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching booking details: {str(e)}")

        try:
            response = requests.get(f'https://seal-app-nvafi.ondigitalocean.app/api/confirmed-bookings/?id={booking_id}')
            response.raise_for_status() 
            booking_data2 = response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching confirmed bookings: {str(e)}")
            return  # Exit if there is an error fetching bookings

        else:
            customer = booking_data.get("customer", {})
            
            if booking_data2['count'] > 0:
                booking_info = booking_data2['results'][0]
                customer_name = booking_info.get("customer_name", "None")
                last_name = customer_name.split()[-1]  # Get the last name
                room_type = booking_info.get("room_type", "None")
                room_number = booking_info.get("room", "None")
                check_in = booking_info.get("check_in", "None")
                check_out = booking_info.get("check_out", "None")
                availed_boat_transfer = booking_info.get("availed_boat_transfer", "None")

                # Convert time to AM/PM format
                if availed_boat_transfer != "None":
                    availed_boat_transfer_time = datetime.strptime(availed_boat_transfer, "%H:%M:%S").strftime("%I:%M %p")
                else:
                    availed_boat_transfer_time = "None"

                # Intro
                message += f"Dear {last_name},\n\n"
                message += "Your booking has been confirmed. Below are your booking details:\n\n"
                message += f"Booking ID: {booking_id}\n"
                message += f"Room Type: {room_type}\n"
                message += f"Room Number: {room_number}\n"
                message += f"Check-in: {check_in}\n"
                message += f"Check-out: {check_out}\n"
                message += f"Boat Schedule: {availed_boat_transfer_time}\n\n"

                # Reminder
                message += "Please remember to bring a valid ID and arrive 15 minutes early before the scheduled boat time.\n\n"
                # Outro
                message += "Thank you for booking with us!\n"
            else:
                message += "No confirmed bookings found.\n\n"

         # recipient email address
        recipient_list = [customer.get('email', '')]

        # Send the email
        try:
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER, 
                recipient_list,
                fail_silently=False,
            )
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
        
class GetPayments(generics.ListCreateAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self): 
        queryset = Payment.objects.all()
        mop = self.request.GET.get('mop')
        customer = self.request.GET.get('customer')
        sort = self.request.GET.get('sort') 

        # Filter
        if mop:
            mop_list = mop.split(',') 
            queryset = queryset.filter(mop__mode__in=[mode.strip() for mode in mop_list])

        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer) | 
                Q(customer_bill__customer__last_name__icontains=customer)
            )

        # Sorting
        if sort:
            if sort == 'ascdate':
                queryset = queryset.order_by('date') 
            elif sort == 'descdate':
                queryset = queryset.order_by('-date')

        return queryset
    
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
