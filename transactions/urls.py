from django.urls import path, include
from . import views

urlpatterns = [
    path("api/billings/", views.BillingList.as_view(), name="billings"),
    path("api/billings/create/", views.BillingCreate.as_view(), name="create-billing"),
    path("api/billings/edit/<int:pk>/", views.BillingUpdate.as_view(), name="edit-billing"),
    path("api/customer/", views.CustomerListCreate.as_view(), name="customers"),
    path("api/payment/", views.PaymentListCreate.as_view(), name="payment"),
    path("api/approve-billing-list/", views.ListBillingBooking.as_view()),
    path("api/billing-guests/", views.GuestList.as_view(), name="guest_list"),
    path("api/billing-guests-status/edit/", views.EditGuestListStatus.as_view(), name="edit_guest_list")

]