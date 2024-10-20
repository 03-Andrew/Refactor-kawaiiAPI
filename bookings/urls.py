from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('available-rooms/', views.available_rooms, name="available_rooms"),
    path("api/available-rooms/", views.get_available_rooms1, name="api_available_rooms"),
    path("api/available-rooms2/", views.AvailableRooms.as_view(), name="available_rooms2"),
    path("api/booking/", views.BookingListCreate.as_view(), name="booking"),
    path('api/rooms/', views.RoomListCreateView.as_view(), name='room-list_create'),
    path('api/rooms/<int:pk>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('api/room-types/', views.RoomTypes.as_view()),
    path('api/create-stayin-booking/', views.CreateStayInBooking.as_view(), name='create_stayin_booking'),

    path('api/booking/current/', views.GetBookedRoomsNow.as_view(), name='booked_rooms_now')
]