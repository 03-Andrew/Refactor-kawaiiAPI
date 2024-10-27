from django.urls import path
#from .views import payment_page, AttachPaymentMethod,CreatePaymentIntent, CreateCardPaymentMethod, CreateGCashSource, GCashWebhook
from .views import CardPayment, GCashSource, CreateLink
from .views import WebhookNotif

#from .views import PaymentIntentList

urlpatterns = [
    # For posting card payments
    path('api/payment-card/', CardPayment.as_view(), name='create_payment_card'), #FINAL

    # For GCASH
    path('api/payment-gcash/', GCashSource.as_view(), name='create_source_gcash'),
    # path('api/payment-gcash/', GCashPayment.as_view(), name='create_payment_gcash'),

    # For Link
    path('api/payment-link/', CreateLink.as_view(), name='create_link'),

    # Webhook testing
    path('api/webhook/', WebhookNotif.as_view(), name='view_webhook_notif'), #FOR TESTING

]
