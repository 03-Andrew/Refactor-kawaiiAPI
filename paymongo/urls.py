from django.urls import path, include
from .views import CreateLink, WebhookNotif
from . import sse

#from .views import PaymentIntentList

urlpatterns = [
    # For Link
    path('api/payment-link/', CreateLink.as_view(), name='create_link'),

    # Webhook testing
    path('api/webhook/', WebhookNotif.as_view(), name='view_webhook_notif'), #FOR TESTING

    path('events/', include('django_eventstream.urls'), {'channels': ['payments']}),
    path('test-event/', sse.trigger_payment)

]
