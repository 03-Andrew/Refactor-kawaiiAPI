from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response

from django.db.models import F, Sum, Q, Exists, OuterRef
from datetime import date, timedelta, datetime
from calendar import monthrange
from collections import defaultdict
from datetime import timedelta


from transactions.models import Payment
from django.db.models.functions import ExtractMonth

from bookings.models import Room
from transactions.models import Amenities, Activity, FoodBill, Payment, ExtraItems

from receptionist.serializers import PaymentSerializer

# Create your views here.
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
            'months': {month: 0.0 for month in range(1, 13)},  # Initialize all months with 0
            'total_yr': 0.0
        }

        for earnings in earnings_monthly:
            month = earnings['month']
            total = float(earnings['total'])

            monthly_earnings['months'][month] = total

            monthly_earnings['total_yr'] += total

        return Response(monthly_earnings) 

def process_payments(data, serialized_data):
    for item in serialized_data:
        paid_for = item.get('paid_for')

        # Check if `paid_for` is a dictionary (object) before proceeding
        if not isinstance(paid_for, dict):
            print(f"Skipping non-dict paid_for: {paid_for} (type: {type(paid_for)})")
            continue

        try:
            # Add the amount to total only if paid_for is valid
            amount = float(item['amount'])  
            
            if item['paymentFor'] in ["Room", "Down payment"]:
                field = str(paid_for['room'])
                data['bookings'][field]['amount'] += amount
                data['bookings'][field]['pax/hrs'] = int(paid_for['adult_count']) + int(paid_for['children_count'])
                data['Total'] += amount 
                continue

            if item['paymentFor'] == 'Activities':
                field = paid_for['activity']['activity']
                data['other sales'][field]['amount'] += amount
                data['other sales'][field]['pax/hrs'] = float(paid_for['hours_availed'])
                data['Total'] += amount  
                continue

            if item['paymentFor'] == 'Amenities':
                field = paid_for['amenity']['amenity']
                data['other sales'][field]['amount'] += amount
                data['other sales'][field]['pax/hrs'] = int(paid_for['head_count'])
                data['Total'] += amount  

            if item['paymentFor'] == 'Food':
                data['Food bill'] += amount
                data['Total'] += amount 
                continue

        except TypeError as e:
            print(f"Error accessing fields in paid_for: {paid_for} - Error: {e}")

    return data

def initialize_data(rooms, amenities, activities):
    data = {}
    
    data['bookings'] = {}
    for item in rooms:            
        data['bookings'][item.number] = {'amount': 0, 'pax/hrs': 0}

    data['other sales'] = {} 
    for item in amenities:
        data['other sales'][item.amenity] = {'amount': 0, 'pax/hrs': 0}
    for item in activities:
        data['other sales'][item.activity] = {'amount': 0, 'pax/hrs': 0}  
    
    # data['other extras'] = {}
    # for item in extraItems:
    #     data['other extras'][item.item] = {'amount': 0, 'pax/hrs': 0}  

    data['Food bill'] = 0
    data['Total'] = 0

    return data 

class GetDailyReport(APIView):
    def get(self, request): 
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        data = initialize_data(rooms, amenities, activities)
        
        date = request.query_params.get('date')
        payments = Payment.objects.all()
        if date:
            payments = payments.filter(date__date=date)

        serialized_data = PaymentSerializer(payments, many=True).data
        data = process_payments(data, serialized_data)
        return Response(data)

