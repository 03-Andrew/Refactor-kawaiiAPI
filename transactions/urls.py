from django.urls import path, include
from . import views

urlpatterns = [
    path("api/billings/", views.BillingList.as_view(), name="billings"),
    path("api/billings/<int:pk>/", views.BillingSingleEntity.as_view(), name="single-billing"),
    path("api/billings/details/<int:pk>/", views.BillingDetails.as_view(), name="billing-details"),
    
    path("api/customer/", views.CustomerListCreate.as_view(), name="customers"),
    path("api/customer/<int:pk>", views.CustomerSingleEntity.as_view()),
    
    path("api/payment/", views.PaymentListCreate.as_view(), name="payment"),
    path("api/payment/multiple/", views.CreatePayment.as_view(), name="create-multiple-payment"),
    
    path("api/guests/", views.GuestListView.as_view(), name="guest-list"),
    path("api/guests/<int:pk>/", views.GuestListSingleEntity.as_view(), name="edit-guest-list"),
    path("api/guests/per-billing/<int:pk>", views.GuestListPerBilling.as_view(), name="guest-list-per-billing"),
    
    path("api/foodbill/", views.AddFoodBill.as_view(), name="add-food-bill"),
    path("api/foodbill/<int:pk>/", views.ModifyFoodBill.as_view(), name='modify-foodbill'),

    path("api/food/", views.AddFoodList.as_view(), name="add-food-list"),
    path("api/food/<int:pk>/", views.ModifyFoodList.as_view(), name='modify-food-list'),

    path("api/additional-payments/", views.AdditionalPayments.as_view(), name="add-additional-payments"),
]