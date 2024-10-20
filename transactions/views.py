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

from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList, FoodBill, GuestStatus
from .serializers import BillingSerializer, CustomerSerializer, PaymentSerializer, BillingSerialzerBase, PendingBookings, BillingGuestList, GuestListSerializer, GuestListSerializerAll, BillingDetailSerializer, ConfirmedBooking, GuestStatusSerializer

from receptionist.serializers import FoodBillSerializer
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
        
        queryset = Booking.objects.filter(status=2).order_by("-check_out")
        return queryset
    



    
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

class GetWeeklyReports(APIView):
    def get(self, request):
        # Retrieve parameters from the request
        month = int(request.query_params.get('month', 1))
        year = int(request.query_params.get('year', 2024))
        week = int(request.query_params.get('week', 1))

        # if week < 1:
        #     return Response({'error': 'Week number must be at least 1'}, status=400)

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
    

class GetMonthlyReports(APIView):
    def get(self, request):
        # Get the start_month and end_month from query parameters
        start_month = request.query_params.get('s')
        end_month = request.query_params.get('e')

        # If end_month is not provided, treat it as the same as start_month
        if not end_month:
            end_month = start_month
        
        # Parse the provided months (in the format 'YYYY-MM' like '2024-01')
        try:
            start_date = datetime.strptime(start_month, '%Y-%m')
            end_date = datetime.strptime(end_month, '%Y-%m')
        except ValueError:
            return Response({'error': 'Invalid month format. Use YYYY-MM format.'}, status=400)

        # Get the first day of the start month and the last day of the end month
        start_of_month = start_date.replace(day=1)
        end_of_month = end_date.replace(day=monthrange(end_date.year, end_date.month)[1])

        # Filter payments by date range
        payments = Payment.objects.filter(date__range=[start_of_month, end_of_month])
        
        # Group payments by week and total the earnings
        earnings_by_week = {}
        for payment in payments:
            week_number = payment.date.isocalendar()[1]  # Get the week number
            year_week_key = f"{payment.date.year}-W{week_number}"  # e.g., '2024-W01'
            
            if year_week_key not in earnings_by_week:
                earnings_by_week[year_week_key] = {
                    'range': {
                        'start_date': payment.date - timedelta(days=payment.date.weekday()),  # Monday of the week
                        'end_date': payment.date + timedelta(days=(6 - payment.date.weekday()))  # Sunday of the week
                    },
                    'payments': [],
                    'total': 0
                }
            
            earnings_by_week[year_week_key]['payments'].append({
                'customer_name': f'{payment.customer_bill.customer.last_name}, {payment.customer_bill.customer.first_name}' ,
                'payment_for': payment.paymentFor.name if payment.paymentFor else 'Unknown',
                'payment_type': payment.status.status if payment.status else 'Unknown',
                'mop': payment.mop.mode,
                'amount': float(payment.amount),
                'date': payment.date
            })
            
            earnings_by_week[year_week_key]['total'] += float(payment.amount)

        # Return the response
        return Response(earnings_by_week)
    

class GetTotalEarningsPerMonth(APIView):
    def get(self, request):
        year = request.query_params.get('year')


        try:
            year = int(year)
        except:
            return Response({'Error please enter a valid year'}, status=400)
        

        earnings_monthly = (Payment.objects
                            .filter(date__year=year)
                            .annotate(month=ExtractMonth('date'))
                            .values('month')
                            .annotate(total=Sum('amount'))
                            .order_by('month'))
        
        monthly_earnings = {
            'months': {},
            'total_yr': 0
        }

        for earnings in earnings_monthly:
            month = earnings['month']
            total = float(earnings['total'])

            monthly_earnings['months'][month] = total

            monthly_earnings['total_yr'] += total

        return Response(monthly_earnings) 




