from django.shortcuts import render
from django.db.models import F, Sum, Q, Exists, OuterRef
from datetime import date, timedelta
from calendar import monthrange

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
    

class GetWeeklyReports(APIView):
     def get(self, request):
        month = int(request.query_params.get('month', 1))  
        year = int(request.query_params.get('year', 2024))
        week = int(request.query_params.get('week', 1))

        # Calculate the first day of the month
        first_day = date(year, month, 1)
        start_of_week = first_day + timedelta(days=(week - 1) * 7)
        days_in_month = monthrange(year, month)[1]

        start_of_week = min(start_of_week, date(year, month, days_in_month))

        end_of_week = start_of_week + timedelta(days=6)
        if end_of_week.month != month:
            end_of_week = date(year, month, days_in_month)

        earnings = (Payment.objects
                    .filter(date__range=[start_of_week, end_of_week])
                    .values('date')
                    .annotate(total_earnings=Sum('amount'))
                    .order_by('date'))

        return Response(earnings)
    