from django.shortcuts import render
from django.db.models import F, Sum, Q, Exists, OuterRef
from datetime import date, timedelta, datetime
from calendar import monthrange

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from django.db.models.functions import ExtractMonth

from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList, FoodBill, GuestStatus, Food, AdditonalPayment
from .serializers import BillingSerializer, CustomerSerializer, PaymentSerializer, BillingSerialzerBase, PendingBookings, BillingGuestList, GuestListSerializer, GuestListSerializerAll, BillingDetailSerializer, ConfirmedBooking, GuestStatusSerializer, FoodListSerializer

from receptionist.serializers import FoodBillSerializer, AdditionalPaymentSerializer
from bookings.serializers import BookingSerializer
from bookings.models import Booking

from rest_framework import status


# 1. List View - for listing all Billings
class BillingList(generics.ListAPIView):
    serializer_class = BillingSerializer

    def get_queryset(self):
        name = self.request.GET.get("name")
        queryset =  Billing.objects.all()

        if name:
            queryset = queryset.filter(Q(customer__first_name__icontains = name) |
                            Q(customer__last_name__icontains = name))
             
        return queryset

# 2. Create View - for creating a new Billing
class BillingCreate(generics.ListCreateAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerialzerBase
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        # Add any custom logic for creation if necessary
        serializer.save()

# 3. Update View - for editing an existing Billing
class BillingUpdate(generics.RetrieveUpdateDestroyAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerialzerBase
    lookup_field = 'pk' 


class CustomerListCreate(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class PaymentListCreate(generics.ListCreateAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

class ListBillingBooking(generics.ListAPIView):
    serializer_class = PendingBookings
    def get_queryset(self):
        queryset = Billing.objects.filter(Q(bookings__isnull=False) & Q(bookings__status__exact=1)).distinct()

        return queryset

class ListConfirmedBooking(generics.ListAPIView):
    serializer_class = ConfirmedBooking
    def get_queryset(self):
        booking_id = self.request.GET.get('id')
        check_in = self.request.GET.get('check_in')
        queryset = Booking.objects.filter(status=2).order_by("-check_out")

        if check_in:
            queryset = queryset.filter(check_in=check_in)

        if booking_id:
            queryset = queryset.filter(id=booking_id)
        
        return queryset
    

class EditBooking(generics.RetrieveUpdateAPIView):
    serializer_class = ConfirmedBooking
    lookup_field = 'pk'
    queryset = Booking.objects.all()
    

    



    
class GuestListView(generics.ListCreateAPIView):
    # queryset = GuestList.objects.all()
    serializer_class = GuestListSerializerAll
    def get_queryset(self):
        queryset = GuestList.objects.filter(Q(customer_bill__status__status="processing") | Q(customer_bill__status__status="confirmed"))
        return queryset

class UpdateGuestListStatus(APIView):
    def get(self, request, format=None):
        return Response({"message": "Use POST to submit amenities and activities."}, status=200)

    def patch(self, request, *args, **kwargs):
        newStatus = request.data.get('newStatus', [])
        response_data = []
        for data in newStatus:
            print(data)
            guest_id = data.get('id')
            try:
                guest = GuestList.objects.get(id=guest_id)
                print(guest.guest)
            except GuestList.DoesNotExist:
                return Response({"detail": f"Guest {guest_id} does not exist."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GuestListSerializer(guest, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                response_data.append(serializer.data)  # Append each updated guest's data to response_data
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({"newStatus": response_data}, status=status.HTTP_200_OK)



class GuestListPerBilling(generics.RetrieveUpdateDestroyAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingGuestList
    lookup_field = 'pk'

class AddGuest(generics.ListCreateAPIView):
    queryset = GuestList.objects.all()
    serializer_class = GuestListSerializerAll
    
    
class EditGuestListStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer
    queryset = GuestList.objects.all()
    lookup_field = 'pk'

class ActiveBookings(generics.ListCreateAPIView):
    serializer_class = BillingSerializer
    
    def get_queryset(self):
        return Billing.objects.filter(status=1)
    
class GetGuestStatus(generics.ListAPIView):
    serializer_class = GuestStatusSerializer
    queryset = GuestStatus.objects.all()

class BillingDetails(generics.RetrieveAPIView):
    serializer_class = BillingDetailSerializer
    queryset = Billing.objects.all()
    lookup_field = 'pk'


class AddFoodBill(generics.ListCreateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        serializer.save()
    
class ModifyFoodBill(generics.RetrieveUpdateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    lookup_field = 'pk'

class AddFoodList(generics.ListCreateAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()

class ModifyFoodList(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()
    lookup_field = 'pk'

class CreateAdditionalPayments(generics.ListCreateAPIView):
    serializer_class = AdditionalPaymentSerializer
    queryset = AdditonalPayment.objects.all()


