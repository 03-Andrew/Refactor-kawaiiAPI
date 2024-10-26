#routing.py

from django.urls import path
from .consumers import ReceptionistConsumer

websocket_urlpatterns = [
    path('ws/receptionist/', ReceptionistConsumer.as_asgi()),  # WebSocket route
]