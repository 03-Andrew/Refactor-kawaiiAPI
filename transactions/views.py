from django.shortcuts import render
from django.db.models import F, Sum, Q, Exists, OuterRef

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import Transaction, Customer, Payment, AmenitiesAvailed, GuestList
from .serializers import TransactionSerializer, CustomerSerializer, PaymentSerializer, TransactionSerialzerBase, ApproveBookings, TransactionGuestList, GuestListSerializer

from bookings.serializers import BookingSerializer

# 1. List View - for listing all transactions
class TransactionList(generics.ListAPIView):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        name = self.request.GET.get("name")
        queryset =  Transaction.objects.all()

        if name:
            queryset = queryset.filter(Q(customer__first_name__icontains = name) |
                            Q(customer__last_name__icontains = name))
             
        return queryset

# 2. Create View - for creating a new transaction
class TransactionCreate(generics.ListCreateAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerialzerBase
    def perform_create(self, serializer):
        # Add any custom logic for creation if necessary
        serializer.save()

# 3. Update View - for editing an existing transaction
class TransactionUpdate(generics.RetrieveUpdateDestroyAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerialzerBase
    lookup_field = 'pk' 


class CustomerListCreate(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class PaymentListCreate(generics.ListCreateAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

class ListTransactionBooking(generics.ListAPIView):
    serializer_class = ApproveBookings
    def get_queryset(self):
        queryset = Transaction.objects.all()

        return queryset
    
class GuestList(generics.ListCreateAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionGuestList

class EditGuestListStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer  # Use the correct serializer for GuestList

    def get_queryset(self):
        transaction_pk = self.request.GET.get("pk")
        guest_pk = self.request.GET.get("pk2")

        # Fetching the GuestList item related to the specified transaction and guest
        queryset = GuestList.objects.filter(
            Q(transaction_id=transaction_pk) & Q(id=guest_pk)
        )

        return queryset