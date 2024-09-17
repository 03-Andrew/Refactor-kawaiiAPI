from django.urls import path
from . import views

urlpatterns = [
    #For viewing room status
    path('api/room-status/',views.room_list_status,name = "room-status"), 
    #For updating room status
    path('api/room-status-detail/<str:pk>/',views.RoomDetailStatus.as_view(),name = "room-detail-status"), 
    #For viewing today's room bookings
    path('api/room-booking/',views.room_booking_list,name = "room-booking"), 

    #For viewing pending bookings
    path('api/booking-pending/',views.booking_list_pending,name = "booking-pending"),
    #For viewing approved bookings
    path('api/booking-approved/',views.booking_list_approved,name = "booking-approved"), 
    #For updating(approving)/deleting bookings
    path('api/booking-pending-detail/<str:pk>/',views.BookingDetailPending.as_view(),name = "booking-pending-detail"),

    #For viewing all amenities
    path('api/amenities/',views.amenities_list,name = "amenities"), 
    #For viewing/adding all amenities availed
    path('api/amenities-availed/', views.AmenitiesListAvailed.as_view(), name="amenities-availed"), 
    #For deleting/updating amenities (not sure if this is needed?)
    path('api/amenities-availed-detail/<str:pk>/',views.AmenitiesDetailAvailed.as_view(),name = "amenities-detail-availed"), 
    
    #For viewing all activities
    path('api/activities/',views.activities_list,name = "activities"), 
    #For viewing/adding all activities availed
    path('api/activities-availed/', views.ActivitiesListAvailed.as_view(), name="activities-availed"), 
    #For deleting/updating activities (not sure if this is needed?)
    path('api/activities-availed-detail/<str:pk>/',views.ActivitiesDetailAvailed.as_view(),name = "activities-detail-availed"), 
]   