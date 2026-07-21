from django.contrib import admin
from django.urls import path, include
from receptionist.consumers import ReceptionistConsumer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


class PublicSchemaView(SpectacularAPIView):
    authentication_classes = []
    permission_classes = []


class PublicSwaggerView(SpectacularSwaggerView):
    authentication_classes = []
    permission_classes = []


class PublicRedocView(SpectacularRedocView):
    authentication_classes = []
    permission_classes = []


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('', include('bookings.urls')),
    path('', include('transactions.urls')),
    path('', include('receptionist.urls')),
    path('', include('user.urls')),
    path('', include('paymongo.urls')),
    path('', include('reports.urls')),

    path('schema/', PublicSchemaView.as_view(), name='schema'),
    path('docs/', PublicSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', PublicRedocView.as_view(url_name='schema'), name='redoc'),
]

websocket_urlpatterns = [
    path('ws/receptionist/', ReceptionistConsumer.as_asgi()),
]
