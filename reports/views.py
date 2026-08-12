from django.db.models import Sum
from django.db.models.functions import ExtractMonth
from django.contrib.contenttypes.models import ContentType

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.views import APIView
from rest_framework.response import Response

from datetime import timedelta, datetime
from collections import defaultdict

# Auth
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

# Models
from transactions.models import Payment, Billing, FoodBill
from bookings.models import Room, Booking
from transactions.models import Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed

# Serializers
from receptionist.serializers import PaymentSerializer

# Shared GFK prefetch
from receptionist.views import prefetch_paid_for

from kawaiiAPI.permissions import IsAdmin, IsReceptionistOrAdmin

# ── Report helpers ─────────────────────────────────────────────

PAYMENT_SELECT_RELATED = ('mop', 'status', 'customer_bill__customer')


def _fetch_payments(queryset):
    """Evaluate queryset with select_related + GFK batch-prefetch."""
    payments = list(queryset)
    prefetch_paid_for(payments)
    return payments


def process_payments(data, serialized_data):
    for item in serialized_data:
        paid_for = item.get('paid_for')

        if not isinstance(paid_for, dict):
            continue

        try:
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

    data['Food bill'] = 0
    data['Total'] = 0

    return data


# ── Report views ────────────────────────────────────────────────

@extend_schema(
    tags=['Reports'],
    parameters=[
        OpenApiParameter(name='year', type=int, description='Year for which to get total earnings per month', required=True),
    ]
)
class GetTotalEarningsPerMonth(APIView):
    permission_classes = [IsAdmin]
    def get(self, request):
        year = request.query_params.get('year')

        try:
            year = int(year)
        except (TypeError, ValueError):
            return Response({'Error please enter a valid year'}, status=400)

        earnings_monthly = (Payment.objects
                            .filter(date__year=year)
                            .annotate(month=ExtractMonth('date'))
                            .values('month')
                            .annotate(total=Sum('amount'))
                            .order_by('month'))

        monthly_earnings = {
            'months': {month: 0.0 for month in range(1, 13)},
            'total_yr': 0.0
        }

        for earnings in earnings_monthly:
            month = earnings['month']
            total = float(earnings['total'])
            monthly_earnings['months'][month] = total
            monthly_earnings['total_yr'] += total

        return Response(monthly_earnings)


@extend_schema(
    tags=['Reports'],
    parameters=[
        OpenApiParameter(name='date', type=str, description='YYYY-MM-DD format', required=False),
    ]
)
class GetDailyReport(APIView):
    permission_classes = [IsReceptionistOrAdmin]

    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        data = initialize_data(rooms, amenities, activities)

        date = request.query_params.get('date')
        payments_qs = Payment.objects.select_related(*PAYMENT_SELECT_RELATED)
        if date:
            payments_qs = payments_qs.filter(date__date=date)

        payments = _fetch_payments(payments_qs)
        serialized_data = PaymentSerializer(payments, many=True).data
        data = process_payments(data, serialized_data)
        return Response(data)


@extend_schema(
    tags=['Reports'],
    parameters=[
        OpenApiParameter(name='year', type=int, description='Year for which to get weekly earnings', required=True),
        OpenApiParameter(name='s', type=int, description='Start week number', required=True),
        OpenApiParameter(name='e', type=int, description='End week number', required=True),
    ]
)
class GetWeeklyReport(APIView):
    permission_classes = [IsReceptionistOrAdmin]
    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        report = defaultdict(lambda: initialize_data(rooms, amenities, activities))

        year = request.query_params.get('year')
        start_week = request.query_params.get('s')
        end_week = request.query_params.get('e')

        if not year:
            return Response({"error": "Year is required."}, status=400)

        if not end_week:
            end_week = start_week

        year = int(year)
        start_week = int(start_week)
        end_week = int(end_week)

        first_day_of_week = datetime.strptime(f'{year}-W{start_week}-1', "%Y-W%W-%w").date()
        last_day_of_week = datetime.strptime(f'{year}-W{end_week}-1', "%Y-W%W-%w").date() + timedelta(days=6)

        # Fetch ALL payments for the full multi-week range in ONE query
        payments_qs = Payment.objects.select_related(*PAYMENT_SELECT_RELATED).filter(
            date__date__gte=first_day_of_week,
            date__date__lte=last_day_of_week,
        )
        all_payments = _fetch_payments(payments_qs)

        # Index payments by date
        payments_by_date = defaultdict(list)
        for p in all_payments:
            payments_by_date[p.date.date()].append(p)

        for week in range(start_week, end_week + 1):
            week_first_day = datetime.strptime(f'{year}-W{week}-1', "%Y-W%W-%w").date()
            week_last_day = week_first_day + timedelta(days=6)
            week_key = f"Week {week}, {year} ({week_first_day} - {week_last_day})"

            if week_key not in report:
                report[week_key] = defaultdict(lambda: initialize_data(rooms, amenities, activities))

            for single_day in (week_first_day + timedelta(days=i) for i in range(7)):
                day_key = single_day.strftime('%Y-%m-%d')
                day_payments = list(payments_by_date.get(single_day, []))
                if day_payments:
                    serialized_data = PaymentSerializer(day_payments, many=True).data
                    report[week_key][day_key] = process_payments(report[week_key][day_key], serialized_data)

        response_data = {week: report[week] for week in sorted(report.keys())}
        return Response(response_data)


