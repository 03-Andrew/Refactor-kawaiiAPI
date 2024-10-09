from django.urls import path
#from .views import payment_page, AttachPaymentMethod,CreatePaymentIntent, CreateCardPaymentMethod, CreateGCashSource, GCashWebhook
from .views import CardPayment
from .views import WebhookNotif,WebhookNotif2
#from .views import PaymentIntentList

urlpatterns = [
    # For posting card payments
    path('api/payment-card/', CardPayment.as_view(), name='create_payment_card'), #FINAL
    path('api/webhook-notif/', WebhookNotif.as_view(), name='view_webhook_notif'), #FOR TESTING
    path('api/webhook-notif-2/', WebhookNotif2.as_view(), name='view_webhook_notif'), #FOR TESTING
]
