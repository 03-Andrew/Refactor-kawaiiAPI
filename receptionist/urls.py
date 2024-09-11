from django.urls import path
from . import views

urlpatterns = [
    path('api/booking-pending',views.booking_list_pending,name = "booking-pending"), #For viewing bookings
    path('api/booking-pending-detail/<str:pk>',views.BookingDetailPending.as_view(),name = "booking-pending-detail"), #For approving/updating bookings

]