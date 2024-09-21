from django.urls import path, include
from . import views

urlpatterns = [
    path("api/transactions/", views.TransactionList.as_view(), name="transactions"),
    path("api/transactions/create/", views.TransactionCreate.as_view(), name="create-transaction"),
    path("api/transactions/edit/<int:pk>/", views.TransactionUpdate.as_view(), name="edit-transaction"),
    path("api/customer/", views.CustomerListCreate.as_view(), name="customers"),
    path("api/payment/", views.PaymentListCreate.as_view(), name="payment"),

]