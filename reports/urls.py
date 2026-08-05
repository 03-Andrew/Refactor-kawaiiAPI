from django.urls import path, include
from . import views

urlpatterns = [
    path("api/reports/monthly-total/", views.GetTotalEarningsPerMonth.as_view(), name='monthly-total'),
    path("api/reports/daily/", views.GetDailyReport.as_view(), name='daily-reports'),
    path("api/reports/monthly/", views.GetMonthlyReport.as_view(), name='monthly-report'),
    path("api/reports/yearly/", views.GetYearlyReport.as_view(), name='yearly-reports'),
    path("api/reports/weekly/", views.GetWeeklyReport.as_view(), name='weekly-report'),
]
