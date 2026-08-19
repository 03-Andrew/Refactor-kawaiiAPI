from django.urls import path
from . import views
from . import views_v0

urlpatterns = [
    # v0 endpoints (unoptimized, without select_related / prefetch_paid_for)
    path("api/v0/reports/monthly-total/", views_v0.GetTotalEarningsPerMonth.as_view(), name='v0-monthly-total'),
    path("api/v0/reports/daily/", views_v0.GetDailyReport.as_view(), name='v0-daily-reports'),
    path("api/v0/reports/monthly/", views_v0.GetMonthlyReport.as_view(), name='v0-monthly-report'),
    path("api/v0/reports/yearly/", views_v0.GetYearlyReport.as_view(), name='v0-yearly-reports'),
    path("api/v0/reports/weekly/", views_v0.GetWeeklyReport.as_view(), name='v0-weekly-report'),

    # Optimized endpoints
    path("api/reports/monthly-total/", views.GetTotalEarningsPerMonth.as_view(), name='monthly-total'),
    path("api/reports/daily/", views.GetDailyReport.as_view(), name='daily-reports'),
    path("api/reports/monthly/", views.GetMonthlyReport.as_view(), name='monthly-report'),
    path("api/reports/yearly/", views.GetYearlyReport.as_view(), name='yearly-reports'),
    path("api/reports/weekly/", views.GetWeeklyReport.as_view(), name='weekly-report'),
]
