from django.urls import path, include
from . import views

urlpatterns = [
    path("api/transactions", views.TransactionListCreate.as_view(), name="transactions"),
    path("api/customer", views.CustomerListCreate.as_view(), name="customers"),

]