from django.urls import path, include
from . import views

urlpatterns = [
    path("api/transactions/", views.TransactionList.as_view(), name="transactions"),
    path("api/transactions/create/", views.TransactionCreate.as_view(), name="create-transaction"),
    path("api/transactions/edit/<int:pk>/", views.TransactionUpdate.as_view(), name="edit-transaction"),
    path("api/customer/", views.CustomerListCreate.as_view(), name="customers"),
    path("api/payment/", views.PaymentListCreate.as_view(), name="payment"),
    path("api/approve-transaction-list/", views.ListTransactionBooking.as_view()),
    path("api/transaction-guests/", views.GuestList.as_view(), name="guest_list"),
    path("api/transaction-guests-status/edit/", views.EditGuestListStatus.as_view(), name="edit_guest_list")

]