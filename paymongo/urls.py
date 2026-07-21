from django.urls import path
from .views import CreateLink, WebhookNotif, ConfirmPayment


urlpatterns = [
    path('api/payment-link/', CreateLink.as_view(), name='create_link'),
    path('api/webhook/', WebhookNotif.as_view(), name='view_webhook_notif'),
    path('confirm-payment/', ConfirmPayment.as_view()),
]

try:
    from django.urls import include
    from . import sse
    urlpatterns += [
        path('events/', include('django_eventstream.urls'), {'channels': ['payments']}),
        path('test-event/', sse.trigger_payment),
    ]
except ImportError:
    pass
