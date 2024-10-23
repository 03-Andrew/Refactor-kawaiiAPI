# receptionist/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/booking_notifications/', consumers.BookingConsumer.as_asgi()),  # WebSocket URL for receptionist
]
