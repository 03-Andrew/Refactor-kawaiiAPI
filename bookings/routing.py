# routing.py
from django.urls import path
from .channels import BookingConsumer

websocket_urlpatterns = [
    path('ws/booking/admin/', BookingConsumer.as_asgi()),
]