from django.urls import path, include
from . import views
from . import views_v0

urlpatterns = [
    # v0 endpoints (unoptimized, without select_related / prefetch_related)
    path("api/v0/billings/", views_v0.BillingListV0.as_view(), name="v0-billings"),
    path("api/v0/billings/<int:pk>/", views_v0.BillingSingleEntityV0.as_view(), name="v0-single-billing"),
    path("api/v0/billings/details/<int:pk>/", views_v0.BillingDetailsV0.as_view(), name="v0-billing-details"),

    # Optimized endpoints
    path("api/billings/", views.BillingList.as_view(), name="billings"),
    path("api/billings/<int:pk>/", views.BillingSingleEntity.as_view(), name="single-billing"),
    path("api/billings/details/<int:pk>/", views.BillingDetails.as_view(), name="billing-details"),
    
    path("api/customer/", views.CustomerList.as_view(), name="customers"),
    path("api/customer/<int:pk>", views.CustomerSingleEntity.as_view()),

    path("api/payment/multiple/", views.CreatePayment.as_view(), name="create-multiple-payment"),
    
    path("api/guests/", views.GuestListView.as_view(), name="guest-list"),
    path("api/guests/<int:pk>/", views.GuestListSingleEntity.as_view(), name="edit-guest-list"),
    
    path("api/foodbill/", views.AddFoodBill.as_view(), name="add-food-bill"),
    path("api/foodbill/<int:pk>/", views.ModifyFoodBill.as_view(), name='modify-foodbill'),

    path("api/food/", views.AddFoodList.as_view(), name="add-food-list"),
    path("api/food/<int:pk>/", views.ModifyFoodList.as_view(), name='modify-food-list'),

    path("api/additional-payments/", views.AdditionalPayments.as_view(), name="add-additional-payments"),
]