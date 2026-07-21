from django.contrib import admin
from django.urls import path, include
from receptionist.consumers import ReceptionistConsumer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('', include('bookings.urls')),
    path('', include('transactions.urls')),
    path('', include('receptionist.urls')),
    path('', include('user.urls')),
    path('', include('paymongo.urls')),
    path('', include('reports.urls')),

    # Swagger / OpenAPI
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

websocket_urlpatterns = [
    path('ws/receptionist/', ReceptionistConsumer.as_asgi()),  # WebSocket route
]
