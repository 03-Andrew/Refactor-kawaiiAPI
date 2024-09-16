from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('available-rooms/', views.available_rooms, name="available_rooms"),
    path("api/available-rooms/", views.available_rooms_api, name="api_available_rooms"),
    path("api/booking/", views.BookingListCreate.as_view(), name="booking"),
    path('api/rooms/', views.RoomListCreateView.as_view(), name='room-list-create'),
    path('api/rooms/<int:pk>/', views.RoomDetailView.as_view(), name='room-detail'),
]