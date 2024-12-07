from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from receptionist.consumers import ReceptionistConsumer
import django_eventstream


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('', include('bookings.urls')),
    path('', include('transactions.urls')),
    path('', include('receptionist.urls')),
    path('', include('user.urls')),
    path('', include('paymongo.urls')),
    path('', include('reports.urls')),
]

websocket_urlpatterns = [
    path('ws/receptionist/', ReceptionistConsumer.as_asgi()),  # WebSocket route
]
