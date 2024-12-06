from django.urls import path
from .views import CreateLink, WebhookNotif

#from .views import PaymentIntentList

urlpatterns = [
    # For Link
    path('api/payment-link/', CreateLink.as_view(), name='create_link'),

    # Webhook testing
    path('api/webhook/', WebhookNotif.as_view(), name='view_webhook_notif'), #FOR TESTING

]
