from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name="home"),
    path('available-rooms', views.available_rooms, name="available_rooms"),
    path("api/available-rooms/", views.available_rooms_api, name="api_available_rooms"),
    path("api/booking", views.BookingListCreate.as_view(), name="booking")
]