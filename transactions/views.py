from django.shortcuts import render
from django.db.models import F, Sum, Q, Exists, OuterRef

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList, FoodBill
from .serializers import BillingSerializer, CustomerSerializer, PaymentSerializer, BillingSerialzerBase, PendingBookings, BillingGuestList, GuestListSerializer, GuestListSerializerAll, BillingDetailSerializer

from receptionist.serializers import FoodBillSerializer
from bookings.serializers import BookingSerializer

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
    
class GuestListView(generics.ListCreateAPIView):
    queryset = GuestList.objects.all()
    serializer_class = GuestListSerializerAll

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
    
class CreateNewCustomerBilling(generics.CreateAPIView):
    pass    


class T(generics.RetrieveAPIView):
    pass