class GetMonthlyReport(APIView):
    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        report = defaultdict(lambda: initialize_data(rooms, amenities, activities))

        year = request.query_params.get('year')
        start_month = request.query_params.get('s')  # Start month
        end_month = request.query_params.get('e')    # End month

        if not year:
            return Response({"error": "Year is required."}, status=400)

        # If end_month is not provided, treat it as the same as start_month
        if not end_month:
            end_month = start_month

        start_month = int(start_month)
        end_month = int(end_month)

        for month in range(start_month, end_month + 1):
            month_name = datetime(2000, month, 1).strftime('%B') 
            month_key = f"{month_name} {year}"


            payments = Payment.objects.filter(date__year=year, date__month=month)


            first_day_of_month = datetime(year=int(year), month=int(month), day=1)
            last_day_of_month = (first_day_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            week_start = first_day_of_month
            while week_start <= last_day_of_month:
                week_end = week_start + timedelta(days=6) 
                week_end = min(week_end, last_day_of_month)  
                
                week_key = f"week {week_start.isocalendar()[1]} ({week_start.strftime('%b %d, %Y')} - {week_end.strftime('%b %d, %Y')})"
                
                weekly_payments = payments.filter(date__gte=week_start, date__lte=week_end)
                serialized_data = PaymentSerializer(weekly_payments, many=True).data
                
                report[week_key] = process_payments(report[week_key], serialized_data)

                week_start += timedelta(days=7)

        response_data = {week: report[week] for week in sorted(report.keys())}

        return Response(response_data)

class GetYearlyReport(APIView):
    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        report = defaultdict(lambda: initialize_data(rooms, amenities, activities))

        start_year = request.query_params.get('s') # Start year
        end_year = request.query_params.get('e') # End year

        # If end_month is not provided, treat it as the same as start_year
        if not end_year:
            end_year = start_year

        start_year = int(start_year)
        end_year = int(end_year)

        if not start_year:
            return Response({"error": "Start year is required."}, status=400)

        for current_year in range(start_year, end_year + 1):
            for month in range(1, 13): 
                month_name = datetime(2000, month, 1).strftime('%B') 
                month_key = f"year {current_year} ({month_name})"

                monthly_payments = Payment.objects.filter(date__year=current_year, date__month=month)

                serialized_data = PaymentSerializer(monthly_payments, many=True).data
                
                report[month_key] = process_payments(report[month_key], serialized_data)

        response_data = {month_key: report[month_key] for month_key in report}

        return Response(response_data)

# class GetMonthlyReports(APIView):
#     def get(self, request):
#         # Get the start_month and end_month from query parameters
#         start_month = request.query_params.get('s')
#         end_month = request.query_params.get('e')

#         # If end_month is not provided, treat it as the same as start_month
#         if not end_month:
#             end_month = start_month
        
#         # Parse the provided months (in the format 'YYYY-MM' like '2024-01')
#         try:
#             start_date = datetime.strptime(start_month, '%Y-%m')
#             end_date = datetime.strptime(end_month, '%Y-%m')
#         except ValueError:
#             return Response({'error': 'Invalid month format. Use YYYY-MM format.'}, status=400)

#         # Get the first day of the start month and the last day of the end month
#         start_of_month = start_date.replace(day=1)
#         end_of_month = end_date.replace(day=monthrange(end_date.year, end_date.month)[1])

#         # Filter payments by date range
#         payments = Payment.objects.filter(date__range=[start_of_month, end_of_month])
        
#         # Group payments by week and total the earnings
#         earnings_by_week = {}
#         for payment in payments:
#             week_number = payment.date.isocalendar()[1]  # Get the week number
#             year_week_key = f"{payment.date.year}-W{week_number}"  # e.g., '2024-W01'
            
#             if year_week_key not in earnings_by_week:
#                 earnings_by_week[year_week_key] = {
#                     'range': {
#                         'start_date': payment.date - timedelta(days=payment.date.weekday()),  # Monday of the week
#                         'end_date': payment.date + timedelta(days=(6 - payment.date.weekday()))  # Sunday of the week
#                     },
#                     'payments': [],
#                     'total': 0
#                 }
            
#             earnings_by_week[year_week_key]['payments'].append({
#                 'customer_name': f'{payment.customer_bill.customer.last_name}, {payment.customer_bill.customer.first_name}' ,
#                 'payment_for': payment.paymentFor.name if payment.paymentFor else 'Unknown',
#                 'payment_type': payment.status.status if payment.status else 'Unknown',
#                 'mop': payment.mop.mode,
#                 'amount': float(payment.amount),
#                 'date': payment.date
#             })
            
#             earnings_by_week[year_week_key]['total'] += float(payment.amount)

#         # Return the response
#         return Response(earnings_by_week)