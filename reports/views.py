from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response

from django.db.models import F, Sum, Q, Exists, OuterRef
from datetime import date, timedelta, datetime
from calendar import monthrange

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



class GetDailyReport(APIView):
    def get_json(self):
        data = {}
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()
        extraItems = ExtraItems.objects.all()


        data['bookings'] = {}
        for item in rooms:            
            data['bookings'][item.number] = {'amount': 0,'pax/hrs': 0}

        data['other sales'] = {} 
        for item in amenities:
            data['other sales'][item.amenity] = {'amount': 0,'pax/hrs': 0}
        for item in activities:
            data['other sales'][item.activity] = {'amount': 0,'pax/hrs': 0}  
        
        data['other extras'] = {}
        for item in extraItems:
            data['other extras'][item.item] = {'amount': 0,'pax/hrs': 0}  

        data['Food bill'] = 0
        return data 
          
    def get(self, request):
        date = request.query_params.get('date')
        data = self.get_json()
        payments = Payment.objects.all()
        if date:
            payments = payments.filter(date__date=date)

        serialized_data = PaymentSerializer(payments, many=True).data
        for item in serialized_data:
            if item['paymentFor'] in ["Room", "Down payment"]:
                field = str(item['paid_for']['room'])
                data['bookings'][field]['amount'] += float(item['amount'])
                data['bookings'][field]['pax/hrs'] = int(item['paid_for']['adult_count']) + int(item['paid_for']['children_count'])
                continue
            
            if item['paymentFor'] == 'Activities':
                field = item['paid_for']['activity']['activity']
                data['other sales'][field]['amount'] += float(item['amount'])
                data['other sales'][field]['pax/hrs'] = float(item['paid_for']['hours_availed'])
                continue

            if item['paymentFor'] == 'Amenities':
                field = item['paid_for']['amenity']['amenity']
                data['other sales'][field]['amount'] += float(item['amount'])
                data['other sales'][field]['pax/hrs'] = int(item['paid_for']['head_count'])
                continue
            
            if item['paymentFor'] == 'Food':
                data['Food bill'] += float(item['amount'])
                continue


                
        return Response(data)
 




