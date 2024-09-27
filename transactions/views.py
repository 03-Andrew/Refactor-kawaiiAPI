from django.shortcuts import render
from django.db.models import F, Sum, Q, Exists, OuterRef

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList
from .serializers import BillingSerializer, CustomerSerializer, PaymentSerializer, BillingSerialzerBase, ApproveBookings, BillingGuestList, GuestListSerializer

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
    serializer_class = ApproveBookings
    def get_queryset(self):
        queryset = Billing.objects.all()

        return queryset
    
class GuestList(generics.ListCreateAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingGuestList

class EditGuestListStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer  # Use the correct serializer for GuestList

    def get_queryset(self):
        Billing_pk = self.request.GET.get("pk")
        guest_pk = self.request.GET.get("pk2")

        # Fetching the GuestList item related to the specified Billing and guest
        queryset = GuestList.objects.filter(
            Q(Billing_id=Billing_pk) & Q(id=guest_pk)
        )

        return queryset