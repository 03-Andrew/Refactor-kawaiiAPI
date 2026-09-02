from datetime import datetime

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes, authentication_classes

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from receptionist.consumers import ReceptionistConsumer


def home(request):
    return JsonResponse({
        'root': 'Kawaii API',
        'time': datetime.now().isoformat(),
    })


@api_view(['GET'])
@permission_classes([])
@authentication_classes([])
def health_check(request):
    return JsonResponse({
        'status': 'ok',
        'time': datetime.now().isoformat(),
    })


urlpatterns = [
    path('', home, name='home'),
    path('api/health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('', include('bookings.urls')),
    path('', include('transactions.urls')),
    path('', include('receptionist.urls')),
    path('', include('user.urls')),
    path('', include('paymongo.urls')),
    path('', include('reports.urls')),
    path('', include('agent.urls')),

    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

websocket_urlpatterns = [
    path('ws/receptionist/', ReceptionistConsumer.as_asgi()),
]
