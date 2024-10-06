from django.urls import path, include
from . import views

urlpatterns = [
    path("api/billings/", views.BillingList.as_view(), name="billings"),
    path("api/billings/create/", views.BillingCreate.as_view(), name="create-billing"),
    path("api/billings/edit/<int:pk>/", views.BillingUpdate.as_view(), name="edit-billing"),
    path("api/billing-details/<int:pk>/", views.BillingDetails.as_view(), name="billing-details"),
    
    path("api/active-billings/", views.ActiveBookings.as_view(), name="active-billings"),
    path("api/customer/", views.CustomerListCreate.as_view(), name="customers"),
    
    path("api/payment/", views.PaymentListCreate.as_view(), name="payment"),
    
    path("api/pending-billing-list/", views.ListBillingBooking.as_view()),
    
    path("api/guests/", views.GuestListView.as_view(), name="guest-list"),
    path("api/guests/add/", views.AddGuest.as_view(), name="add-guest-list"),
    path("api/guests/<int:pk>/", views.GuestListPerBilling.as_view(), name="guest-list-per-billing"),
    path("api/guests-status/edit/<int:pk>/", views.EditGuestListStatus.as_view(), name="edit-guest-list"),
    
    path("api/foodbill/add/", views.AddFoodBill.as_view(), name="add-food-bill"),
    
]