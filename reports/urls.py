from django.urls import path, include
from . import views

urlpatterns = [
    path("api/total-per-month/", views.GetTotalEarningsPerMonth.as_view(), name='total-per-month'),
    path("api/daily-reports/", views.GetDailyReport.as_view(), name='daily-reports'),
    path("api/monthly-reports/", views.GetMonthlyReport.as_view(), name='monthly-report'),
    path("api/yearly-reports/", views.GetYearlyReport.as_view(), name='yearly-reports'),
    path("api/weekly-reports/", views.GetWeeklyReport.as_view(), name='weekly-report'),
]
