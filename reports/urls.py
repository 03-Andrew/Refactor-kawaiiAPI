from django.urls import path, include
from . import views

urlpatterns = [
    path("api/weekly-earnings/", views.GetWeeklyReports.as_view(), name='weekly-report'),
    path("api/monthly-report/", views.GetMonthlyReports.as_view(), name='monthly-report'),
    path("api/total-per-month/", views.GetTotalEarningsPerMonth.as_view(), name='total-per-month'),
    path("api/daily-reports/", views.GetDailyReport.as_view(), name='daily-reports')
]
