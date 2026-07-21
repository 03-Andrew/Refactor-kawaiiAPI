from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('api/health/', views.health_check, name="health_check"),
    # path('available-rooms/', views.AvailableRoomTypes.as_view, name="available_rooms"),
    path("api/available-rooms/", views.AvailableRoomTypes.as_view(), name="api_available_rooms"),
    path("api/available-rooms2/", views.AvailableRooms.as_view(), name="available_rooms2"),
    path("api/booking/", views.BookingListCreate.as_view(), name="booking"),
    path('api/rooms/', views.RoomListCreateView.as_view(), name='room-list_create'),
    path('api/rooms/<int:pk>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('api/room-types/', views.RoomTypes.as_view()),

    path('api/create-stayin-booking/', views.CreateStayInBooking.as_view(), name='create_stayin_booking'),
    path('api/create-online-booking/', views.CreateOnlineBooking.as_view(), name='create_online_booking'),
    path('api/create-daytour-guest/', views.CreateDayTourGuest.as_view(), name='create_day_tour'),

    path('api/booking/current/', views.GetBookedRoomsNow.as_view(), name='booked_rooms_now'),
    path('api/booking/current2/', views.GetBookedNow.as_view(), name='booked_rooms_now2'),

    path('api/rooms/status/', views.GetAvailableRoomsNow.as_view(), name='room-status')
    # path('api/av/', views.AvailableRoomTypes.as_view())
]
