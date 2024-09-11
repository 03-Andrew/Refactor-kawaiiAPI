from django.urls import path
from . import views

urlpatterns = [
    path('api/room-status',views.room_list_status,name = "room-status"), #For viewing room status
    path('api/room-status-detail/<str:pk>',views.RoomDetailStatus.as_view(),name = "room-detail-status"), #For updating room status
    path('api/room-booking',views.room_booking_list,name = "room-booking"), #For viewing room status
    path('api/booking-pending',views.booking_list_pending,name = "booking-pending"), #For viewing pending bookings
    path('api/booking-approved',views.booking_list_approved,name = "booking-approved"), #For viewing approved bookings
    path('api/booking-pending-detail/<str:pk>',views.BookingDetailPending.as_view(),name = "booking-pending-detail"), #For approving/updating bookings
]