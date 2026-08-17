from django.urls import path
from .views import CreatePaymentQr, CreateCheckoutSession, WebhookNotif

urlpatterns = [
    path('api/qr-code/', CreatePaymentQr.as_view(), name="create_payment_intent"),
    path('api/checkout-session/', CreateCheckoutSession.as_view(), name="create_checkout_session"),
    path('api/webhook/', WebhookNotif.as_view(), name='view_webhook_notif'),
]

# try:
#     from django.urls import include
#     from . import sse
#     urlpatterns += [
#         path('events/', include('django_eventstream.urls'), {'channels': ['payments']}),
#         path('test-event/', sse.trigger_payment),
#     ]
# except ImportError:
#     pass
