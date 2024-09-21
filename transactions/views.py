from django.shortcuts import render

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import Transaction, Customer, Payment
from .serializers import TransactionSerializer, CustomerSerializer, PaymentSerializer, TransactionSerialzerBase

# 1. List View - for listing all transactions
class TransactionList(generics.ListAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer

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
    lookup_field = 'pk'  # Assuming you're using the primary key to look up objects


class CustomerListCreate(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class PaymentListCreate(generics.ListCreateAPIView):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