@extend_schema(
    tags=['Reports'],
    parameters=[
        OpenApiParameter(name='year', type=int, description='Year for which to get monthly earnings', required=True),
        OpenApiParameter(name='s', type=int, description='Start month number', required=True),
        OpenApiParameter(name='e', type=int, description='End month number', required=True),
    ]
)
class GetMonthlyReport(APIView):
    permission_classes = [IsReceptionistOrAdmin]
    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        report = defaultdict(lambda: defaultdict(lambda: initialize_data(rooms, amenities, activities)))

        year = request.query_params.get('year')
        start_month = request.query_params.get('s')
        end_month = request.query_params.get('e')

        if not year:
            return Response({"error": "Year is required."}, status=400)

        if not end_month:
            end_month = start_month

        start_month = int(start_month)
        end_month = int(end_month)

        # Fetch ALL payments for the full month range in ONE query
        payments_qs = Payment.objects.select_related(*PAYMENT_SELECT_RELATED).filter(
            date__year=year,
            date__month__gte=start_month,
            date__month__lte=end_month,
        )
        all_payments = _fetch_payments(payments_qs)

        # Index payments by date
        payments_by_date = defaultdict(list)
        for p in all_payments:
            payments_by_date[p.date.date()].append(p)

        for month in range(start_month, end_month + 1):
            month_name = datetime(2000, month, 1).strftime('%B')
            month_key = f"{month_name}, {year}"

            first_day_of_month = datetime(year=int(year), month=int(month), day=1)
            last_day_of_month = (first_day_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            week_start = first_day_of_month - timedelta(days=first_day_of_month.weekday())

            while week_start <= last_day_of_month:
                week_end = week_start + timedelta(days=6)

                week_key = f"Week {week_start.isocalendar()[1]}, {year} ({week_start.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')})"

                if week_key not in report[month_key]:
                    report[month_key][week_key] = initialize_data(rooms, amenities, activities)

                week_payments = [
                    p for day, day_payments in payments_by_date.items()
                    if week_start.date() <= day <= week_end.date()
                    for p in day_payments
                ]
                if week_payments:
                    serialized_data = PaymentSerializer(week_payments, many=True).data
                    report[month_key][week_key] = process_payments(report[month_key][week_key], serialized_data)

                week_start += timedelta(days=7)

        response_data = {month: report[month] for month in sorted(report.keys())}
        return Response(response_data)


@extend_schema(
    tags=['Reports'],
    parameters=[
        OpenApiParameter(name='year', type=int, description='Year for which to get yearly earnings', required=True),
        OpenApiParameter(name='s', type=int, description='Start year', required=True),
        OpenApiParameter(name='e', type=int, description='End year', required=True),
    ]
)
class GetYearlyReport(APIView):
    permission_classes = [IsAdmin]
    def get(self, request):
        rooms = Room.objects.all()
        amenities = Amenities.objects.all()
        activities = Activity.objects.all()

        report = defaultdict(lambda: defaultdict(lambda: initialize_data(rooms, amenities, activities)))

        start_year = request.query_params.get('s')
        end_year = request.query_params.get('e')
        start_month = request.query_params.get('sm')
        end_month = request.query_params.get('em')

        if not end_year:
            end_year = start_year

        start_year = int(start_year)
        end_year = int(end_year)

        if not start_year:
            return Response({"error": "Start year is required."}, status=400)

        start_month = int(start_month) if start_month else 1
        end_month = int(end_month) if end_month else 12

        if start_month < 1 or start_month > 12 or end_month < 1 or end_month > 12:
            return Response({"error": "Months must be between 1 and 12."}, status=400)

        # Build date range filter
        from datetime import date as date_type
        range_start = date_type(start_year, start_month, 1)
        if end_month == 12:
            range_end = date_type(end_year, 12, 31)
        else:
            range_end = date_type(end_year, end_month + 1, 1) - timedelta(days=1)

        # Fetch ALL payments for the full year range in ONE query
        payments_qs = Payment.objects.select_related(*PAYMENT_SELECT_RELATED).filter(
            date__date__gte=range_start,
            date__date__lte=range_end,
        )
        all_payments = _fetch_payments(payments_qs)

        # Index payments by (year, month)
        payments_by_month = defaultdict(list)
        for p in all_payments:
            payments_by_month[(p.date.year, p.date.month)].append(p)

        for current_year in range(start_year, end_year + 1):
            for month in range(start_month, end_month + 1):
                month_name = datetime(2000, month, 1).strftime('%B')
                month_key = f"{month_name}"
                month_payments = payments_by_month.get((current_year, month), [])
                if month_payments:
                    serialized_data = PaymentSerializer(month_payments, many=True).data
                    report[current_year][month_key] = process_payments(report[current_year][month_key], serialized_data)

        response_data = {f"{year} ({start_month} - {end_month})": report[year] for year in report}
        return Response(response_data)
