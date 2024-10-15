from django.urls import path
#from .views import payment_page, AttachPaymentMethod,CreatePaymentIntent, CreateCardPaymentMethod, CreateGCashSource, GCashWebhook
from .views import CardPayment, GCashSource, GCashPayment
from .views import WebhookNotif

#from .views import PaymentIntentList

urlpatterns = [
    # For posting card payments
    path('api/payment-card/', CardPayment.as_view(), name='create_payment_card'), #FINAL

    # For GCASH
    path('api/source-gcash/', GCashSource.as_view(), name='create_source_gcash'),
    path('api/payment-gcash/', GCashPayment.as_view(), name='create_payment_gcash'),

    # Webhook testing
    path('api/webhook-notif/', WebhookNotif.as_view(), name='view_webhook_notif'), #FOR TESTING

]
