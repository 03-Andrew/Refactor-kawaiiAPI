from django.urls import path
from .views import rooms, bookings


urlpatterns = [
    path('api/rooms/', rooms.RoomListCreateView.as_view(), name='room_list_create'),
    path('api/rooms/<int:pk>/', rooms.RoomDetailView.as_view(), name='room_detail'),
    path('api/room-types/', rooms.RoomTypesListView.as_view(), name='room_types_list'),
    path('api/room-types/<int:pk>/', rooms.RoomTypesDetailView.as_view(), name='room_types_detail'),

    # path('api/booking/', bookings.BookingListCreate.as_view(), name='booking'),
    # path('api/booking/current/', bookings.GetBookedRoomsNow.as_view(), name='booked_rooms_now'),
    # path('api/create-stayin-booking/', bookings.CreateStayInBooking.as_view(), name='create_stayin_booking'),
    path('api/bookings/online', bookings.CreateOnlineBooking.as_view(), name='create_online_booking'),
    path('api/bookings/lock-room-type', bookings.LockRoomType.as_view(), name='lock_room_type'),
    path('api/bookings/release-room-type', bookings.ReleaseRoomType.as_view(), name='release_room_type'),
    # path('api/create-daytour-guest/', bookings.CreateDayTourGuest.as_view(), name='create_day_tour'),
]
